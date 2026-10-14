"""Daily audit: reads Calcme every morning and e-mails what needs a look.

Checks (read-only):
  - receivables marked as received with no bank entry (Pix/OFX) of the same amount nearby
  - orders with a value but no receivable after a couple of days
  - orders with no customer
  - overdue receivables
  - payables overdue or due in the next few days
  - bank entries with no person, with a suggestion from the statement rules
  - open "- saldo" bills left by partial payments

Customer collections (received-without-bank, orders without receivable, overdue
receivables, open partial balances) and unclassified bank entries are only checked at month close: some
customers settle the whole month at the end of it, so day to day those checks
are just noise. `CLOSE_DAY` (default 1) or `full=True` turns them on.

Result goes to S3 (audit/YYYY-MM-DD.json + audit/latest.json) and, when there's
something to see, to the SNS alerts topic (which e-mails me).
"""
from __future__ import annotations

import json
import logging
import os
import unicodedata
from datetime import date, timedelta

from ..calcme_client import CalcmeClient

log = logging.getLogger(__name__)

WINDOW_DAYS = 30
MATCH_DAYS = 5
ORDER_GRACE_DAYS = 2
PAYABLE_HEADS_UP = 3
CLOSE_DAY = int(os.getenv("AUDIT_CLOSE_DAY", "1"))
CLOSE_ONLY = ("received_without_bank_entry", "orders_without_receivable", "overdue_receivables", "open_partial_balances",
              "unclassified_bank_entries")
BANK_PREFIXES = ("PIX ", "TED ", "DOC ", "TRANSFERENCIA", "DEPOSITO")


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def _d(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def is_bank_entry(bill: dict) -> bool:
    return not bill.get("pedidos") and _norm(bill.get("descricao")).startswith(BANK_PREFIXES)


def suggest(bill: dict, rules: list[dict], kind: str) -> dict | None:
    text = _norm(bill.get("descricao"))
    for r in rules:
        if _norm(r.get("contains")) in text and r.get("kind", kind) == kind:
            return {"person_id": r.get("person_id"), "label": r.get("label")}
    return None


def _line(b: dict, today: date) -> dict:
    due = _d(b.get("dataVencimento"))
    return {"number": b.get("idInt"), "id": b.get("id"), "person": b.get("personNomeExibicao") or b.get("personNome"),
            "description": b.get("descricao"), "amount": b.get("valorConta"), "due": b.get("dataVencimento"),
            "days_late": (today - due).days if due and due < today else 0}


def audit(receivables: list[dict], payables: list[dict], orders: list[dict], statement_rules: list[dict] | None = None,
          today: date | None = None, full: bool | None = None) -> dict:
    today = today or date.today()
    if full is None:
        full = today.day == CLOSE_DAY
    since = today - timedelta(days=WINDOW_DAYS)
    bank_in = [b for b in receivables if is_bank_entry(b) and b.get("liquidado")]

    received_no_bank = []
    for b in receivables:
        when = _d(b.get("dataRecebimento") or b.get("dataVencimento"))
        if not b.get("liquidado") or is_bank_entry(b) or not b.get("pedidos") or not when or when < since:
            continue
        if "DINHEIRO" in _norm(b.get("formaPagamento")):
            continue
        match = any(round(float(e.get("valorConta") or 0), 2) == round(float(b.get("valorConta") or 0), 2)
                    and abs(((_d(e.get("dataRecebimento") or e.get("dataVencimento")) or when) - when).days) <= MATCH_DAYS
                    for e in bank_in)
        if not match:
            received_no_bank.append(_line(b, today))

    billed = {str(p.get("idInt")) for b in receivables for p in b.get("pedidos") or []}
    no_bill, no_customer = [], []
    for o in orders:
        if "CANCEL" in _norm(o.get("statusTitulo")):
            continue
        row = {"number": o.get("idInt"), "customer": o.get("clienteNome"), "date": o.get("data"), "total": o.get("valorTotal")}
        if not o.get("clienteId") and not o.get("clienteNome"):
            no_customer.append(row)
        when = _d(o.get("data"))
        has_bill = o.get("hasContas") or str(o.get("idInt")) in billed
        if not has_bill and float(o.get("valorTotal") or 0) > 0 and when and (today - when).days >= ORDER_GRACE_DAYS:
            no_bill.append(row)

    def open_(bills):
        return [b for b in bills if not b.get("liquidado") and not is_bank_entry(b)]

    overdue = [_line(b, today) for b in open_(receivables) if (_d(b.get("dataVencimento")) or today) < today]
    payables_soon = [_line(b, today) for b in open_(payables)
                     if (_d(b.get("dataVencimento")) or today + timedelta(days=99)) <= today + timedelta(days=PAYABLE_HEADS_UP)]
    balances = [_line(b, today) for b in open_(receivables) + open_(payables) if _norm(b.get("descricao")).endswith(" - SALDO")]

    unclassified = []
    for kind, bills in (("receive", receivables), ("pay", payables)):
        for b in bills:
            when = _d(b.get("dataRecebimento") or b.get("dataPagamento") or b.get("dataVencimento"))
            if b.get("personId") or not is_bank_entry(b) or (when and when < since):
                continue
            unclassified.append({**_line(b, today), "kind": kind, "suggestion": suggest(b, statement_rules or [], kind)})

    sections = {"received_without_bank_entry": received_no_bank, "orders_without_receivable": no_bill,
                "orders_without_customer": no_customer, "overdue_receivables": overdue,
                "payables_due_soon": payables_soon, "unclassified_bank_entries": unclassified,
                "open_partial_balances": balances}
    if not full:
        sections = {k: v for k, v in sections.items() if k not in CLOSE_ONLY}
    return {"date": today.isoformat(), "kind": "month_close" if full else "daily",
            "issues": sum(len(v) for v in sections.values()),
            "summary": {k: len(v) for k, v in sections.items()}, **sections}


def email_text(result: dict) -> tuple[str, str]:
    subject = f"Calcme audit {result['date']}: {result['issues']} item(s)"
    lines = [subject, ""]
    for key, n in result["summary"].items():  # summary only lists the sections that ran
        if not n:
            continue
        lines.append(f"- {key.replace('_', ' ')}: {n}")
        for row in result[key][:10]:
            lines.append(f"    #{row.get('number')} {row.get('person') or row.get('customer') or ''} "
                         f"{row.get('description') or ''} {row.get('amount') or row.get('total') or ''}".rstrip())
    return subject[:100], "\n".join(lines)


def run(client: CalcmeClient | None = None, statement_rules: list[dict] | None = None, today: date | None = None,
        full: bool | None = None) -> dict:
    import boto3

    client = client or CalcmeClient()
    result = audit(list(client.iter_resource("contas_receber")), list(client.iter_resource("contas_pagar")),
                   list(client.iter_resource("pedidos")), statement_rules, today, full)
    bucket = os.getenv("REPORTS_BUCKET")
    if bucket:
        s3 = boto3.client("s3")
        body = json.dumps(result, ensure_ascii=False, default=str).encode()
        for key in (f"audit/{result['date']}.json", "audit/latest.json"):
            s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    topic = os.getenv("ALERTS_TOPIC_ARN")
    if topic and result["issues"]:
        subject, text = email_text(result)
        boto3.client("sns").publish(TopicArn=topic, Subject=subject, Message=text)
    log.info("audit %s: %s issue(s)", result["date"], result["issues"])
    return {"date": result["date"], "issues": result["issues"], "summary": result["summary"]}
