"""Mark receivables/payables as paid, fully or partially.

Calcme's API has no "partial payment": a bill is either settled or not. So a
partial payment is done as a split, in this order:

  1. create a new open bill with the remaining balance ("<description> - saldo"),
     same person, due date = the one given or the original;
  2. shrink the original bill to the amount actually paid and mark it settled.

The balance bill goes first on purpose: if step 2 fails, nothing receivable is
lost, the original is still open and we just report it.

Same rule as everything else in the connector: confirm=False only previews.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from ..calcme_client import CalcmeClient

KINDS = {"receive": "contas_receber", "pay": "contas_pagar"}
# fields the bill write endpoint accepts; PUT replaces the record, so we always send all of them back
WRITE_FIELDS = ("personId", "descricao", "valorConta", "dataCompetencia", "dataVencimento", "liquidado")


def _money(v) -> Decimal:
    return Decimal(str(v).replace(",", ".")).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _body(bill: dict, **changes) -> dict:
    body = {k: bill.get(k) for k in WRITE_FIELDS if bill.get(k) is not None}
    body.update(changes)
    return body


def record_payment(client: CalcmeClient, bill_id: str, paid=None, kind: str = "receive",
                   balance_due: str | None = None, confirm: bool = False) -> dict:
    resource = KINDS[kind]
    bill = client.get_one(resource, bill_id)
    total = _money(bill["valorConta"])
    paid = total if paid in (None, "") else _money(paid)

    if bill.get("liquidado"):
        return {"status": "blocked", "reason": "bill is already settled; undo it first"}
    if paid <= 0 or paid > total:
        return {"status": "blocked", "reason": f"paid amount must be between 0 and {total}"}

    balance = total - paid
    plan = {"bill": bill_id, "total": float(total), "paid": float(paid), "balance": float(balance)}
    if balance == 0:
        plan["steps"] = ["mark bill as settled"]
    else:
        plan["steps"] = [f"create open bill of {balance} (balance)", f"set original to {paid} and mark settled"]
        plan["warnings"] = ["the balance bill has no category / cost center / order link / bank account "
                            "(the API doesn't accept those fields)"]
    if not confirm:
        return {"status": "preview", **plan}

    created = None
    if balance:
        new_bill = {"descricao": f"{bill.get('descricao') or 'Conta'} - saldo", "valorConta": float(balance),
                    "dataCompetencia": bill.get("dataCompetencia"),
                    "dataVencimento": balance_due or bill.get("dataVencimento"), "liquidado": False}
        if bill.get("personId"):
            new_bill["personId"] = bill["personId"]
        created = client.create(resource, new_bill)
    try:
        client.update(resource, bill_id, _body(bill, valorConta=float(paid), liquidado=True))
    except Exception as exc:  # noqa: BLE001 - balance already exists, report instead of retrying
        return {"status": "partial", "balance_bill": created, "error": str(exc), **plan}
    return {"status": "done", "balance_bill": created, **plan}


def undo_payment(client: CalcmeClient, bill_id: str, kind: str = "receive", confirm: bool = False) -> dict:
    resource = KINDS[kind]
    bill = client.get_one(resource, bill_id)
    if not bill.get("liquidado"):
        return {"status": "unchanged", "reason": "bill is already open"}
    if not confirm:
        return {"status": "preview", "steps": ["mark bill as open again"]}
    client.update(resource, bill_id, _body(bill, liquidado=False))
    return {"status": "done"}
