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
| `record_payment` | settle a bill, fully or partially (see below) | preview → confirm |
| `undo_payment` | reopen a settled bill | preview → confirm |
| `audit_now` | run the daily checks on demand | no |

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
- customer markup (if any) applies to lines **without** `*`, rounded **up** to the
  customer's step (default 10 cents: 2,288 → 2,30)
- `*` → price on paper already includes the markup, kept as is
- dims → stored as item description, area (m²) derived from W×H
- item not in catalog → created as a simple product on confirm
- note price ≠ catalog price → shows up in `warnings`

## Partial payments

The API only knows "settled" or "open", so a partial payment is a split:

1. create a new open bill with the balance (`<description> - saldo`, same person,
   due date of your choice or the original one);
2. shrink the original to what was paid and mark it settled.

The balance goes first so nothing receivable gets lost if the second call fails.
The balance bill can't carry category / cost center / order link / bank account
(the write endpoint doesn't take them), the preview says so.

## Daily audit

Every morning a Lambda reads receivables, payables and orders and flags:
received bills with no matching bank entry, orders with no receivable or no
customer, overdue receivables, payables due in the next days, bank entries with
no person (with a suggestion from the `statement` rules) and open partial
balances. Result lands in `audit/` in the reports bucket; if there's anything,
it goes out by e-mail through an SNS topic (`AlertEmail` parameter).

## Running it

```bash
make connector
```

Then point your MCP client at `python -m laserline.connector.server`
(with `PYTHONPATH=src` and the `.env` loaded).
