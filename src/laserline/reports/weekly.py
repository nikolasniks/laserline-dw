"""Weekly report: runs every Friday, dumps KPIs as JSON + CSV into S3.

Layout in the bucket:
    reports/weekly/YYYY/WW/summary.json
    reports/weekly/YYYY/WW/top_customers.csv
    reports/weekly/YYYY/WW/top_products.csv
"""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date, timedelta
from decimal import Decimal

import boto3

from .. import db
from ..config import get_settings

log = logging.getLogger(__name__)


def _default(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, date):
        return o.isoformat()
    raise TypeError(type(o))


def _week_window(today: date | None = None) -> tuple[date, date]:
    """Monday..Friday of the current week."""
    today = today or date.today()
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=4)


def _rows_to_csv(cols, rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def build(conn, start: date, end: date) -> dict:
    kpi = conn.execute(
        """SELECT COUNT(DISTINCT f.order_id), COALESCE(SUM(f.line_total),0),
                  COALESCE(SUM(f.area_m2 * f.quantity),0)
             FROM dw.fact_order_line f JOIN dw.dim_date d ON d.date_key = f.order_date_key
            WHERE d.full_date BETWEEN %s AND %s""",
        (start, end),
    ).fetchone()
    prev = conn.execute(
        """SELECT COALESCE(SUM(f.line_total),0)
             FROM dw.fact_order_line f JOIN dw.dim_date d ON d.date_key = f.order_date_key
            WHERE d.full_date BETWEEN %s AND %s""",
        (start - timedelta(days=7), end - timedelta(days=7)),
    ).fetchone()[0]
    cash = conn.execute("SELECT side, open_amount, overdue FROM dw.v_cash_position").fetchall()

    orders, revenue, area = kpi
    wow = float((revenue - prev) / prev * 100) if prev else None
    return {
        "week_start": start, "week_end": end,
        "orders": orders, "revenue": revenue, "area_m2": area,
        "avg_ticket": (revenue / orders) if orders else 0,
        "revenue_wow_pct": round(wow, 1) if wow is not None else None,
        "cash": {s: {"open": o, "overdue": ov} for s, o, ov in cash},
    }


def run(today: date | None = None) -> dict:
    s = get_settings()
    start, end = _week_window(today)
    year, week, _ = start.isocalendar()
    prefix = f"reports/weekly/{year}/{week:02d}"
    s3 = boto3.client("s3", region_name=s.aws_region)

    with db.connect() as conn:
        run_id = db.start_run(conn, "weekly_report")
        try:
            summary = build(conn, start, end)
            s3.put_object(Bucket=s.reports_bucket, Key=f"{prefix}/summary.json",
                          Body=json.dumps(summary, default=_default, indent=2).encode(),
                          ContentType="application/json")
            for name, view in (("top_customers", "v_top_customers_90d"),
                               ("top_products", "v_top_products_90d")):
                cur = conn.execute(f"SELECT * FROM dw.{view} LIMIT 20")
                cols = [c.name for c in cur.description]
                s3.put_object(Bucket=s.reports_bucket, Key=f"{prefix}/{name}.csv",
                              Body=_rows_to_csv(cols, cur.fetchall()), ContentType="text/csv")
            db.finish_run(conn, run_id, rows_out=3)
        except Exception as e:  # noqa: BLE001
            conn.rollback()  # an aborted transaction would make finish_run fail and hide the real error
            db.finish_run(conn, run_id, status="failed", error=str(e))
            raise
    log.info("weekly report saved to s3://%s/%s", s.reports_bucket, prefix)
    return {"bucket": s.reports_bucket, "prefix": prefix}
