import os

os.environ.setdefault("CALCME_BASE_URL", "http://x")
os.environ.setdefault("CALCME_API_TOKEN", "t")

from laserline.connector import orders  # noqa: E402
from laserline.etl.transform import area_m2_from_text, date_key  # noqa: E402

RULES = {
    "aliases": {"store a": {"customer_id": 101}, "reseller x": {"customer_id": 103}},
    "markup": {"store a": 0.10},
}


def test_ceil_cents_rounds_up():
    assert orders.ceil_cents(2.291) == 2.30
    assert orders.ceil_cents(2.30) == 2.30


def test_area_from_dims():
    assert area_m2_from_text("20x14x8") == 0.028
    assert area_m2_from_text("no dims here") is None


def test_date_key():
    assert date_key("2026-10-14") == 20261014
    assert date_key(None) is None


def test_round_up_to_ten_cents():
    assert orders.round_up(2.288) == 2.30
    assert orders.round_up(2.29) == 2.30
    assert orders.round_up(2.20) == 2.20
    assert orders.round_up(2.281, 0.01) == 2.29


def test_markup_skips_starred_items():
    d = orders.parse_note("Store A\n10 cx ts 20x14x8 2,08\n5 tag 1,50 *", RULES)
    assert d.customer_id == "101"
    plain, starred = d.items
    assert plain.unit_price == 2.30     # 2.08 * 1.10 = 2.288 -> rounded up to 2.30
    assert starred.unit_price == 1.50   # '*' = already marked up


def test_no_markup_for_other_customers():
    d = orders.parse_note("Reseller X\n10 cx ts 20x14x8 2,08", RULES)
    assert d.items[0].unit_price == 2.08


def test_unknown_customer_warns():
    d = orders.parse_note("Someone\n1 thing 3", RULES)
    assert d.customer_id == ""
    assert any("unknown customer" in w for w in d.warnings)


def test_preview_does_not_post():
    class Boom:
        def create(self, *a, **k):
            raise AssertionError("should not write on preview")

    d = orders.parse_note("Store A\n1 cx ts 10x10 5", RULES)
    out = orders.create_order(d, Boom(), confirm=False)
    assert "preview" in out
