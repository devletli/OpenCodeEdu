import random
import sqlite3

import pytest

from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.rules import DEFAULT_POLICY, decide


@pytest.fixture
def ledger():
    ledger_obj = Ledger(connect(":memory:"))
    ledger_obj.init_genesis()
    return ledger_obj


def test_genesis_is_100_eur(ledger):
    assert ledger.total_balance() == 10_000
    assert ledger.balances()["emergency"] == 1500


def test_genesis_only_once(ledger):
    with pytest.raises(RuntimeError):
        ledger.init_genesis()


def test_auto_approve_within_limit(ledger):
    r = ledger.request_spend("builder", "infra", 300, "vps")
    assert r["status"] == "approved"
    assert ledger.balances()["infra"] == 2700


def test_yellow_pending_above_auto_limit(ledger):
    r = ledger.request_spend("builder", "infra", 301, "domain")
    assert r["status"] == "pending" and r["tier"] == "yellow"
    assert ledger.balances()["infra"] == 3000  # not deducted yet


def test_red_above_hard_limit(ledger):
    r = ledger.request_spend("brain", "experiment", 1001, "ads")
    assert r["status"] == "pending" and r["tier"] == "red"


def test_insufficient_balance_rejected(ledger):
    r = ledger.request_spend("brain", "experiment", 2600, "big project")
    assert r["status"] == "rejected"


def test_daily_token_cap(ledger):
    assert ledger.request_spend("scout", "tokens", 40, "llm")["status"] == "approved"
    assert ledger.request_spend("scout", "tokens", 30, "llm")["status"] == "rejected"
    assert ledger.request_spend("scout", "tokens", 20, "llm")["status"] == "approved"


@pytest.mark.parametrize("bucket", ["emergency", "owner"])
def test_human_only_buckets(ledger, bucket):
    ledger.record_income(10_000, "pay_1")  # give the owner bucket a balance too
    r = ledger.request_spend("brain", bucket, 100, "x")
    assert r["status"] == "pending" and r["tier"] == "red"


def test_negative_or_zero_amount_rejected(ledger):
    assert ledger.request_spend("a", "infra", 0, "x")["status"] == "rejected"
    assert ledger.request_spend("a", "infra", -5, "x")["status"] == "rejected"


def test_unknown_bucket_rejected(ledger):
    assert ledger.request_spend("a", "casino", 100, "x")["status"] == "rejected"


def test_approve_executes_spend(ledger):
    r = ledger.request_spend("builder", "infra", 500, "server upgrade")
    out = ledger.approve(r["approval_id"], "dev")
    assert out["status"] == "executed"
    assert ledger.balances()["infra"] == 2500
    assert ledger.approve(r["approval_id"], "dev")["status"] == "error"  # no double approval


def test_approve_rechecks_balance(ledger):
    pending = ledger.request_spend("brain", "experiment", 500, "test")
    for _ in range(8):
        assert ledger.request_spend("brain", "experiment", 300, "x")["status"] == "approved"
    out = ledger.approve(pending["approval_id"], "dev")  # only 100 left < 500
    assert out["status"] == "rejected"


def test_reject_pending(ledger):
    r = ledger.request_spend("brain", "experiment", 500, "test")
    assert ledger.reject(r["approval_id"], "dev")["status"] == "rejected"
    assert ledger.pending() == []


def test_ledger_is_append_only(ledger):
    with pytest.raises(sqlite3.DatabaseError):
        ledger.conn.execute("DELETE FROM ledger")
    with pytest.raises(sqlite3.DatabaseError):
        ledger.conn.execute("UPDATE ledger SET delta_cents = 1")


def test_income_split_and_idempotent(ledger):
    out = ledger.record_income(1000, "ls_order_1")
    assert out == {"status": "recorded", "experiment": 500, "emergency": 300, "owner": 200}
    assert ledger.record_income(1000, "ls_order_1")["status"] == "duplicate"
    assert ledger.balances()["owner"] == 200


def test_income_requires_ref(ledger):
    with pytest.raises(ValueError):
        ledger.record_income(100, "")


def test_survival_mode_blocks_experiment_spending():
    d = decide(DEFAULT_POLICY, bucket="experiment", amount=100, bucket_balance=500,
               total_balance=900, spent_today=0)
    assert d.status == "rejected"
    d2 = decide(DEFAULT_POLICY, bucket="infra", amount=100, bucket_balance=500,
                total_balance=900, spent_today=0)
    assert d2.status == "approved"  # rent still gets paid


def test_no_bucket_ever_goes_negative(ledger):
    rng = random.Random(42)
    for _ in range(300):
        ledger.request_spend("fuzz", rng.choice(["infra", "tokens", "experiment", "emergency"]),
                             rng.randint(-50, 1500), "fuzz")
        if rng.random() < 0.3 and (p := ledger.pending()):
            ledger.approve(rng.choice(p)["id"], "fuzz-human")
    assert all(v >= 0 for v in ledger.balances().values())
