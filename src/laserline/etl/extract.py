"""Extract step: pull each Calcme resource incrementally and land it raw in staging.

Idempotent by design: the (resource, source_id, payload_hash) unique index
means re-running the same window is a no-op.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from .. import db
from ..calcme_client import RESOURCES, CalcmeClient

log = logging.getLogger(__name__)

# dims first, facts after — keeps FK lookups happy in the transform step
EXTRACT_ORDER = [
    "status", "vendedores", "clientes", "produtos", "materiais", "fornecedores",
    "pedidos", "compras", "contas_receber", "contas_pagar",
]


def _hash(payload: dict) -> str:
    return hashlib.md5(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def extract_resource(conn, client: CalcmeClient, resource: str, run_id) -> int:
    since = db.get_watermark(conn, resource)
    started = datetime.now(timezone.utc).isoformat()
    n = 0
    with conn.cursor() as cur:
        for rec in client.iter_resource(resource, updated_since=since):
            source_id = str(rec.get("id") or rec.get("codigo"))
            cur.execute(
                """INSERT INTO staging.raw_records (resource, source_id, payload, payload_hash, run_id)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (resource, source_id, payload_hash) DO NOTHING""",
                (resource, source_id, Jsonb(rec), _hash(rec), run_id),
            )
            n += cur.rowcount
    db.set_watermark(conn, resource, started)
    conn.commit()
    log.info("extract %-15s +%d rows (since %s)", resource, n, since)
    return n


def run(resources: list[str] | None = None) -> dict:
    client = CalcmeClient()
    total = 0
    with db.connect() as conn:
        run_id = db.start_run(conn, "extract")
        try:
            for r in resources or EXTRACT_ORDER:
                if r not in RESOURCES:
                    log.warning("skipping unknown resource %s", r)
                    continue
                total += extract_resource(conn, client, r, run_id)
            db.finish_run(conn, run_id, rows_in=total)
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            db.finish_run(conn, run_id, status="failed", rows_in=total, error=str(e))
            raise
    return {"run_id": str(run_id), "rows": total}
