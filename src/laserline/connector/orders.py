"""Order launcher: turns a quick handwritten-style note into a Calcme order.

Rule #1: nothing is written without a preview first. `create_order(confirm=False)`
returns what *would* be sent; only `confirm=True` actually POSTs.
Creating an order doesn't move money — approval still happens by hand in Calcme.

Customer nicknames and pricing rules live in a local, git-ignored file
(`config/rules.json`, see `config/rules.example.json`) so no customer data ends up in the repo.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..calcme_client import CalcmeClient
from ..etl.transform import area_m2_from_text

RULES_PATH = Path(__file__).resolve().parents[3] / "config" / "rules.json"


def load_rules(path: Path = RULES_PATH) -> dict:
    if not path.exists():
        return {"aliases": {}, "markup": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def round_up(v: float, step: float = 0.10) -> float:
    """Round UP to the next multiple of `step` (default 10 cents: 2.288 -> 2.30, 2.29 -> 2.30)."""
    if not step:
        return round(v, 2)
    return round(math.ceil(round(v / step, 6)) * step, 2)


@dataclass
class OrderItem:
    name: str
    description: str = ""
    quantity: float = 1
    unit_price: float = 0.0
    product_id: str | None = None
    marked: bool = False          # '*' in the note = price already includes the customer's markup
    area_m2: float | None = None


@dataclass
class OrderDraft:
    customer_id: str
    items: list[OrderItem] = field(default_factory=list)
    notes: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(sum(i.quantity * i.unit_price for i in self.items), 2)


LINE_RE = re.compile(
    r"^\s*(?P<qty>\d+(?:[.,]\d+)?)\s*(?:x|un)?\s+(?P<name>.+?)"
    r"(?:\s+(?P<dims>\d+(?:[.,]\d+)?[xX]\d+(?:[.,]\d+)?(?:[xX]\d+(?:[.,]\d+)?)?))?"
    r"(?:\s+(?:R\$)?\s*(?P<price>\d+(?:[.,]\d+)?))?\s*(?P<star>\*)?\s*$"
)


def parse_note(note: str, rules: dict | None = None) -> OrderDraft:
    """First line = customer nickname, rest = items like '10 cx ts 20x14x8 2,29 *'."""
    rules = rules or load_rules()
    lines = [ln for ln in note.strip().splitlines() if ln.strip()]
    alias = lines[0].strip().lower()
    cust = rules["aliases"].get(alias)
    draft = OrderDraft(customer_id=str(cust["customer_id"]) if cust else "")
    if not cust:
        draft.warnings.append(f"unknown customer nickname: {lines[0]!r}")

    markup = rules["markup"].get(alias, 0.0)
    step = rules.get("rounding_step", {}).get(alias, 0.10)
    for raw in lines[1:]:
        m = LINE_RE.match(raw)
        if not m:
            draft.warnings.append(f"couldn't parse line: {raw!r}")
            continue
        price = float((m["price"] or "0").replace(",", "."))
        star = bool(m["star"])
        if markup and not star:      # starred lines were already marked up on paper
            price = round_up(price * (1 + markup), step)
        draft.items.append(OrderItem(
            name=m["name"].strip(), description=m["dims"] or "",
            quantity=float(m["qty"].replace(",", ".")), unit_price=price,
            marked=star, area_m2=area_m2_from_text(m["dims"]),
        ))
    return draft


def resolve_products(draft: OrderDraft, client: CalcmeClient, catalog: list[dict] | None = None) -> None:
    """Match item names against the catalog; flag missing ones + price mismatches."""
    catalog = catalog if catalog is not None else list(client.iter_resource("produtos"))
    by_name = {(p.get("nome") or "").strip().lower(): p for p in catalog}
    for it in draft.items:
        p = by_name.get(it.name.lower())
        if not p:
            draft.warnings.append(f"'{it.name}' not in catalog -> will be created as simple product")
            continue
        it.product_id = str(p["id"])
        list_price = float(p.get("preco") or 0)
        if list_price and not it.marked and abs(list_price - it.unit_price) > 0.009:
            draft.warnings.append(
                f"'{it.name}': note price {it.unit_price:.2f} != catalog {list_price:.2f}")


def to_payload(draft: OrderDraft) -> dict:
    return {
        "cliente_id": draft.customer_id,
        "observacao": draft.notes,
        "itens": [
            {"produto_id": i.product_id, "descricao": i.description,
             "quantidade": i.quantity, "valor_unitario": i.unit_price}
            for i in draft.items
        ],
    }


def create_order(draft: OrderDraft, client: CalcmeClient, confirm: bool = False) -> dict:
    payload = to_payload(draft)
    if not confirm:
        return {"preview": payload, "total": draft.total, "warnings": draft.warnings,
                "items": [asdict(i) for i in draft.items]}
    if not draft.customer_id:
        raise ValueError("refusing to create order without a customer")
    for it in draft.items:
        if not it.product_id:  # auto-create missing simple products
            created = client.create("produtos", {"nome": it.name, "tipo": "simples",
                                                 "preco": it.unit_price})
            it.product_id = str(created["id"])
    return client.create("pedidos", to_payload(draft))
