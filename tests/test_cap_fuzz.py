"""Fuzz: no agent path can push today's token spend past the daily cap.

Every spend in the system funnels through `Ledger.request_spend`
(direct agent calls, the broker, and the runner's pre-run gate all call
the same function) plus human `approve()` on pending rows. The fuzz hammers
all of them with seeded randomness and asserts the cap holds every step.
"""

import random

from kiraci.config import Config
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.rules import DEFAULT_POLICY
from kiraci.runner import OpencodeRunner
from kiraci.store import Store

AGENTS = ["scout", "builder", "seller", "treasurer", "diplomat", "chronicler",
          "brain", "judge"]
BUCKETS = ["tokens", "tokens", "tokens", "infra", "experiment", "emergency",
           "owner", "casino", ""]


def fresh_ledger():
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    return ledger


def test_fuzz_token_cap_holds_across_spend_and_approve():
    cap = DEFAULT_POLICY.daily_caps_cents["tokens"]
    for seed in range(30):
        rng = random.Random(seed)
        ledger = fresh_ledger()
        for _ in range(200):
            agent = rng.choice(AGENTS)
            bucket = rng.choice(BUCKETS)
            amount = rng.randint(-50, 1200)
            r = ledger.request_spend(agent, bucket, amount, "fuzz")
            if r["status"] == "pending" and rng.random() < 0.5:
                if rng.random() < 0.7:
                    ledger.approve(r["approval_id"], "fuzz-human")
                else:
                    ledger.reject(r["approval_id"], "fuzz-human")
            assert ledger.spent_today("tokens") <= cap, (seed, agent)
            assert all(v >= 0 for v in ledger.balances().values()), seed


def test_fuzz_runner_gate_stops_paid_runs_at_cap(monkeypatch):
    """Full gate path (spend gate + runs rows + a real trivial process)."""
    monkeypatch.setenv("KIRACI_MODEL_MID", "test/model")
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    config = Config(models={"builder": "mid"}, costs={"builder": 3})
    runner = OpencodeRunner(ledger=ledger, store=Store(conn), config=config,
                            cmd_builder=lambda _a, _m, _p: ["true"])
    ok_runs = 0
    skipped = 0
    for _ in range(25):
        res = runner.run("builder", "build", ".", 60)
        if res.ok:
            ok_runs += 1
        else:
            assert res.skipped_reason is not None
            assert res.skipped_reason.startswith("budget:")
            skipped += 1
    assert ok_runs > 0
    assert skipped > 0  # the gate actually fired
    assert ledger.spent_today("tokens") <= 60


def test_fuzz_income_then_spend_still_capped():
    cap = DEFAULT_POLICY.daily_caps_cents["tokens"]
    rng = random.Random(7)
    ledger = fresh_ledger()
    for i in range(50):
        if rng.random() < 0.2:
            ledger.record_income(rng.randint(100, 5000), f"pay_{i}")
        agent = rng.choice(AGENTS)
        r = ledger.request_spend(agent, "tokens", rng.randint(1, 300), "fuzz")
        if r["status"] == "pending":
            ledger.approve(r["approval_id"], "fuzz-human")
        assert ledger.spent_today("tokens") <= cap
