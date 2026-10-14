-- 001_schemas.sql
-- Three layers:
--   staging  -> raw JSON straight from the Calcme API (append-only, cheap to replay)
--   dw       -> galaxy schema (conformed dims + several fact tables)
--   ops      -> pipeline bookkeeping (watermarks, run log)

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS ops;

-- read-only role for BI / reporting
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_reader') THEN
    CREATE ROLE dw_reader NOLOGIN;
  END IF;
END$$;

GRANT USAGE ON SCHEMA dw TO dw_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA dw GRANT SELECT ON TABLES TO dw_reader;
