-- 004_facts.sql
-- Fact constellation. Every fact hangs off the conformed dims above,
-- so you can slice sales vs. purchases vs. cash by the same date/customer/product.

-- ---------- order lines (grain: one row per order item) ----------
CREATE TABLE IF NOT EXISTS dw.fact_order_line (
    order_id        TEXT NOT NULL,
    line_no         INT  NOT NULL,
    order_date_key  INT  NOT NULL REFERENCES dw.dim_date(date_key),
    due_date_key    INT           REFERENCES dw.dim_date(date_key),
    customer_sk     BIGINT NOT NULL DEFAULT -1 REFERENCES dw.dim_customer(customer_sk),
    product_sk      BIGINT NOT NULL DEFAULT -1 REFERENCES dw.dim_product(product_sk),
    seller_sk       BIGINT NOT NULL DEFAULT -1 REFERENCES dw.dim_seller(seller_sk),
    status_sk       INT    NOT NULL DEFAULT -1 REFERENCES dw.dim_status(status_sk),
    quantity        NUMERIC(14,3) NOT NULL,
    unit_price      NUMERIC(14,4) NOT NULL,
    discount        NUMERIC(14,2) NOT NULL DEFAULT 0,
    line_total      NUMERIC(14,2) NOT NULL,
    area_m2         NUMERIC(14,4),               -- derived from dimensions (WxHxD) when present
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, line_no)
);
CREATE INDEX IF NOT EXISTS ix_fol_date     ON dw.fact_order_line (order_date_key);
CREATE INDEX IF NOT EXISTS ix_fol_customer ON dw.fact_order_line (customer_sk);
CREATE INDEX IF NOT EXISTS ix_fol_product  ON dw.fact_order_line (product_sk);

-- ---------- purchases (grain: one row per purchase item) ----------
CREATE TABLE IF NOT EXISTS dw.fact_purchase (
    purchase_id     TEXT NOT NULL,
    line_no         INT  NOT NULL,
    purchase_date_key INT NOT NULL REFERENCES dw.dim_date(date_key),
    supplier_sk     BIGINT NOT NULL DEFAULT -1 REFERENCES dw.dim_supplier(supplier_sk),
    material_sk     BIGINT NOT NULL DEFAULT -1 REFERENCES dw.dim_material(material_sk),
    quantity        NUMERIC(14,3) NOT NULL,
    unit_cost       NUMERIC(14,4) NOT NULL,
    line_total      NUMERIC(14,2) NOT NULL,
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (purchase_id, line_no)
);

-- ---------- receivables / payables (grain: one row per installment) ----------
CREATE TABLE IF NOT EXISTS dw.fact_receivable (
    receivable_id   TEXT PRIMARY KEY,
    order_id        TEXT,
    customer_sk     BIGINT NOT NULL DEFAULT -1 REFERENCES dw.dim_customer(customer_sk),
    category_sk     INT    NOT NULL DEFAULT -1 REFERENCES dw.dim_finance_category(category_sk),
    issue_date_key  INT REFERENCES dw.dim_date(date_key),
    due_date_key    INT REFERENCES dw.dim_date(date_key),
    paid_date_key   INT REFERENCES dw.dim_date(date_key),
    amount          NUMERIC(14,2) NOT NULL,
    amount_paid     NUMERIC(14,2) NOT NULL DEFAULT 0,
    is_paid         BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dw.fact_payable (
    payable_id      TEXT PRIMARY KEY,
    purchase_id     TEXT,
    supplier_sk     BIGINT NOT NULL DEFAULT -1 REFERENCES dw.dim_supplier(supplier_sk),
    category_sk     INT    NOT NULL DEFAULT -1 REFERENCES dw.dim_finance_category(category_sk),
    issue_date_key  INT REFERENCES dw.dim_date(date_key),
    due_date_key    INT REFERENCES dw.dim_date(date_key),
    paid_date_key   INT REFERENCES dw.dim_date(date_key),
    amount          NUMERIC(14,2) NOT NULL,
    amount_paid     NUMERIC(14,2) NOT NULL DEFAULT 0,
    is_paid         BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- daily snapshot of open orders (periodic snapshot fact) ----------
CREATE TABLE IF NOT EXISTS dw.fact_order_snapshot (
    snapshot_date_key INT NOT NULL REFERENCES dw.dim_date(date_key),
    status_sk         INT NOT NULL REFERENCES dw.dim_status(status_sk),
    open_orders       INT NOT NULL,
    open_amount       NUMERIC(14,2) NOT NULL,
    PRIMARY KEY (snapshot_date_key, status_sk)
);
