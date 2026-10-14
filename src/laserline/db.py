"""Postgres helpers (psycopg 3)."""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator

import psycopg

from .config import get_settings


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(get_settings().pg_dsn, autocommit=False) as conn:
        yield conn


def start_run(conn: psycopg.Connection, job: str) -> uuid.UUID:
    run_id = uuid.uuid4()
    conn.execute("INSERT INTO ops.run_log (run_id, job) VALUES (%s, %s)", (run_id, job))
    conn.commit()
    return run_id


def finish_run(conn, run_id, status="ok", rows_in=0, rows_out=0, error=None) -> None:
    conn.execute(
        """UPDATE ops.run_log
              SET finished_at = now(), status = %s, rows_in = %s, rows_out = %s, error = %s
            WHERE run_id = %s""",
        (status, rows_in, rows_out, (error or "")[:2000] or None, run_id),
    )
    conn.commit()


def get_watermark(conn, resource: str) -> str:
    row = conn.execute(
        "SELECT last_value FROM ops.watermark WHERE resource = %s", (resource,)
    ).fetchone()
    return row[0].isoformat() if row else "2020-01-01T00:00:00+00:00"


def set_watermark(conn, resource: str, value: str) -> None:
    conn.execute(
        """INSERT INTO ops.watermark (resource, last_value) VALUES (%s, %s)
           ON CONFLICT (resource) DO UPDATE SET last_value = EXCLUDED.last_value, updated_at = now()""",
        (resource, value),
    )
