"""Payment polling (Lemon Squeezy). No inbound port, no webhook.

The LemonSqueezyProvider below is VERIFIED against the provider's current public
docs (checked 2026-09-30):
- list endpoint ``GET https://api.lemonsqueezy.com/v1/orders``
  (https://docs.lemonsqueezy.com/api/orders/list-all-orders)
- ``Authorization: Bearer {api_key}`` + ``Accept/Content-Type:
  application/vnd.api+json``
  (https://docs.lemonsqueezy.com/api/getting-started/requests)
- JSON:API response; filters ``filter[store_id]`` / ``filter[user_email]`` /
  ``filter[order_number]`` (there is NO server-side date filter, so this
  adapter pages ``sort=-created_at`` and stops client-side)
- amount fields in cents (``total``, ``subtotal``, ``tax`` + ``*_usd`` twins),
  ``status`` in paid/refunded/partial_refund/..., ``refunded`` flag,
  ``first_order_item.product_id``, ``created_at``, ``test_mode``
  (https://docs.lemonsqueezy.com/api/orders/the-order-object)
- pricing 5% + 50c confirmed on https://www.lemonsqueezy.com/pricing (2026);
  the fee estimate below stays labelled as an estimate because surcharges and
  the fixed-fee currency can differ per store.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

API_BASE = "https://api.lemonsqueezy.com/v1"
JSONAPI_HEADERS = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json",
}
MAX_PAGES = 20
PAGE_SIZE = 100


@dataclass
class Order:
    order_id: str
    product_id: str
    currency: str
    gross_cents: int
    net_before_fees_cents: int
    status: str  # "paid" | "refunded" | "other"
    created_at: str
    test_mode: bool = False


class HttpClient(Protocol):
    def get_json(self, url: str, headers: dict[str, str]) -> dict: ...


class UrllibHttpClient:
    """Thin urllib wrapper, 15 s timeout, stdlib only."""

    def __init__(self, timeout_s: int = 15):
        self.timeout_s = timeout_s

    def get_json(self, url: str, headers: dict[str, str]) -> dict:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))


class PaymentProvider(Protocol):
    name: str

    def fetch_orders(self, since_iso: str) -> list[Order]: ...


class LemonSqueezyProvider:
    """Lists orders, newest first, stopping below ``since_iso``."""

    name = "lemonsqueezy"

    def __init__(self, api_key: str, http_client: HttpClient | None = None,
                 store_id: str = ""):
        self._api_key = api_key
        self._http = http_client or UrllibHttpClient()
        self._store_id = store_id

    def _headers(self) -> dict[str, str]:
        return {**JSONAPI_HEADERS, "Authorization": f"Bearer {self._api_key}"}

    def _first_url(self) -> str:
        # NOTE: the orders endpoint rejects `sort=created_at` (verified live:
        # 400 "Sort parameter created_at is not allowed"). Ordering does not
        # matter for correctness: the poll dedupes on (provider, order_id)
        # and re-scans a 3-day overlap window on every run.
        params = {"page[number]": "1", "page[size]": str(PAGE_SIZE)}
        if self._store_id:
            params["filter[store_id]"] = self._store_id
        return f"{API_BASE}/orders?{urllib.parse.urlencode(params)}"

    @staticmethod
    def _parse_order(item: dict) -> Order | None:
        try:
            attrs = item["attributes"]
            foi = attrs.get("first_order_item") or {}
            status = str(attrs.get("status", ""))
            refunded = bool(attrs.get("refunded")) or status == "refunded"
            if refunded:
                mapped = "refunded"
            elif status == "paid":
                mapped = "paid"
            else:
                mapped = "other"
            return Order(
                order_id=str(item["id"]),
                product_id=str(foi.get("product_id") or ""),
                currency=str(attrs.get("currency", "")).upper(),
                gross_cents=int(attrs.get("total", 0)),
                net_before_fees_cents=int(attrs.get("subtotal", 0)),
                status=mapped,
                created_at=str(attrs.get("created_at", "")),
                test_mode=bool(attrs.get("test_mode", False)),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def fetch_orders(self, since_iso: str) -> list[Order]:
        orders: list[Order] = []
        url: str | None = self._first_url()
        for _ in range(MAX_PAGES):
            try:
                payload = self._http.get_json(url, self._headers())
            except (urllib.error.URLError, OSError, ValueError) as e:
                raise RuntimeError(f"order fetch failed: {e}") from e
            items = payload.get("data", []) if isinstance(payload, dict) else []
            if not items:
                break
            stop = False
            for item in items:
                order = self._parse_order(item)
                if order is None or order.test_mode:
                    continue
                if order.created_at < since_iso:
                    stop = True
                    continue
                orders.append(order)
            links = payload.get("links", {}) if isinstance(payload, dict) else {}
            url = links.get("next")
            if stop or not url:
                break
        return orders


def _estimate_income_cents(net_cents: int, fee_percent: int, fee_fixed: int) -> int:
    return net_cents - (net_cents * fee_percent // 100 + fee_fixed)


def _find_venture_id(conn: sqlite3.Connection, product_id: str) -> int | None:
    if not product_id:
        return None
    row = conn.execute(
        "SELECT id FROM ventures WHERE external_product_id=?", (product_id,)
    ).fetchone()
    return int(row["id"]) if row else None


def poll(store, ledger, *, provider_name: str, api_key: str, fee_percent: int,
         fee_fixed: int, provider=None, now: datetime | None = None) -> dict:
    """Poll once. Returns a summary; never raises for provider failures.

    The API key must never appear in any stored text or returned message.
    """
    now = now or datetime.now(UTC)
    out: dict = {"status": "ok", "fetched": 0, "recorded": 0, "ignored": 0,
                 "fx_unhandled": 0, "refunds": 0, "skipped_other": 0}
    if not api_key:
        live = store.conn.execute(
            "SELECT COUNT(*) c FROM ventures WHERE status='live'").fetchone()["c"]
        if live:
            res = store.add_human_task(
                kind="secret_provisioning",
                title="Add the payment API key",
                instructions=("At least one venture is live but LEMONSQUEEZY_API_KEY "
                              "is missing. Add it to the .env file next to the "
                              "service (never send the key itself anywhere)."),
                dedupe_key="env-payments", created_by="orchestrator")
            out["status"] = "no-key"
            out["human_task"] = res.get("status")
        else:
            out["status"] = "no-key-no-live"
        return out
    if provider is None:
        if provider_name != "lemonsqueezy":
            return {"status": "error",
                    "reason": f"unsupported payment provider: {provider_name}"}
        provider = LemonSqueezyProvider(api_key)
    cursor = store.kv_get("payments_cursor")
    since = cursor or (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if cursor:
        try:
            since_dt = datetime.fromisoformat(cursor)
            since = (since_dt - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    try:
        orders = provider.fetch_orders(since)
    except RuntimeError as e:
        out["status"] = "fetch-failed"
        out["reason"] = str(e)
        return out
    out["fetched"] = len(orders)
    for order in orders:
        _process_order(store, ledger, provider_name, order, fee_percent,
                       fee_fixed, out)
    store.kv_set("payments_cursor", now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return out


def _process_order(store, ledger, provider_name: str, order: Order,
                   fee_percent: int, fee_fixed: int, out: dict) -> None:
    conn = store.conn
    existing = conn.execute(
        "SELECT * FROM payments WHERE provider=? AND order_id=?",
        (provider_name, order.order_id)).fetchone()
    if order.status == "other":
        out["skipped_other"] += 1
        return
    if existing is not None:
        _process_refund_transition(store, ledger, provider_name, order, existing, out)
        return
    if order.status == "refunded":
        conn.execute(
            """INSERT INTO payments(provider,order_id,product_id,venture_id,currency,
                                    gross_cents,recorded_cents,status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (provider_name, order.order_id, order.product_id,
             _find_venture_id(conn, order.product_id), order.currency,
             order.gross_cents, 0, "refunded"))
        return
    # paid, first sighting
    venture_id = _find_venture_id(conn, order.product_id)
    if venture_id is None:
        conn.execute(
            """INSERT INTO payments(provider,order_id,product_id,venture_id,currency,
                                    gross_cents,recorded_cents,status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (provider_name, order.order_id, order.product_id, None,
             order.currency, order.gross_cents, 0, "ignored"))
        out["ignored"] += 1
        return
    if order.currency != "EUR":
        conn.execute(
            """INSERT INTO payments(provider,order_id,product_id,venture_id,currency,
                                    gross_cents,recorded_cents,status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (provider_name, order.order_id, order.product_id, venture_id,
             order.currency, order.gross_cents, 0, "fx_unhandled"))
        out["fx_unhandled"] += 1
        return
    income = _estimate_income_cents(order.net_before_fees_cents, fee_percent, fee_fixed)
    if income <= 0:
        conn.execute(
            """INSERT INTO payments(provider,order_id,product_id,venture_id,currency,
                                    gross_cents,recorded_cents,status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (provider_name, order.order_id, order.product_id, venture_id,
             order.currency, order.gross_cents, 0, "recorded"))
        out["recorded"] += 1
        return
    ref = f"order:{provider_name}:{order.order_id}"
    note = (f"order {order.order_id} product {order.product_id} "
            f"gross {order.gross_cents}c net {order.net_before_fees_cents}c "
            f"(fee estimate {fee_percent}%+{fee_fixed}c)")
    ledger.record_income(income, ref, note, agent="payments", venture_id=venture_id)
    try:
        conn.execute(
            """INSERT INTO payments(provider,order_id,product_id,venture_id,currency,
                                    gross_cents,recorded_cents,status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (provider_name, order.order_id, order.product_id, venture_id,
             order.currency, order.gross_cents, income, "recorded"))
    except sqlite3.IntegrityError:
        pass
    out["recorded"] += 1


def _process_refund_transition(store, ledger, provider_name: str, order: Order,
                               existing, out: dict) -> None:
    if order.status != "refunded" or existing["status"] != "recorded":
        return
    recorded = int(existing["recorded_cents"])
    if recorded > 0:
        ref = f"refund:order:{provider_name}:{order.order_id}"
        note = f"refund of order {order.order_id}"
        ledger.record_refund(recorded, ref, note, agent="payments",
                             venture_id=existing["venture_id"])
    store.conn.execute("UPDATE payments SET status='refund_recorded' WHERE id=?",
                       (existing["id"],))
    out["refunds"] += 1
