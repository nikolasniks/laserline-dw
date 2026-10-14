-- 003_dimensions.sql
-- Conformed dimensions shared across all fact tables (that's what makes it a galaxy).
-- dim_customer / dim_product are SCD type 2 so price and register changes keep history.

-- ---------- date ----------
CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key      INT PRIMARY KEY,               -- yyyymmdd
    full_date     DATE NOT NULL UNIQUE,
    year          SMALLINT NOT NULL,
    quarter       SMALLINT NOT NULL,
    month         SMALLINT NOT NULL,
    month_name    TEXT NOT NULL,
    week_of_year  SMALLINT NOT NULL,
    day_of_month  SMALLINT NOT NULL,
    day_of_week   SMALLINT NOT NULL,             -- 1=Mon .. 7=Sun (ISO)
    day_name      TEXT NOT NULL,
    is_weekend    BOOLEAN NOT NULL
);

INSERT INTO dw.dim_date
SELECT
    to_char(d, 'YYYYMMDD')::INT,
    d::DATE,
    EXTRACT(YEAR    FROM d),
    EXTRACT(QUARTER FROM d),
    EXTRACT(MONTH   FROM d),
    to_char(d, 'TMMonth'),
    EXTRACT(WEEK    FROM d),
    EXTRACT(DAY     FROM d),
    EXTRACT(ISODOW  FROM d),
    to_char(d, 'TMDay'),
    EXTRACT(ISODOW  FROM d) IN (6, 7)
FROM generate_series('2020-01-01'::DATE, '2030-12-31'::DATE, '1 day') AS d
ON CONFLICT (date_key) DO NOTHING;

-- ---------- customer ----------
CREATE TABLE IF NOT EXISTS dw.dim_customer (
    customer_sk    BIGSERIAL PRIMARY KEY,
    customer_id    TEXT NOT NULL,                -- Calcme natural key
    name           TEXT,
    doc_type       TEXT,                         -- PF / PJ
    city           TEXT,
    state          CHAR(2),
    segment        TEXT,
    valid_from     TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to       TIMESTAMPTZ,
    is_current     BOOLEAN NOT NULL DEFAULT TRUE,
    row_hash       TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_customer_current
    ON dw.dim_customer (customer_id) WHERE is_current;

-- ---------- product ----------
CREATE TABLE IF NOT EXISTS dw.dim_product (
    product_sk     BIGSERIAL PRIMARY KEY,
    product_id     TEXT NOT NULL,
    name           TEXT,
    category       TEXT,
    unit           TEXT,
    list_price     NUMERIC(14,2),
    is_simple      BOOLEAN,                      -- "produto simples" in Calcme
    valid_from     TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to       TIMESTAMPTZ,
    is_current     BOOLEAN NOT NULL DEFAULT TRUE,
    row_hash       TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_product_current
    ON dw.dim_product (product_id) WHERE is_current;

-- ---------- material (MDF sheets, acrylic, etc.) ----------
CREATE TABLE IF NOT EXISTS dw.dim_material (
    material_sk    BIGSERIAL PRIMARY KEY,
    material_id    TEXT NOT NULL UNIQUE,
    name           TEXT,
    thickness_mm   NUMERIC(6,2),
    unit           TEXT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- supplier ----------
CREATE TABLE IF NOT EXISTS dw.dim_supplier (
    supplier_sk    BIGSERIAL PRIMARY KEY,
    supplier_id    TEXT NOT NULL UNIQUE,
    name           TEXT,
    city           TEXT,
    state          CHAR(2),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- seller ----------
CREATE TABLE IF NOT EXISTS dw.dim_seller (
    seller_sk      BIGSERIAL PRIMARY KEY,
    seller_id      TEXT NOT NULL UNIQUE,
    name           TEXT,
    active         BOOLEAN,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- order status ----------
CREATE TABLE IF NOT EXISTS dw.dim_status (
    status_sk      SERIAL PRIMARY KEY,
    status_id      TEXT NOT NULL UNIQUE,
    description    TEXT,
    is_final       BOOLEAN DEFAULT FALSE
);

-- ---------- finance category (chart of accounts-ish) ----------
CREATE TABLE IF NOT EXISTS dw.dim_finance_category (
    category_sk    SERIAL PRIMARY KEY,
    category_id    TEXT NOT NULL UNIQUE,
    name           TEXT,
    kind           TEXT CHECK (kind IN ('income', 'expense', 'transfer'))
);

-- unknown members (sk = -1) so facts never get orphaned FKs
INSERT INTO dw.dim_customer (customer_sk, customer_id, name, row_hash)
    VALUES (-1, 'UNKNOWN', 'Unknown', '-') ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_product (product_sk, product_id, name, row_hash)
    VALUES (-1, 'UNKNOWN', 'Unknown', '-') ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_supplier (supplier_sk, supplier_id, name)
    VALUES (-1, 'UNKNOWN', 'Unknown') ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_seller (seller_sk, seller_id, name)
    VALUES (-1, 'UNKNOWN', 'Unknown') ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_status (status_sk, status_id, description)
    VALUES (-1, 'UNKNOWN', 'Unknown') ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_material (material_sk, material_id, name)
    VALUES (-1, 'UNKNOWN', 'Unknown') ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_finance_category (category_sk, category_id, name)
    VALUES (-1, 'UNKNOWN', 'Unknown') ON CONFLICT DO NOTHING;
