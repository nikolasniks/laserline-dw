# Architecture

```
                 ┌───────────────────────┐
                 │      Calcme ERP       │
                 │      (REST API)       │
                 └──────────┬────────────┘
         hourly (Mon–Sat)   │            ▲  preview -> confirm
     EventBridge → Lambda   │            │  (orders, products, updates)
                            ▼            │
┌───────────────────────────────────┐   ┌┴──────────────────────────┐
│ sync_handler                      │   │ MCP connector             │
│  extract  → staging.raw_records   │   │  laserline.connector      │
│  transform→ dw.* (dims + facts)   │   │  (runs locally)           │
└──────────────┬────────────────────┘   └───────────────────────────┘
               ▼
┌───────────────────────────────────┐   Fridays 18:00 BRT
│ RDS PostgreSQL  (laserline_dw)    │──► weekly_report_handler ──► S3
│  staging │ dw (galaxy) │ ops      │     reports/weekly/YYYY/WW/
└───────────────────────────────────┘
```

## Why a galaxy schema

Sales, purchases, receivables and payables are separate business processes with
different grains, but they share the same "who / what / when". Splitting them into
several fact tables around **conformed dimensions** (`dim_date`, `dim_customer`,
`dim_product`, `dim_supplier`, …) lets one query compare, say, revenue vs. material
spend by month without gluing star schemas together later.

| Fact | Grain | Main dims |
|---|---|---|
| `fact_order_line` | one order item | date, customer, product, seller, status |
| `fact_purchase` | one purchase item | date, supplier, material |
| `fact_receivable` | one installment | date (issue/due/paid), customer, category |
| `fact_payable` | one installment | date (issue/due/paid), supplier, category |
| `fact_order_snapshot` | day × status | date, status |

`dim_customer` and `dim_product` are **SCD type 2** — price changes and register edits
keep history, so old orders still join to the price that was valid back then.
Every dim has an `-1 / Unknown` member so a missing FK never drops a fact row.

## Load strategy

1. **Extract** — per resource, pull everything `updated_since` the last watermark,
   land as raw JSONB. Unique on `(resource, source_id, payload_hash)` → replays are free.
2. **Transform** — read `staging.latest_records`, upsert dims, then facts.
   Pure SQL-ish upserts, no ORM.
3. **Ops** — every run writes to `ops.run_log` (status, row counts, error) so you can
   `SELECT * FROM ops.run_log ORDER BY started_at DESC LIMIT 20` and see what broke.

## Security notes

- DB creds + API token live in Secrets Manager, never in env files committed to git.
- Lambdas run inside the VPC; RDS is not publicly accessible.
- Reports bucket: private, encrypted, versioned.
- API error logs never include response bodies (they can carry customer data).
- Customer nicknames / pricing rules for the order connector stay in a git-ignored file.
