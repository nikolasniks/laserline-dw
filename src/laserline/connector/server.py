"""MCP server exposing the Calcme API as tools, so an assistant can look things up
and draft orders for me. Every write tool is two-step: preview first, confirm after.

Run locally:
    python -m laserline.connector.server
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..audit import daily
from ..calcme_client import RESOURCES, CalcmeClient
from . import orders, payments

mcp = FastMCP("calcme")
_client: CalcmeClient | None = None


def client() -> CalcmeClient:
    global _client
    _client = _client or CalcmeClient()
    return _client


@mcp.tool()
def catalog() -> dict:
    """List the resources this connector can read/write."""
    return {"resources": sorted(RESOURCES)}


@mcp.tool()
def query(resource: str, record_id: str | None = None, limit: int = 50) -> list | dict:
    """Read records from a resource (or a single one by id)."""
    if record_id:
        return client().get_one(resource, record_id)
    out = []
    for rec in client().iter_resource(resource):
        out.append(rec)
        if len(out) >= limit:
            break
    return out


@mcp.tool()
def search_customers(term: str) -> list[dict]:
    """Case-insensitive name search over customers."""
    t = term.lower()
    return [c for c in client().iter_resource("clientes") if t in (c.get("nome") or "").lower()][:20]


@mcp.tool()
def register(resource: str, data: dict, confirm: bool = False) -> dict:
    """Create a record. confirm=False only returns the preview."""
    if not confirm:
        return {"preview": {"resource": resource, "data": data}}
    return client().create(resource, data)


@mcp.tool()
def update(resource: str, record_id: str, data: dict, confirm: bool = False) -> dict:
    """Update a record. confirm=False only returns the preview."""
    if not confirm:
        current = client().get_one(resource, record_id)
        return {"preview": {"before": current, "changes": data}}
    return client().update(resource, record_id, data)


@mcp.tool()
def draft_order(note: str, confirm: bool = False) -> dict:
    """Parse a quick order note (first line = customer nickname) and preview/create it."""
    d = orders.parse_note(note)
    orders.resolve_products(d, client())
    return orders.create_order(d, client(), confirm=confirm)


@mcp.tool()
def record_payment(bill_id: str, paid: float | None = None, kind: str = "receive",
                   balance_due: str | None = None, confirm: bool = False) -> dict:
    """Settle a bill. Paid < total -> split: new open bill with the balance, original shrunk and settled."""
    return payments.record_payment(client(), bill_id, paid, kind, balance_due, confirm)


@mcp.tool()
def undo_payment(bill_id: str, kind: str = "receive", confirm: bool = False) -> dict:
    """Reopen a settled bill."""
    return payments.undo_payment(client(), bill_id, kind, confirm)


@mcp.tool()
def audit_now() -> dict:
    """Run the daily audit right now (read-only, no e-mail)."""
    c = client()
    return daily.audit(list(c.iter_resource("contas_receber")), list(c.iter_resource("contas_pagar")),
                       list(c.iter_resource("pedidos")), orders.load_rules().get("statement", []))


if __name__ == "__main__":
    mcp.run()
