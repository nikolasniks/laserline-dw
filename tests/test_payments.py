import os

os.environ.setdefault("CALCME_BASE_URL", "http://x")
os.environ.setdefault("CALCME_API_TOKEN", "t")

from laserline.connector import payments  # noqa: E402


class FakeClient:
    """In-memory Calcme: PUT replaces the record, like the real API."""

    def __init__(self):
        self.bills = {"b1": {"id": "b1", "personId": "c1", "descricao": "Pedido 19", "valorConta": 275.0,
                             "dataCompetencia": "2026-09-18", "dataVencimento": "2026-10-18", "liquidado": False,
                             "pedidos": [{"idInt": 19}]}}
        self.calls = []

    def get_one(self, resource, rid):
        return dict(self.bills[rid])

    def create(self, resource, body):
        self.calls.append("POST")
        rid = f"b{len(self.bills) + 1}"
        self.bills[rid] = {"id": rid, **body}
        return self.bills[rid]

    def update(self, resource, rid, body):
        self.calls.append("PUT")
        keep = {k: v for k, v in self.bills[rid].items() if k not in payments.WRITE_FIELDS}
        self.bills[rid] = {**keep, **body}
        return self.bills[rid]


def test_preview_writes_nothing():
    c = FakeClient()
    out = payments.record_payment(c, "b1", "100")
    assert out["status"] == "preview" and out["balance"] == 175.0 and c.calls == []


def test_partial_payment_splits_balance_first():
    c = FakeClient()
    out = payments.record_payment(c, "b1", "100,00", balance_due="2026-10-30", confirm=True)
    assert out["status"] == "done" and c.calls == ["POST", "PUT"]
    original, balance = c.bills["b1"], c.bills["b2"]
    assert original["valorConta"] == 100.0 and original["liquidado"] and original["pedidos"]
    assert balance["valorConta"] == 175.0 and not balance["liquidado"]
    assert balance["personId"] == "c1" and balance["dataVencimento"] == "2026-10-30"
    assert balance["descricao"] == "Pedido 19 - saldo"


def test_full_payment_just_settles():
    c = FakeClient()
    out = payments.record_payment(c, "b1", confirm=True)
    assert out["status"] == "done" and c.calls == ["PUT"] and c.bills["b1"]["valorConta"] == 275.0


def test_blocks_overpayment_and_double_settle():
    c = FakeClient()
    assert payments.record_payment(c, "b1", 300)["status"] == "blocked"
    payments.record_payment(c, "b1", confirm=True)
    assert payments.record_payment(c, "b1", 10)["status"] == "blocked"
    assert payments.undo_payment(c, "b1", confirm=True)["status"] == "done"
    assert not c.bills["b1"]["liquidado"]
