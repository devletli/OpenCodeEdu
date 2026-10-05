"""Resume-after-restart, survival cheapest-model, and MCP surface tests."""

import inspect

from kiraci import mcp_server as ledger_mcp
from kiraci import queue_mcp
from kiraci.config import Config
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.orchestrator import Orchestrator
from kiraci.runner import OpencodeRunner, RunResult
from kiraci.store import Store
from kiraci.testing import FakeRunner


def make_orch(tmp_path, monkeypatch, *, runner=None):
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
    orch = Orchestrator(root=tmp_path, store=store, ledger=ledger,
                        config=config,
                        runner=runner if runner is not None else FakeRunner())
    return orch, store


def queue(store, agent, title="Work"):
    r = store.create_task(agent=agent, title=title, prompt="do it",
                          priority=5, created_by="brain")
    assert r["status"] == "created", r
    return r["task_id"]


def test_resume_requeues_stale_running(tmp_path, monkeypatch):
    orch, store = make_orch(tmp_path, monkeypatch)
    tid = queue(store, "scout")
    store.set_status(tid, "running")
    done_id = queue(store, "scout", title="Finished")
    store.set_status(done_id, "done", result_summary="ok")
    orch.startup()
    t = store.get_task(tid)
    assert t["status"] == "pending"
    assert t["attempts"] == 1
    assert "restart" in t["result_summary"]
    assert store.get_task(done_id)["status"] == "done"
    orch.startup()  # idempotent: no double attempts
    assert store.get_task(tid)["attempts"] == 1


def test_resume_leaves_blocked_alone(tmp_path, monkeypatch):
    orch, store = make_orch(tmp_path, monkeypatch)
    tid = queue(store, "scout")
    hid = store.add_human_task(
        kind="login", title="T", instructions="I", dedupe_key="k",
        created_by="scout")["task"]["id"]
    store.set_status(tid, "blocked", blocked_on=hid)
    orch.startup()
    t = store.get_task(tid)
    assert t["status"] == "blocked" and t["blocked_on"] == hid


def test_apply_survival_mode_flag_and_flagless(tmp_path, monkeypatch):
    orch, _ = make_orch(tmp_path, monkeypatch)

    class FlagRunner(FakeRunner):
        def __init__(self):
            super().__init__()
            self.survival_mode = False

    flagged = FlagRunner()
    orch.runner = flagged
    orch._apply_survival_mode(True)
    assert flagged.survival_mode is True
    orch._apply_survival_mode(False)
    assert flagged.survival_mode is False
    orch.runner = FakeRunner()  # no flag: must not crash
    orch._apply_survival_mode(True)


def test_runner_survival_uses_cheap_chain(tmp_path, monkeypatch):
    monkeypatch.setenv("KIRACI_MODEL_MID", "test/mid-model")
    monkeypatch.setenv("KIRACI_MODEL_CHEAP", "test/cheap-model")
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    config = Config(models={"builder": "mid", "scout": "cheap"}, costs={})
    runner = OpencodeRunner(ledger=ledger, store=Store(conn), config=config)
    seen = []

    def fake_execute(agent, model, prompt, cwd, timeout_s, task_id):
        seen.append(model)
        return RunResult(ok=True, text="ok", exit_code=0, duration_s=0.1)

    monkeypatch.setattr(runner, "_execute", fake_execute)
    runner.run("builder", "build", tmp_path, 60)
    assert seen[-1] == "test/mid-model"
    runner.survival_mode = True
    runner.run("builder", "build", tmp_path, 60)
    assert seen[-1] == "test/cheap-model"
    runner.run("scout", "search", tmp_path, 60)
    assert seen[-1] == "test/cheap-model"


def _public_tools(mod):
    return {name for name, fn in inspect.getmembers(mod, inspect.isfunction)
            if fn.__module__ == mod.__name__ and not name.startswith("_")}


PRIVILEGED = {"approve", "reject", "resolve", "dismiss", "record_income",
              "record_refund", "init_genesis", "set_product",
              "set_external_product", "restore", "resolve_human_task"}


def test_ledger_mcp_surface_has_no_privileged_tools():
    assert _public_tools(ledger_mcp) == {
        "get_balances", "request_spend", "list_pending", "recent_entries"}
    assert not (_public_tools(ledger_mcp) & PRIVILEGED)


def test_queue_mcp_surface_has_no_privileged_tools():
    assert _public_tools(queue_mcp) == {
        "create_task", "list_tasks", "request_human_action",
        "list_human_tasks", "create_venture", "update_venture",
        "list_ventures"}
    assert not (_public_tools(queue_mcp) & PRIVILEGED)


def test_sandbox_gate_open_without_sandbox(tmp_path, monkeypatch):
    """FakeRunner path (dry-run): gate is open, nothing real is executed."""
    orch, _store = make_orch(tmp_path, monkeypatch)
    assert orch.sandbox is None
    assert orch._sandbox_gate(orch.now()) == "ok"
