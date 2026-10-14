# LaserLine DW — Calcme ERP Analytics on AWS

Galaxy-schema data warehouse for the **Calcme** ERP, running on **AWS RDS (PostgreSQL)**.
A serverless bot (Lambda + EventBridge) keeps it in sync, a Friday job drops weekly
reports into S3, and a small **MCP connector** lets me query the ERP and launch orders
without the UI grind.

Built for a small laser-cutting / MDF crafts shop that was tired of copy-pasting
numbers into spreadsheets. 🪵⚡

---

## TL;DR

```bash
git clone https://github.com/nikolasniks/laserline-dw && cd laserline-dw
cp .env.example .env            # fill in your creds
make install
make migrate                    # creates schemas, dims, facts, views
make sync                       # pull Calcme -> staging -> dw
make report                     # weekly report to S3
make test
```

## What's inside

```
laserline-dw/
├── sql/                 # idempotent DDL, run in order (001 → 006)
├── src/laserline/
│   ├── calcme_client.py # REST client: auth, pagination, retries
│   ├── etl/             # extract (raw JSONB) + transform (dims/facts)
│   ├── reports/         # weekly KPIs → S3 (json + csv)
│   ├── connector/       # MCP server + order-note parser
│   └── handlers.py      # Lambda entrypoints
├── infra/template.yaml  # AWS SAM: Lambdas, schedules, S3
├── config/              # rules.example.json (real one is git-ignored)
├── docs/                # architecture, connector, prompts
└── tests/
```

## The stack

| Piece | Tech |
|---|---|
| Source | Calcme REST API |
| Warehouse | PostgreSQL 16 on RDS |
| Orchestration | EventBridge Scheduler → Lambda (Python 3.12) |
| Reports | S3 (private, encrypted, versioned) |
| Secrets | AWS Secrets Manager |
| Connector | MCP (`mcp` python SDK) |
| IaC | AWS SAM |

## Data model (galaxy schema)

Five fact tables sharing conformed dims — so revenue, purchases and cash can be
sliced by the same date / customer / product. Full rundown in
[`docs/architecture.md`](docs/architecture.md).

- **Facts:** `fact_order_line`, `fact_purchase`, `fact_receivable`, `fact_payable`, `fact_order_snapshot`
- **Dims:** `dim_date`, `dim_customer` (SCD2), `dim_product` (SCD2), `dim_material`,
  `dim_supplier`, `dim_seller`, `dim_status`, `dim_finance_category`
- **Views:** `v_sales_daily`, `v_top_customers_90d`, `v_top_products_90d`, `v_cash_position`

## Schedules

| Job | When (BRT) | What |
|---|---|---|
| `sync_handler` | hourly, 07–20h, Mon–Sat | extract + transform |
| `weekly_report_handler` | Fridays 18:00 | KPIs → `s3://…/reports/weekly/YYYY/WW/` |

## Connector

Preview-first by design: nothing is written to Calcme until you've seen the payload
and sent `confirm=True`. Details in [`docs/connector.md`](docs/connector.md).

## Deploy

```bash
make deploy   # sam build + sam deploy --guided
```

You'll need: a VPC with private subnets that can reach RDS, two secrets
(DB creds + Calcme token), and a security group allowing Lambda → RDS on 5432.

## Troubleshooting

- **Sync looks stuck** → `SELECT * FROM ops.run_log ORDER BY started_at DESC LIMIT 10;`
- **Need to backfill** → `UPDATE ops.watermark SET last_value = '2020-01-01' WHERE resource = 'pedidos';`
- **Lots of 429s** → lower `CALCME_PAGE_SIZE` or space out the schedule.
- **Facts pointing at `-1`** → dims weren't loaded yet; rerun `make sync`.

## Privacy

No real customer data, credentials or company info lives in this repo. `.env`,
`config/rules.json` and any exports are git-ignored on purpose.

## Notes

Some boilerplate was drafted with AI assistance and then reviewed/tweaked by hand —
see [`docs/prompts.md`](docs/prompts.md).

## Roadmap

- [ ] dbt models on top of `dw`
- [ ] Metabase dashboards
- [ ] Slack/email ping when the weekly report lands
- [ ] cutting-time per material in the fact table (for pricing)

## License

MIT
