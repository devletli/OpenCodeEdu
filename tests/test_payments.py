from datetime import UTC, datetime

import pytest

from kiraci.config import Config
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.payments import LemonSqueezyProvider, Order, poll
from kiraci.runner import OpencodeRunner
from kiraci.store import Store


def paid(order_id, product="prod_5", currency="EUR", gross=1199, net=999,
         created="2026-09-20T10:00:00.000000Z"):
    return Order(order_id=order_id, product_id=product, currency=currency,
                 gross_cents=gross, net_before_fees_cents=net,
                 status="paid", created_at=created)


class FakeProvider:
    name = "testpay"

    def __init__(self, orders):
        self.orders = list(orders)
        self.since_seen = []

    def fetch_orders(self, since_iso):
        self.since_seen.append(since_iso)
        return [o for o in self.orders if o.created_at >= since_iso]


#: Fixed "now" so the 3-day overlap window covers the fixture orders.
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)

BASE_KW = {"provider_name": "testpay", "api_key": "k", "fee_percent": 5,
           "fee_fixed": 50, "now": NOW}


@pytest.fixture
def wired():
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    store = Store(conn)
    conn.execute(
        """INSERT INTO ventures(name,slug,kind,hypothesis,score,evidence,
                                status,external_product_id)
           VALUES ('Gadget','gadget','digital_product','Sells.',8.0,'[]',
                   'live','prod_5')""")
    return store, ledger


def test_paid_eur_recorded_with_fee_and_split(wired):
    store, ledger = wired
    out = poll(store, ledger, provider=FakeProvider([paid("o1")]), **BASE_KW)
    assert out["status"] == "ok" and out["recorded"] == 1
    # net 999 - (999*5//100 + 50) = 999 - 99 = 900 -> 450/270/180
    row = store.conn.execute(
        "SELECT * FROM payments WHERE order_id='o1'").fetchone()
    assert row["status"] == "recorded" and row["recorded_cents"] == 900
    assert row["venture_id"] == 1
    parts = {r["bucket"]: r["s"] for r in store.conn.execute(
        "SELECT bucket, SUM(delta_cents) s FROM ledger"
        " WHERE ref LIKE 'order:testpay:o1:%' GROUP BY bucket")}
    assert parts == {"experiment": 450, "emergency": 270, "owner": 180}


def test_same_order_twice_records_once(wired):
    store, ledger = wired
    provider = FakeProvider([paid("o1")])
    kw = {"provider": provider, **BASE_KW}
    poll(store, ledger, **kw)
    out = poll(store, ledger, **kw)
    assert out["recorded"] == 0  # already handled: nothing new, no duplicate
    n = store.conn.execute(
        "SELECT COUNT(*) c FROM payments WHERE order_id='o1'").fetchone()["c"]
    assert n == 1
    n = store.conn.execute(
        "SELECT COUNT(*) c FROM ledger WHERE ref LIKE 'order:testpay:o1:%'"
    ).fetchone()["c"]
    assert n == 3


def test_non_eur_is_fx_unhandled(wired):
    store, ledger = wired
    out = poll(store, ledger, provider=FakeProvider([paid("o2", currency="USD")]),
               **BASE_KW)
    assert out["fx_unhandled"] == 1
    row = store.conn.execute(
        "SELECT status FROM payments WHERE order_id='o2'").fetchone()
    assert row["status"] == "fx_unhandled"
    n = store.conn.execute(
        "SELECT COUNT(*) c FROM ledger WHERE kind='income'").fetchone()["c"]
    assert n == 0


def test_unmapped_product_ignored(wired):
    store, ledger = wired
    out = poll(store, ledger,
               provider=FakeProvider([paid("o3", product="prod_999")]), **BASE_KW)
    assert out["ignored"] == 1
    n = store.conn.execute(
        "SELECT COUNT(*) c FROM ledger WHERE kind='income'").fetchone()["c"]
    assert n == 0


def test_refund_creates_mirrored_entries_once(wired):
    store, ledger = wired
    provider = FakeProvider([paid("o4")])
    kw = {"provider": provider, **BASE_KW}
    poll(store, ledger, **kw)
    provider.orders = [Order(order_id="o4", product_id="prod_5", currency="EUR",
                             gross_cents=1199, net_before_fees_cents=999,
                             status="refunded",
                             created_at="2026-09-20T10:00:00.000000Z")]
    out = poll(store, ledger, **kw)
    assert out["refunds"] == 1
    kinds = [r["kind"] for r in store.conn.execute(
        "SELECT kind FROM ledger WHERE ref LIKE 'refund:order:testpay:o4:%'"
        " ORDER BY id")]
    assert kinds == ["refund", "refund", "refund"]
    row = store.conn.execute(
        "SELECT status FROM payments WHERE order_id='o4'").fetchone()
    assert row["status"] == "refund_recorded"
    out = poll(store, ledger, **kw)
    n = store.conn.execute(
        "SELECT COUNT(*) c FROM ledger WHERE ref LIKE 'refund:order:testpay:o4:%'"
    ).fetchone()["c"]
    assert n == 3


def test_cursor_overlap_window(wired):
    store, ledger = wired
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    provider = FakeProvider([])
    poll(store, ledger, provider_name="testpay", api_key="k", fee_percent=5,
         fee_fixed=50, provider=provider, now=now)
    assert store.kv_get("payments_cursor") == "2026-09-30T12:00:00Z"
    poll(store, ledger, provider_name="testpay", api_key="k", fee_percent=5,
         fee_fixed=50, provider=provider, now=now)
    assert provider.since_seen[-1] == "2026-09-27T12:00:00Z"  # 3-day overlap


def test_missing_key_creates_one_task_only_when_live(wired):
    store, ledger = wired
    out = poll(store, ledger, provider_name="testpay", api_key="",
               fee_percent=5, fee_fixed=50, provider=FakeProvider([]))
    out2 = poll(store, ledger, provider_name="testpay", api_key="",
                fee_percent=5, fee_fixed=50, provider=FakeProvider([]))
    assert out["status"] == "no-key" and out2["status"] == "no-key"
    tasks = [t for t in store.list_human_tasks("open")
             if t["dedupe_key"] == "env-payments"]
    assert len(tasks) == 1


def test_missing_key_quiet_without_live():
    conn = connect(":memory:")
    store = Store(conn)
    out = poll(store, Ledger(conn), provider_name="testpay", api_key="",
               fee_percent=5, fee_fixed=50, provider=FakeProvider([]))
    assert out["status"] == "no-key-no-live"
    assert store.list_human_tasks("open") == []


def test_key_never_in_stored_texts_or_agent_env(wired, tmp_path, monkeypatch):
    store, ledger = wired
    monkeypatch.setenv("LEMONSQUEEZY_API_KEY", "sk-live-SECRETKEY123")
    config = Config(models={"scout": "cheap"}, costs={}, limits={})
    runner = OpencodeRunner(ledger=ledger, store=store, config=config)
    assert "LEMONSQUEEZY_API_KEY" not in runner._child_env()
    poll(store, ledger, provider_name="testpay", api_key="sk-live-SECRETKEY123",
         fee_percent=5, fee_fixed=50, now=NOW,
         provider=FakeProvider([paid("o9")]))
    texts = []
    for tbl, col in (("ledger", "note"), ("ledger", "ref"), ("payments", "order_id"),
                     ("human_tasks", "title"), ("human_tasks", "instructions"),
                     ("runs", "model")):
        texts += [r[col] or "" for r in
                  store.conn.execute(f"SELECT {col} FROM {tbl}")]
    assert not any("sk-live-SECRETKEY123" in t for t in texts)


LS_PAGE = {
    "data": [
        {"id": "11", "type": "orders",
         "attributes": {"store_id": 1, "currency": "eur", "subtotal": 999,
                        "total": 1199, "status": "paid", "refunded": False,
                        "refunded_at": None,
                        "first_order_item": {"product_id": 5},
                        "created_at": "2026-09-20T10:00:00.000000Z",
                        "test_mode": False}},
        {"id": "12", "type": "orders",
         "attributes": {"store_id": 1, "currency": "EUR", "subtotal": 500,
                        "total": 600, "status": "refunded", "refunded": True,
                        "refunded_at": "2026-09-21T10:00:00.000000Z",
                        "first_order_item": {"product_id": 5},
                        "created_at": "2026-09-21T10:00:00.000000Z",
                        "test_mode": False}},
        {"id": "13", "type": "orders",
         "attributes": {"store_id": 1, "currency": "EUR", "subtotal": 500,
                        "total": 600, "status": "paid", "refunded": False,
                        "refunded_at": None,
                        "first_order_item": {"product_id": 5},
                        "created_at": "2020-01-01T00:00:00.000000Z",
                        "test_mode": False}},
        {"id": "14", "type": "orders",
         "attributes": {"store_id": 1, "currency": "EUR", "subtotal": 500,
                        "total": 600, "status": "paid", "refunded": False,
                        "refunded_at": None,
                        "first_order_item": {"product_id": 5},
                        "created_at": "2026-09-22T10:00:00.000000Z",
                        "test_mode": True}},
    ],
    "links": {},
}


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, headers):
        self.calls.append((url, headers))
        return self.payload


def test_lemonsqueezy_adapter_parses_docs_shaped_payload():
    http = FakeHttp(LS_PAGE)
    provider = LemonSqueezyProvider("k", http_client=http, store_id="1")
    orders = provider.fetch_orders("2026-09-01T00:00:00Z")
    assert "filter%5Bstore_id%5D=1" in http.calls[0][0] or "filter[store_id]=1" in \
        http.calls[0][0]
    assert http.calls[0][1]["Authorization"] == "Bearer k"
    by_id = {o.order_id: o for o in orders}
    assert set(by_id) == {"11", "12"}  # old + test_mode excluded
    assert by_id["11"].status == "paid" and by_id["11"].gross_cents == 1199
    assert by_id["11"].net_before_fees_cents == 999
    assert by_id["11"].currency == "EUR" and by_id["11"].product_id == "5"
    assert by_id["12"].status == "refunded"
