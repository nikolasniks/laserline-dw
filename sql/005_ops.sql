-- 005_ops.sql
-- Pipeline bookkeeping: incremental watermarks + a run log you can actually debug with.

CREATE TABLE IF NOT EXISTS ops.watermark (
    resource     TEXT PRIMARY KEY,
    last_value   TIMESTAMPTZ NOT NULL DEFAULT '2020-01-01',
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.run_log (
    run_id        UUID PRIMARY KEY,
    job           TEXT NOT NULL,                 -- extract | transform | weekly_report
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'running'
                  CHECK (status IN ('running', 'ok', 'failed')),
    rows_in       INT DEFAULT 0,
    rows_out      INT DEFAULT 0,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS ix_run_log_job_started ON ops.run_log (job, started_at DESC);
