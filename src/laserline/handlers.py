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
