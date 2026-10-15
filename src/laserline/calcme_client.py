"""Thin wrapper around the Calcme REST API.

Nothing fancy: auth header, pagination, retries with backoff on 429/5xx.
Resource paths live in RESOURCES so if Calcme renames an endpoint it's a one-line fix.
"""
from __future__ import annotations

import logging
from typing import Any, Iterator

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import get_settings

log = logging.getLogger(__name__)

# logical name -> API path. Adjust to whatever your Calcme account exposes.
RESOURCES: dict[str, str] = {
    "clientes": "/clientes",
    "produtos": "/produtos",
    "materiais": "/materiais",
    "fornecedores": "/fornecedores",
    "vendedores": "/vendedores",
    "status": "/status",
    "pedidos": "/pedidos",
    "compras": "/compras",
    "contas_receber": "/contas-receber",
    "contas_pagar": "/contas-pagar",
}


class CalcmeError(RuntimeError):
    pass


class _Retryable(CalcmeError):
    pass


class CalcmeClient:
    def __init__(self, base_url: str | None = None, token: str | None = None,
                 timeout: int | None = None, page_size: int | None = None):
        s = get_settings() if not (base_url and token) else None
        self.base_url = (base_url or s.calcme_base_url).rstrip("/")
        self.timeout = timeout or (s.calcme_timeout if s else 30)
        self.page_size = page_size or (s.calcme_page_size if s else 100)
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token or s.calcme_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "laserline-dw/0.1",
        })

    # ---------- low level ----------
    @retry(
        retry=retry_if_exception_type(_Retryable),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _request(self, method: str, path: str, **kw) -> Any:
        url = f"{self.base_url}{path}"
        resp = self.session.request(method, url, timeout=self.timeout, **kw)
        # 429 means the request was rejected before running, so it is always safe to retry.
        # A 5xx on POST may already have created the record: retrying would duplicate
        # orders/bills, so only idempotent methods (GET, PUT) retry on 5xx.
        if resp.status_code == 429 or (resp.status_code >= 500 and method in ("GET", "PUT")):
            log.warning("calcme %s %s -> %s, backing off", method, path, resp.status_code)
            raise _Retryable(f"{resp.status_code} on {path}")
        if not resp.ok:
            # don't log the body, it can carry customer data
            raise CalcmeError(f"{method} {path} failed: HTTP {resp.status_code}")
        return resp.json() if resp.content else None

    def get(self, path: str, **params) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, body: dict) -> Any:
        return self._request("POST", path, json=body)

    def put(self, path: str, body: dict) -> Any:
        return self._request("PUT", path, json=body)

    # ---------- high level ----------
    def iter_resource(self, resource: str, updated_since: str | None = None) -> Iterator[dict]:
        """Yield every record of a resource, walking pages until the API runs dry."""
        path = RESOURCES[resource]
        page = 1
        while True:
            params = {"page": page, "per_page": self.page_size}
            if updated_since:
                params["updated_since"] = updated_since
            data = self.get(path, **params)
            items = data.get("data", data) if isinstance(data, dict) else data
            if not items:
                break
            yield from items
            if len(items) < self.page_size:
                break
            page += 1

    def get_one(self, resource: str, record_id: str | int) -> dict:
        return self.get(f"{RESOURCES[resource]}/{record_id}")

    def create(self, resource: str, body: dict) -> dict:
        return self.post(RESOURCES[resource], body)

    def update(self, resource: str, record_id: str | int, body: dict) -> dict:
        return self.put(f"{RESOURCES[resource]}/{record_id}", body)
