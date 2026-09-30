import pytest

from kiraci.config import Config
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.review import review_approvals
from kiraci.store import Store
from kiraci.testing import FakeRunner


@pytest.fixture
def ctx(tmp_path):
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    store = Store(conn)
    config = Config(
        models={"judge": "mid", "builder": "mid", "scout": "cheap"},
        costs={"judge": 3, "builder": 3},
        limits={"yellow_daily_auto_approve_cents": 1000,
                "run_timeout_seconds": 60},
    )
    return {"ledger": ledger, "store": store, "config": config, "root": tmp_path}


def _review(ctx, runner, judge_enabled=True):
    return review_approvals(
        store=ctx["store"], ledger=ctx["ledger"], runner=runner,
        config=ctx["config"], balances=ctx["ledger"].balances(),
        runway_str="test", judge_enabled=judge_enabled,
        repo_root=ctx["root"], timeout_s=60,
    )


def _decided_by(ctx, approval_id):
    row = ctx["ledger"].conn.execute(
        "SELECT status, decided_by FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    return row["status"], row["decided_by"]


def test_yellow_accept_executes_with_judge(ctx):
    r = ctx["ledger"].request_spend("builder", "infra", 500, "server upgrade")
    runner = FakeRunner(outputs={"judge": ["ACCEPT\nspecific and proportional"]})
    out = _review(ctx, runner)
    assert out["yellow_accepted"] == 1
    status, by = _decided_by(ctx, r["approval_id"])
    assert (status, by) == ("executed", "judge")
    assert ctx["ledger"].balances()["infra"] == 2500


def test_yellow_reject_and_garbled(ctx):
    r1 = ctx["ledger"].request_spend("builder", "infra", 500, "vague stuff")
    r2 = ctx["ledger"].request_spend("builder", "infra", 500, "more stuff")
    runner = FakeRunner(outputs={"judge": ["REJECT\ntoo vague", "maybe, not sure"]})
    out = _review(ctx, runner)
    assert out["yellow_rejected"] == 2
    assert _decided_by(ctx, r1["approval_id"])[0] == "rejected"
    assert _decided_by(ctx, r2["approval_id"])[0] == "rejected"


def test_judge_approvals_never_self_reviewed(ctx):
    ctx["ledger"].conn.execute(
        """INSERT INTO approvals(agent,bucket,amount_cents,purpose,tier,status,reason)
           VALUES ('judge','infra',200,'self deal','yellow','pending','')"""
    )
    runner = FakeRunner(outputs={"judge": ["ACCEPT\nsure"]})
    out = _review(ctx, runner)
    assert runner.calls == []
    assert out["yellow_accepted"] == 0
    row = ctx["ledger"].conn.execute(
        "SELECT status FROM approvals WHERE agent='judge'").fetchone()
    assert row["status"] == "pending"


def test_daily_yellow_limit_respected(ctx):
    ctx["config"] = Config(
        models={"judge": "mid"}, costs={"judge": 3},
        limits={"yellow_daily_auto_approve_cents": 400, "run_timeout_seconds": 60},
    )
    r1 = ctx["ledger"].request_spend("builder", "infra", 350, "one")
    r2 = ctx["ledger"].request_spend("builder", "infra", 350, "two")
    runner = FakeRunner(outputs={"judge": ["ACCEPT", "ACCEPT"]})
    out = _review(ctx, runner)
    assert out["yellow_accepted"] == 1 and out["yellow_deferred"] == 1
    assert len(runner.calls_for("judge")) == 1
    assert _decided_by(ctx, r1["approval_id"])[0] == "executed"
    assert _decided_by(ctx, r2["approval_id"])[0] == "pending"


def test_red_creates_exactly_one_human_task_and_closes(ctx):
    r = ctx["ledger"].request_spend("brain", "emergency", 100, "reserve use")
    assert r["status"] == "pending" and r["tier"] == "red"
    runner = FakeRunner()
    out1 = _review(ctx, runner)
    out2 = _review(ctx, runner)
    assert out1["red_filed"] == 1 and out2["red_filed"] == 0
    open_tasks = ctx["store"].list_human_tasks("open")
    assert len(open_tasks) == 1
    assert open_tasks[0]["dedupe_key"] == f"approval:{r['approval_id']}"
    assert open_tasks[0]["kind"] == "red_tier_approval"
    assert ctx["ledger"].approve(r["approval_id"], "dev")["status"] == "executed"
    out3 = _review(ctx, runner)
    assert out3["red_closed"] == 1
    assert ctx["store"].list_human_tasks("open") == []
