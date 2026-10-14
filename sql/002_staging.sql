-- 002_staging.sql
-- One generic landing table. Each API resource lands here as raw JSONB,
-- so if the transform breaks we just re-run it without hammering the API again.

CREATE TABLE IF NOT EXISTS staging.raw_records (
    id            BIGSERIAL PRIMARY KEY,
    resource      TEXT        NOT NULL,          -- e.g. 'pedidos', 'clientes'
    source_id     TEXT        NOT NULL,          -- id on the Calcme side
    payload       JSONB       NOT NULL,
    payload_hash  TEXT        NOT NULL,          -- md5 of payload, skips no-op updates
    extracted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id        UUID
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_raw_resource_source_hash
    ON staging.raw_records (resource, source_id, payload_hash);

CREATE INDEX IF NOT EXISTS ix_raw_resource_extracted
    ON staging.raw_records (resource, extracted_at DESC);

-- convenience view: latest version of each record
CREATE OR REPLACE VIEW staging.latest_records AS
SELECT DISTINCT ON (resource, source_id) *
FROM staging.raw_records
ORDER BY resource, source_id, extracted_at DESC;
