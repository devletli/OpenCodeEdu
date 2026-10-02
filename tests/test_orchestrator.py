from datetime import UTC, datetime

from kiraci.config import Config
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.orchestrator import Orchestrator
from kiraci.runner import RunResult
from kiraci.store import Store, tomorrow_0005
from kiraci.testing import FakeRunner


def make_orch(tmp_path, monkeypatch, now, *, bootstrapped=True, runner=None):
    for var in ("KIRACI_MODEL_STRONG", "KIRACI_MODEL_MID", "KIRACI_MODEL_CHEAP"):
        monkeypatch.setenv(var, "test/model")
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    store = Store(conn)
    config = Config(
        models={"brain": "strong", "judge": "mid", "builder": "mid",
                "scout": "cheap", "seller": "cheap", "treasurer": "cheap",
                "diplomat": "cheap", "chronicler": "cheap"},
        costs={"brain": 5, "judge": 3, "builder": 3},
        limits={"tick_seconds": 30, "run_timeout_seconds": 60,
                "max_task_attempts": 3, "yellow_daily_auto_approve_cents": 1000,
                "min_free_disk_mb": 1, "max_consecutive_failures": 5},
    )
    runner = runner if runner is not None else FakeRunner()
    clock = {"now": now}
    orch = Orchestrator(root=tmp_path, store=store, ledger=ledger,
                        config=config, runner=runner,
                        clock=lambda: clock["now"])
    orch.startup()
    if bootstrapped:
        store.kv_set("bootstrapped", "1")
    return orch, clock, store, ledger, runner


def queue(store, agent, title="Work", priority=5):
    r = store.create_task(agent=agent, title=title, prompt="do it",
                          priority=priority, created_by="brain")
    assert r["status"] == "created", r
    return r["task_id"]


def test_agents_dispatch_anytime_06_to_22(tmp_path, monkeypatch):
    orch, clock, store, _, _ = make_orch(
        tmp_path, monkeypatch, datetime(2026, 1, 5, 5, 0, tzinfo=UTC))
    tid = queue(store, "scout")
    orch.tick()  # 05:00, night: nothing runs
    assert store.get_task(tid)["status"] == "pending"

    clock["now"] = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    orch.tick()
    assert store.get_task(tid)["status"] == "done"

    for hh in (6, 13, 21):
        t = queue(store, "scout", priority=4)  # ahead of any leftover p5 jobs
        clock["now"] = datetime(2026, 1, 5, hh, 0, tzinfo=UTC)
        orch.tick()
        assert store.get_task(t)["status"] == "done"


def test_priority_zero_ignores_windows_but_not_night(tmp_path, monkeypatch):
    orch, clock, store, _, _ = make_orch(
        tmp_path, monkeypatch, datetime(2026, 1, 5, 13, 0, tzinfo=UTC))
    tid = queue(store, "scout", priority=0)
    orch.tick()
    assert store.get_task(tid)["status"] == "done"

    tid2 = queue(store, "scout", priority=0)
    clock["now"] = datetime(2026, 1, 5, 23, 0, tzinfo=UTC)
    summary = orch.tick()
    assert "night" in summary
    assert store.get_task(tid2)["status"] == "pending"


def test_one_shot_jobs_run_once_per_day(tmp_path, monkeypatch):
    orch, _, store, _, _ = make_orch(
        tmp_path, monkeypatch, datetime(2026, 1, 5, 6, 5, tzinfo=UTC))
    orch.tick()
    orch.tick()
    assert store.kv_get("job:morning_report:2026-01-05") == "1"
    all_tasks = store.list_tasks()
    assert len([t for t in all_tasks if t["title"] == "Daily cash report"]) == 1


def test_kill_stops_loop(tmp_path, monkeypatch):
    orch, _, _, _, _ = make_orch(
        tmp_path, monkeypatch, datetime(2026, 1, 5, 8, 0, tzinfo=UTC))
    (tmp_path / "data" / "KILL").touch()
    summary = orch.tick()
    assert "killed" in summary and orch.stopped


def test_pause_skips_dispatch(tmp_path, monkeypatch):
    orch, _, store, _, _ = make_orch(
        tmp_path, monkeypatch, datetime(2026, 1, 5, 8, 0, tzinfo=UTC))
    tid = queue(store, "scout")
    (tmp_path / "data" / "PAUSE").touch()
    summary = orch.tick()
    assert "paused" in summary
    assert store.get_task(tid)["status"] == "pending"


def test_ledger_refusal_defers_to_tomorrow(tmp_path, monkeypatch):
    runner = FakeRunner(outputs={"scout": [RunResult(
        ok=False, text="", exit_code=None, duration_s=0.0,
        skipped_reason="budget: daily cap would be exceeded")]})
    now = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    orch, _, store, _, _ = make_orch(tmp_path, monkeypatch, now, runner=runner)
    tid = queue(store, "scout")
    orch.tick()
    task = store.get_task(tid)
    assert task["status"] == "pending"
    assert task["not_before"] == tomorrow_0005(now)


def test_survival_mode_dispatch_filter(tmp_path, monkeypatch):
    orch, clock, store, ledger, _ = make_orch(
        tmp_path, monkeypatch, datetime(2026, 1, 5, 8, 0, tzinfo=UTC))
    ledger.conn.execute(
        "INSERT INTO ledger(kind,bucket,delta_cents,agent,note)"
        " VALUES ('expense','infra',-9001,'test','drain')")
    assert ledger.total_balance() < 1000
    regular = queue(store, "scout", "Regular research")
    revenue = queue(store, "scout", "[revenue] Quick win")
    cash = queue(store, "treasurer", "Cash check")
    build = queue(store, "builder", "[revenue] Thing")
    assert "SURVIVAL" in orch.tick()
    assert store.get_task(revenue)["status"] == "done"
    orch.tick()  # 08:00: treasurer is window-open all day now, so cash runs
    assert store.get_task(cash)["status"] == "done"
    assert store.get_task(regular)["status"] == "pending"
    clock["now"] = datetime(2026, 1, 5, 20, 5, tzinfo=UTC)
    orch.tick()  # survival still filters regular (non-revenue) and build (paid)
    assert store.get_task(regular)["status"] == "pending"
    clock["now"] = datetime(2026, 1, 6, 13, 0, tzinfo=UTC)
    orch.tick()
    assert store.get_task(build)["status"] == "pending"  # paid run, banned


def test_missing_model_env_creates_one_task(tmp_path, monkeypatch):
    orch, _, store, _, _ = make_orch(
        tmp_path, monkeypatch, datetime(2026, 1, 5, 8, 0, tzinfo=UTC))
    monkeypatch.delenv("KIRACI_MODEL_CHEAP")
    from kiraci.orchestrator import Orchestrator as O

    orch2 = O(root=tmp_path, store=store, ledger=orch.ledger,
              config=orch.config, runner=orch.runner, clock=orch.clock)
    orch2.startup()
    orch2.tick()
    orch2.tick()
    found = [t for t in store.list_human_tasks("open")
             if t["dedupe_key"] == "env-models"]
    assert len(found) == 1
    assert found[0]["kind"] == "secret_provisioning"


def test_bootstrap_runs_once(tmp_path, monkeypatch):
    orch, _, store, _, runner = make_orch(
        tmp_path, monkeypatch, datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
        bootstrapped=False)
    orch.tick()
    assert store.kv_get("bootstrapped") == "1"
    assert len(runner.calls_for("brain")) == 1
    assert (tmp_path / "data" / "outputs" / "brain-2026-01-05-bootstrap.md").exists()
    orch.tick()
    assert len(runner.calls_for("brain")) == 1
