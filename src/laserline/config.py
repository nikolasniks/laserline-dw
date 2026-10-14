"""Settings loaded from env (.env locally, Lambda env / Secrets Manager in AWS)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # not installed in the lambda layer, that's fine
    pass


def _env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.getenv(name, default)
    if required and not val:
        raise RuntimeError(f"missing required env var: {name}")
    return val or ""


@dataclass(frozen=True)
class Settings:
    calcme_base_url: str
    calcme_token: str
    calcme_timeout: int
    calcme_page_size: int
    pg_dsn: str
    reports_bucket: str
    aws_region: str
    log_level: str


def _db_dsn() -> str:
    """Prefer Secrets Manager when DB_SECRET_ARN is set (prod), else plain PG* vars."""
    arn = os.getenv("DB_SECRET_ARN")
    if arn:
        import boto3

        sm = boto3.client("secretsmanager")
        s = json.loads(sm.get_secret_value(SecretId=arn)["SecretString"])
        return (
            f"host={s['host']} port={s.get('port', 5432)} dbname={s['dbname']} "
            f"user={s['username']} password={s['password']} sslmode=require"
        )
    return (
        f"host={_env('PGHOST', required=True)} port={_env('PGPORT', '5432')} "
        f"dbname={_env('PGDATABASE', required=True)} user={_env('PGUSER', required=True)} "
        f"password={_env('PGPASSWORD', required=True)} sslmode={_env('PGSSLMODE', 'require')}"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings(
        calcme_base_url=_env("CALCME_BASE_URL", required=True).rstrip("/"),
        calcme_token=_env("CALCME_API_TOKEN", required=True),
        calcme_timeout=int(_env("CALCME_TIMEOUT_SECONDS", "30")),
        calcme_page_size=int(_env("CALCME_PAGE_SIZE", "100")),
        pg_dsn=_db_dsn(),
        reports_bucket=_env("REPORTS_BUCKET", "laserline-dw-reports"),
        aws_region=_env("AWS_REGION", "sa-east-1"),
        log_level=_env("LOG_LEVEL", "INFO"),
    )
