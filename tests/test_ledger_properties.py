"""Property tests for the money core (Phase 1, hypothesis).

Invariants over arbitrary operation sequences: buckets never go negative,
the cent total is conserved exactly, and the daily token cap always holds.
"""

import string

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.rules import DEFAULT_POLICY
from kiraci.verify import verify_ledger

AGENTS = ["a", "b", "c"]
BUCKETS = ["infra", "tokens", "experiment", "emergency", "owner", "nope"]
CAP = DEFAULT_POLICY.daily_caps_cents["tokens"]


def fresh():
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    return ledger


def _op():
    return st.one_of(
        st.tuples(st.just("spend"), st.sampled_from(AGENTS),
                  st.sampled_from(BUCKETS), st.integers(-100, 3000)),
        st.tuples(st.just("approve"), st.integers(0, 5)),
        st.tuples(st.just("reject"), st.integers(0, 5)),
        st.tuples(st.just("income"), st.integers(1, 5000),
                  st.integers(0, 1000)),
    )


def _apply(ledger, expected, op):
    kind = op[0]
    if kind == "spend":
        _, agent, bucket, amount = op
        r = ledger.request_spend(agent, bucket, amount, "prop")
        if r["status"] == "approved":
            return expected - amount
        return expected
    if kind == "income":
        _, amount, refnum = op
        before = dict(ledger.balances())
        r = ledger.record_income(amount, f"hyp_{refnum}")
        if r["status"] == "recorded":
            gained = sum(ledger.balances()[b] - before[b]
                         for b in before)
            return expected + gained
        return expected
    pend = ledger.pending()
    if not pend:
        return expected
    target = pend[op[1] % len(pend)]
    if kind == "approve":
        out = ledger.approve(target["id"], "prop-human")
        if out["status"] == "executed":
            return expected - target["amount_cents"]
        return expected
    ledger.reject(target["id"], "prop-human")
    return expected


@settings(max_examples=30, deadline=None,
          suppress_health_check=[HealthCheck.too_slow])
@given(ops=st.lists(_op(), max_size=60))
def test_properties_hold_over_random_sequences(ops):
    ledger = fresh()
    expected = 10_000  # genesis total across all buckets
    for op in ops:
        expected = _apply(ledger, expected, op)
        assert ledger.spent_today("tokens") <= CAP
    balances = ledger.balances()
    assert all(v >= 0 for v in balances.values())
    assert sum(balances.values()) == expected


@given(key=st.text(alphabet=string.ascii_letters, min_size=1, max_size=12),
       amount=st.integers(1, 300), n=st.integers(2, 5))
@settings(max_examples=25, deadline=None)
def test_idempotency_key_replay_changes_nothing(key, amount, n):
    ledger = fresh()
    first = ledger.request_spend("a", "infra", amount, "x",
                                 idempotency_key=key)

    def counts():
        c = ledger.conn
        return (c.execute("SELECT COUNT(*) c FROM ledger").fetchone()["c"],
                c.execute("SELECT COUNT(*) c FROM idempotency_keys"
                          ).fetchone()["c"])

    before = counts()
    for _ in range(n - 1):
        assert ledger.request_spend("a", "infra", amount, "x",
                                    idempotency_key=key) == first
    assert counts() == before
    assert ledger.balances()["infra"] == 3000 - (
        amount if first["status"] == "approved" else 0)


@given(amount=st.integers(1, 5000))
@settings(max_examples=10, deadline=None)
def test_tampered_row_breaks_verify(amount):
    ledger = fresh()
    ledger.record_income(amount, "prop_tamper")
    assert verify_ledger(ledger.conn) == []
    ledger.conn.execute(
        "INSERT INTO ledger(kind,bucket,delta_cents,agent,note)"
        " VALUES ('expense','infra',-1,'mallory','x')")
    assert verify_ledger(ledger.conn) != []


def test_overlong_idempotency_key_rejected():
    with pytest.raises(ValueError):
        fresh().request_spend("a", "infra", 10, "x",
                              idempotency_key="k" * 129)
