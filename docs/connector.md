# Calcme connector

Small MCP server that wraps the Calcme API so I can query stuff and launch orders
from a chat window instead of clicking through the ERP every time.

## Tools

| Tool | What it does | Writes? |
|---|---|---|
| `catalog` | lists available resources | no |
| `query` | read a resource / single record | no |
| `search_customers` | name search | no |
| `register` | create a record (e.g. simple product) | preview → confirm |
| `update` | update a record, shows before/after | preview → confirm |
| `draft_order` | parse an order note into a Calcme order | preview → confirm |

**Golden rule:** `confirm=False` is the default and only returns a preview.
Nothing hits the API until the preview was checked and `confirm=True` is sent.
Orders created this way are just drafts — approval is still manual in Calcme.

## Order notes

```
Store A
10 cx ts 20x14x8 2,08 *
5 tag 1,50
```

- 1st line → customer nickname, mapped in `config/rules.json`
- each line → `qty name [WxHxD] [price] [*]`
- `*` → applies the customer's markup (if any), rounded **up** to the cent
- dims → stored as item description, area (m²) derived from W×H
- item not in catalog → created as a simple product on confirm
- note price ≠ catalog price → shows up in `warnings`

## Running it

```bash
make connector
```

Then point your MCP client at `python -m laserline.connector.server`
(with `PYTHONPATH=src` and the `.env` loaded).
