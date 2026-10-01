import math
from datetime import UTC, datetime

import pytest

from kiraci import usage
from kiraci.config import Config
from kiraci.db import connect
from kiraci.ledger import Ledger, Policy
from kiraci.store import Store


class FakeProbe:
    def __init__(self, cumulative: int, daily: int | None = None):
        self.cumulative = cumulative
        self.daily = daily

    def cumulative_spend_cents(self):
        return self.cumulative

    def daily_spend_cents(self):
        return self.daily


@pytest.fixture
def wired():
    conn = connect(":memory:")
    ledger = Ledger(conn, Policy(daily_caps_cents={}))
    ledger.init_genesis()
    return Store(conn), ledger


NOW = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)


def test_under_booked_usage_becomes_expense_idempotently(wired):
    store, ledger = wired
    probe = FakeProbe(cumulative=500)
    res = usage.reconcile(store, ledger, Config(), probe, NOW)
    assert res["status"] == "reconciled"
    assert res["delta"] == -500  # actual 500, booked 0 -> expense
    assert res["ref"] == "reconcile:2026-10-01:1"
    kinds = [r["kind"] for r in store.conn.execute(
        "SELECT kind FROM ledger WHERE ref LIKE 'reconcile:%'")]
    assert kinds == ["expense"]
    # idempotent: rerun with the same cumulative -> no second booking
    res2 = usage.reconcile(store, ledger, Config(), probe, NOW)
    assert res2["delta"] == 0 and res2["ref"] is None
    kinds = [r["kind"] for r in store.conn.execute(
        "SELECT kind FROM ledger WHERE ref LIKE 'reconcile:%'")]
    assert kinds == ["expense"]


def test_over_booked_usage_becomes_credit(wired):
    store, ledger = wired
    # a run was estimated at 300, provider only reports 200 total
    assert ledger.request_spend("scout", "tokens", 300, "run scout")[
        "status"] == "approved"
    probe = FakeProbe(cumulative=200)
    res = usage.reconcile(store, ledger, Config(), probe, NOW)
    assert res["delta"] == 100  # booked 300, actual 200 -> credit
    row = store.conn.execute(
        "SELECT kind, delta_cents FROM ledger WHERE ref LIKE 'reconcile:%'"
    ).fetchone()
    assert row["kind"] == "refund" and row["delta_cents"] == 100


def test_negative_bucket_only_via_reconciliation_and_blocks_spending(wired):
    _store, ledger = wired
    res = ledger.record_reconciliation("tokens", -50_000, "reconcile:x:1")
    assert res["status"] == "recorded"
    assert ledger.balances()["tokens"] < 0
    # a negative bucket blocks further spending through decide()
    assert ledger.request_spend("a", "tokens", 100, "x")["status"] == "rejected"
    # reconciliation is idempotent on ref
    assert ledger.record_reconciliation("tokens", -50_000, "reconcile:x:1")[
        "status"] == "duplicate"


def test_multiplier_clamped_between_1_and_max(wired):
    store, _ledger = wired
    config = Config(cost_truth={"cost_safety_multiplier_max": 5.0})
    # first call just accumulates within the 7-day window
    assert usage._update_multiplier(store, config, actual=100, booked=1000,
                                    now=NOW) is None
    later = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)  # window complete
    mult = usage._update_multiplier(store, config, actual=0, booked=0, now=later)
    assert mult == 1.0  # ratio 0.1 -> clamped up to 1.0
    store.kv_set("calib_actual", "0")
    store.kv_set("calib_booked", "0")
    store.kv_set("calib_since", NOW.isoformat())
    store.kv_set("calib_actual", "50000")
    store.kv_set("calib_booked", "5000")
    mult = usage._update_multiplier(store, config, actual=0, booked=0, now=later)
    assert mult == 5.0  # ratio 10 -> clamped down to max
    store.kv_set("calib_actual", "0")
    store.kv_set("calib_booked", "0")
    store.kv_set("calib_since", NOW.isoformat())
    store.kv_set("calib_actual", "7500")
    store.kv_set("calib_booked", "5000")
    mult = usage._update_multiplier(store, config, actual=0, booked=0, now=later)
    assert mult == 1.5  # ratio 1.5 kept as-is


def test_hard_stop_pauses_paid_runs_until_0005(wired, monkeypatch):
    store, _ledger = wired
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    config = Config(cost_truth={"daily_hard_stop_cents": 120})
    probe = FakeProbe(cumulative=1000, daily=150)
    stop = usage.check_hard_stop(store, config, probe, NOW)
    assert stop and "hard stop" in stop
    assert usage.paid_paused(store, NOW) is True
    # ends at 00:05 UTC next day
    after = datetime(2026, 10, 2, 0, 6, tzinfo=UTC)
    assert usage.paid_paused(store, after) is False
    # under the cap: no pause
    probe2 = FakeProbe(cumulative=1000, daily=100)
    assert usage.check_hard_stop(store, config, probe2, after) is None


def test_missing_probe_files_one_task_and_uses_2x(wired, monkeypatch):
    store, ledger = wired
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    config = Config(models={"builder": "mid"}, costs={"builder": 3})
    res = usage.reconcile(store, ledger, config, None, NOW)
    assert res["status"] == "no-probe"
    usage.reconcile(store, ledger, config, None, NOW)
    tasks = [t for t in store.list_human_tasks("open")
             if t["dedupe_key"] == "env-usage-probe"]
    assert len(tasks) == 1
    assert tasks[0]["kind"] == "secret_provisioning"
    # paid estimates carry the conservative 2.0 multiplier
    assert usage.paid_estimate_cents(store, config, "builder") == math.ceil(3 * 2.0)


def test_paid_estimate_with_probe_uses_kv_multiplier(wired, monkeypatch):
    store, _ledger = wired
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    config = Config(models={"builder": "mid"}, costs={"builder": 3})
    store.kv_set("cost_multiplier", "1.5")
    assert usage.paid_estimate_cents(store, config, "builder") == 5  # ceil(4.5)
    store.kv_set("cost_multiplier", "0.2")
    assert usage.paid_estimate_cents(store, config, "builder") == 3  # never < 1.0x
    # free agents stay free
    assert usage.paid_estimate_cents(store, config, "scout") == 0


def test_openrouter_probe_parses_verified_shape(monkeypatch):
    from kiraci.usage import OpenRouterProbe

    class FakeClient:
        def get_json(self, url, headers):
            assert url == usage.OPENROUTER_KEY_ENDPOINT
            assert headers["Authorization"] == "Bearer sk-test"
            return {"data": {"usage": 1.25, "usage_daily": 0.4}}

    probe = OpenRouterProbe(api_key="sk-test", usd_to_eur=0.92,
                            client=FakeClient())
    assert probe.cumulative_spend_cents() == round(1.25 * 0.92 * 100)  # 115
    assert probe.daily_spend_cents() == round(0.4 * 0.92 * 100)  # 37


def test_probe_unreadable_is_handled(wired):
    store, ledger = wired

    class BrokenProbe(FakeProbe):
        def cumulative_spend_cents(self):
            return None

    res = usage.reconcile(store, ledger, Config(), BrokenProbe(0), NOW)
    assert res["status"] == "probe-unreadable"