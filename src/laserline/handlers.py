"""AWS Lambda entrypoints. EventBridge fires these on a schedule (see infra/template.yaml)."""
from __future__ import annotations

import logging
import os

logging.getLogger().setLevel(os.getenv("LOG_LEVEL", "INFO"))


def sync_handler(event, context):
    """Hourly: extract + transform."""
    from .etl import extract, transform

    resources = (event or {}).get("resources")  # optional: run just a subset
    e = extract.run(resources)
    t = transform.run()
    return {"extract": e, "transform": t}


def weekly_report_handler(event, context):
    """Fridays: build the weekly report and drop it in S3."""
    from .reports import weekly

    return weekly.run()


def daily_audit_handler(event, context):
    """Every morning: check Calcme and e-mail what needs attention."""
    from .audit import daily
    from .connector.orders import load_rules

    return daily.run(statement_rules=load_rules().get("statement", []))
