"""Transform step: staging.latest_records -> dw (dims as SCD2, facts as upserts).

Field names below follow what the Calcme payload returns; if your account uses
different keys, tweak the FIELD maps and you're done.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime

from .. import db

log = logging.getLogger(__name__)

DIMS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)(?:\s*[xX]\s*(\d+(?:[.,]\d+)?))?")


# ---------------- helpers ----------------
def date_key(v) -> int | None:
    if not v:
        return None
    if isinstance(v, str):
        v = datetime.fromisoformat(v.replace("Z", "+00:00")).date()
    if isinstance(v, datetime):
        v = v.date()
    return int(v.strftime("%Y%m%d")) if isinstance(v, date) else None


def area_m2_from_text(text: str | None) -> float | None:
    """'20x14x8' (cm) -> footprint area in m². Uses the first two numbers."""
    if not text:
        return None
    m = DIMS_RE.search(text)
    if not m:
        return None
    w, h = (float(x.replace(",", ".")) for x in m.group(1, 2))
    return round((w * h) / 10_000, 4)


def row_hash(*vals) -> str:
    return hashlib.md5("|".join("" if v is None else str(v) for v in vals).encode()).hexdigest()


def _latest(conn, resource: str):
    return conn.execute(
        "SELECT payload FROM staging.latest_records WHERE resource = %s", (resource,)
    ).fetchall()


# ---------------- SCD2 dims ----------------
def _scd2(conn, table, nk_col, nk, cols: dict) -> None:
    h = row_hash(*cols.values())
    cur = conn.execute(
        f"SELECT row_hash FROM dw.{table} WHERE {nk_col} = %s AND is_current", (nk,)
    ).fetchone()
    if cur and cur[0] == h:
        return
    if cur:
        conn.execute(
            f"UPDATE dw.{table} SET is_current = FALSE, valid_to = now() "
            f"WHERE {nk_col} = %s AND is_current", (nk,),
        )
    names = ", ".join([nk_col, *cols.keys(), "row_hash"])
    ph = ", ".join(["%s"] * (len(cols) + 2))
    conn.execute(f"INSERT INTO dw.{table} ({names}) VALUES ({ph})", (nk, *cols.values(), h))


def load_customers(conn) -> int:
    rows = _latest(conn, "clientes")
    for (p,) in rows:
        _scd2(conn, "dim_customer", "customer_id", str(p["id"]), {
            "name": p.get("nome"),
            "doc_type": "PJ" if len(re.sub(r"\D", "", p.get("documento") or "")) == 14 else "PF",
            "city": p.get("cidade"),
            "state": (p.get("uf") or "")[:2] or None,
            "segment": p.get("segmento"),
        })
    return len(rows)


def load_products(conn) -> int:
    rows = _latest(conn, "produtos")
    for (p,) in rows:
        _scd2(conn, "dim_product", "product_id", str(p["id"]), {
            "name": p.get("nome"),
            "category": p.get("categoria"),
            "unit": p.get("unidade"),
            "list_price": p.get("preco"),
            "is_simple": p.get("tipo") == "simples",
        })
    return len(rows)


def _upsert_simple(conn, resource, table, nk_col, cols_fn) -> int:
    rows = _latest(conn, resource)
    for (p,) in rows:
        cols = cols_fn(p)
        names = ", ".join([nk_col, *cols.keys()])
        ph = ", ".join(["%s"] * (len(cols) + 1))
        upd = ", ".join(f"{k} = EXCLUDED.{k}" for k in cols)
        conn.execute(
            f"INSERT INTO dw.{table} ({names}) VALUES ({ph}) "
            f"ON CONFLICT ({nk_col}) DO UPDATE SET {upd}",
            (str(p["id"]), *cols.values()),
        )
    return len(rows)


def load_small_dims(conn) -> int:
    n = 0
    n += _upsert_simple(conn, "vendedores", "dim_seller", "seller_id",
                        lambda p: {"name": p.get("nome"), "active": p.get("ativo", True)})
    n += _upsert_simple(conn, "fornecedores", "dim_supplier", "supplier_id",
                        lambda p: {"name": p.get("nome"), "city": p.get("cidade"),
                                   "state": (p.get("uf") or "")[:2] or None})
    n += _upsert_simple(conn, "materiais", "dim_material", "material_id",
                        lambda p: {"name": p.get("nome"), "thickness_mm": p.get("espessura"),
                                   "unit": p.get("unidade")})
    n += _upsert_simple(conn, "status", "dim_status", "status_id",
                        lambda p: {"description": p.get("descricao"),
                                   "is_final": p.get("finalizado", False)})
    return n


# ---------------- facts ----------------
def _sk(conn, table, sk, nk_col, nk) -> int:
    if nk is None:
        return -1
    extra = " AND is_current" if table in ("dim_customer", "dim_product") else ""
    r = conn.execute(
        f"SELECT {sk} FROM dw.{table} WHERE {nk_col} = %s{extra}", (str(nk),)
    ).fetchone()
    return r[0] if r else -1


def load_order_lines(conn) -> int:
    rows = _latest(conn, "pedidos")
    n = 0
    for (o,) in rows:
        cust = _sk(conn, "dim_customer", "customer_sk", "customer_id", o.get("cliente_id"))
        seller = _sk(conn, "dim_seller", "seller_sk", "seller_id", o.get("vendedor_id"))
        status = _sk(conn, "dim_status", "status_sk", "status_id", o.get("status_id"))
        for i, it in enumerate(o.get("itens", []), start=1):
            qty = float(it.get("quantidade") or 0)
            price = float(it.get("valor_unitario") or 0)
            disc = float(it.get("desconto") or 0)
            conn.execute(
                """INSERT INTO dw.fact_order_line
                     (order_id, line_no, order_date_key, due_date_key, customer_sk, product_sk,
                      seller_sk, status_sk, quantity, unit_price, discount, line_total, area_m2)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (order_id, line_no) DO UPDATE SET
                     status_sk = EXCLUDED.status_sk, quantity = EXCLUDED.quantity,
                     unit_price = EXCLUDED.unit_price, discount = EXCLUDED.discount,
                     line_total = EXCLUDED.line_total, area_m2 = EXCLUDED.area_m2,
                     loaded_at = now()""",
                (str(o["id"]), i, date_key(o.get("data")), date_key(o.get("data_entrega")),
                 cust, _sk(conn, "dim_product", "product_sk", "product_id", it.get("produto_id")),
                 seller, status, qty, price, disc, round(qty * price - disc, 2),
                 area_m2_from_text(it.get("descricao"))),
            )
            n += 1
    return n


def _load_installments(conn, resource, table, id_col, party_col, party_dim, party_sk, party_nk,
                       party_key, ref_col, ref_key) -> int:
    rows = _latest(conn, resource)
    for (r,) in rows:
        # the bills endpoint returns valorConta / liquidado / dataVencimento (same names the
        # connector writes back); older payloads used valor / valor_pago / vencimento.
        amount = float(r.get("valorConta") or r.get("valor") or 0)
        settled = r.get("liquidado")
        if settled is not None:
            paid = amount if settled else float(r.get("valor_pago") or 0)
        else:
            paid = float(r.get("valor_pago") or 0)
        issue = r.get("dataCompetencia") or r.get("emissao")
        due = r.get("dataVencimento") or r.get("vencimento")
        paid_on = r.get("dataLiquidacao") or r.get("dataPagamento") or r.get("pagamento")
        conn.execute(
            f"""INSERT INTO dw.{table}
                  ({id_col}, {ref_col}, {party_col}, issue_date_key, due_date_key, paid_date_key,
                   amount, amount_paid, is_paid)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT ({id_col}) DO UPDATE SET
                  paid_date_key = EXCLUDED.paid_date_key, amount = EXCLUDED.amount,
                  amount_paid = EXCLUDED.amount_paid, is_paid = EXCLUDED.is_paid, loaded_at = now()""",
            (str(r["id"]), r.get(ref_key),
             _sk(conn, party_dim, party_sk, party_nk, r.get(party_key) or r.get("personId")),
             date_key(issue), date_key(due), date_key(paid_on),
             amount, paid, bool(settled) if settled is not None else paid >= amount > 0),
        )
    return len(rows)


def load_finance(conn) -> int:
    n = _load_installments(conn, "contas_receber", "fact_receivable", "receivable_id",
                           "customer_sk", "dim_customer", "customer_sk", "customer_id",
                           "cliente_id", "order_id", "pedido_id")
    n += _load_installments(conn, "contas_pagar", "fact_payable", "payable_id",
                            "supplier_sk", "dim_supplier", "supplier_sk", "supplier_id",
                            "fornecedor_id", "purchase_id", "compra_id")
    return n


def snapshot_open_orders(conn) -> None:
    conn.execute(
        """INSERT INTO dw.fact_order_snapshot (snapshot_date_key, status_sk, open_orders, open_amount)
           SELECT to_char(current_date, 'YYYYMMDD')::INT, f.status_sk,
                  COUNT(DISTINCT f.order_id), SUM(f.line_total)
             FROM dw.fact_order_line f
             JOIN dw.dim_status s ON s.status_sk = f.status_sk
            WHERE NOT COALESCE(s.is_final, FALSE)
            GROUP BY f.status_sk
           ON CONFLICT (snapshot_date_key, status_sk) DO UPDATE
             SET open_orders = EXCLUDED.open_orders, open_amount = EXCLUDED.open_amount"""
    )


def run() -> dict:
    with db.connect() as conn:
        run_id = db.start_run(conn, "transform")
        try:
            out = 0
            out += load_small_dims(conn)
            out += load_customers(conn)
            out += load_products(conn)
            out += load_order_lines(conn)
            out += load_finance(conn)
            snapshot_open_orders(conn)
            conn.commit()
            db.finish_run(conn, run_id, rows_out=out)
            log.info("transform done, %d rows touched", out)
            return {"run_id": str(run_id), "rows": out}
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            db.finish_run(conn, run_id, status="failed", error=str(e))
            raise
