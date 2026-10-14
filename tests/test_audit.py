import os
from datetime import date

os.environ.setdefault("CALCME_BASE_URL", "http://x")
os.environ.setdefault("CALCME_API_TOKEN", "t")

from laserline.audit import daily  # noqa: E402

TODAY = date(2026, 10, 14)


def bill(i, desc, amount, due, settled, person=None, orders=(), received=None):
    return {"id": f"r{i}", "idInt": i, "descricao": desc, "valorConta": amount, "dataVencimento": due,
            "liquidado": settled, "personId": person, "pedidos": [{"idInt": o} for o in orders],
            "dataRecebimento": received}


RECEIVABLES = [
    bill(1, "Pedido 18", 1130.5, "2026-09-25", True, "c1", [18], "2026-09-25"),   # no matching Pix
    bill(2, "Pedido 19", 275.0, "2026-10-01", False, "c2", [19]),                  # overdue
    bill(3, "Pedido 19 - saldo", 50.0, "2026-10-30", False, "c2"),                  # partial balance
    bill(4, 'Pix recebido: "STORE B"', 320.0, "2026-10-10", True, received="2026-10-10"),  # unclassified
]
PAYABLES = [bill(9, "Sheets", 1400.0, "2026-10-15", False, "s1")]
ORDERS = [
    {"idInt": 18, "clienteId": "c1", "clienteNome": "A", "data": "2026-09-11", "valorTotal": 1130.5},
    {"idInt": 19, "clienteId": "c2", "clienteNome": "B", "data": "2026-09-18", "valorTotal": 325.0},
    {"idInt": 20, "data": "2026-10-01", "valorTotal": 80.0},
    {"idInt": 21, "clienteId": "c2", "clienteNome": "B", "data": "2026-10-01", "valorTotal": 99.0,
     "statusTitulo": "Cancelado"},
]
RULES = [{"contains": "STORE B", "kind": "receive", "person_id": "c2", "label": "Sale"}]


def test_daily_run_leaves_collections_for_month_close():
    r = daily.audit(RECEIVABLES, PAYABLES, ORDERS, RULES, TODAY)
    assert r["kind"] == "daily" and "overdue_receivables" not in r and "unclassified_bank_entries" not in r
    assert "orders_without_customer" in r
    assert daily.audit(RECEIVABLES, PAYABLES, ORDERS, RULES, date(2026, 11, 1))["kind"] == "month_close"


def test_audit_finds_each_kind_of_issue():
    r = daily.audit(RECEIVABLES, PAYABLES, ORDERS, RULES, TODAY, full=True)
    assert [x["number"] for x in r["received_without_bank_entry"]] == [1]
    assert [x["number"] for x in r["overdue_receivables"]] == [2]
    assert [x["number"] for x in r["open_partial_balances"]] == [3]
    assert [x["number"] for x in r["payables_due_soon"]] == [9]
    assert [x["number"] for x in r["orders_without_receivable"]] == [20]   # 21 is cancelled
    assert [x["number"] for x in r["orders_without_customer"]] == [20]
    assert r["unclassified_bank_entries"][0]["suggestion"] == {"person_id": "c2", "label": "Sale"}


def test_matching_pix_clears_received_check():
    pix = bill(5, "Pix recebido: A", 1130.5, "2026-09-24", True, received="2026-09-24")
    r = daily.audit(RECEIVABLES + [pix], PAYABLES, ORDERS, RULES, TODAY, full=True)
    assert r["received_without_bank_entry"] == []


def test_email_lists_sections():
    subject, text = daily.email_text(daily.audit(RECEIVABLES, PAYABLES, ORDERS, RULES, TODAY, full=True))
    assert "item(s)" in subject and "overdue receivables" in text
