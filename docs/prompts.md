# Prompts I used

I leaned on an AI assistant for some boilerplate and as a rubber duck. Everything
was reviewed, tested and tweaked by hand. These are the main asks (cleaned up):

1. *"Design a galaxy schema for an ERP with orders, purchases, receivables and
   payables. Conformed dims, SCD2 for customer and product, unknown members."*
2. *"Write a Python client for a paginated REST API with bearer auth and
   exponential backoff on 429/5xx. Don't log response bodies."*
3. *"Incremental extract to a JSONB staging table, idempotent by payload hash,
   with a watermark table."*
4. *"SAM template: two Lambdas in a VPC, EventBridge schedules in
   America/Sao_Paulo, private encrypted S3 bucket."*
5. *"MCP server where every write tool returns a preview unless confirm=True."*
6. *"Regex to parse order lines like `10 cx ts 20x14x8 2,08 *`."*
