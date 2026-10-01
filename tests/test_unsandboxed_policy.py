from datetime import UTC, datetime

from kiraci.config import Config
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.orchestrator import Orchestrator
from kiraci.sandbox import UNSANDBOXED_ALLOWED_AGENTS
from kiraci.store import Store
from kiraci.testing import FakeRunner


class UnavailableSandbox:
    def status(self, *, force=False):
        return "unavailable"

    def unsandboxed_agent_allowed(self, agent):
        return agent in UNSANDBOXED_ALLOWED_AGENTS


class DisabledSandbox:
    def status(self, *, force=False):
        return "disabled"

    def unsandboxed_agent_allowed(self, agent):
        return agent in UNSANDBOXED_ALLOWED_AGENTS


def make_orch(tmp_path, monkeypatch, sandbox, now=None):
    for var in ("KIRACI_MODEL_STRONG", "KIRACI_MODEL_MID", "KIRACI_MODEL_CHEAP"):
        monkeypatch.setenv(var, "test/model")
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    store = Store(conn)
    config = Config(
        models={"brain": "strong", "builder": "mid", "scout": "cheap",
                "treasurer": "cheap"},
        costs={"builder": 3},
        limits={"run_timeout_seconds": 60, "min_free_disk_mb": 1,
                "max_consecutive_failures": 5},
    )
    runner = FakeRunner()
    now = now or datetime(2026, 1, 5, 10, 0, tzinfo=UTC)  # scout window open
    orch = Orchestrator(root=tmp_path, store=store, ledger=ledger,
                        config=config, runner=runner,
                        clock=lambda: now, sandbox=sandbox)
    orch.startup()
    store.kv_set("bootstrapped", "1")
    return orch, store


def queue(store, agent, title="Work"):
    r = store.create_task(agent=agent, title=title, prompt="do it",
                          priority=0, created_by="brain")
    assert r["status"] == "created", r
    return r["task_id"]


def test_required_mode_with_unavailable_sandbox_dispatches_nothing(tmp_path,
                                                                   monkeypatch):
    orch, store = make_orch(tmp_path, monkeypatch, UnavailableSandbox())
    tid = queue(store, "scout")
    summary = orch.tick()
    assert "dispatch:none (sandbox unavailable)" in summary
    assert store.get_task(tid)["status"] == "pending"
    # a system notice was written - never a human task for the sandbox
    inbox = (tmp_path / "HUMAN_INBOX.md").read_text(encoding="utf-8")
    assert "sandbox" in inbox.lower()
    assert [t for t in store.open_human_tasks()
            if "sandbox" in t["title"].lower()] == []
    # the notice is sent at most once per day
    first = (tmp_path / "HUMAN_INBOX.md").read_text(encoding="utf-8")
    orch.tick()
    second = (tmp_path / "HUMAN_INBOX.md").read_text(encoding="utf-8")
    assert first == second  # no duplicate notice


def test_override_runs_only_no_bash_no_write_agents(tmp_path, monkeypatch):
    monkeypatch.setenv("KIRACI_SANDBOX", "off")
    monkeypatch.setenv("KIRACI_ALLOW_UNSANDBOXED", "1")
    orch, store = make_orch(tmp_path, monkeypatch, DisabledSandbox())
    scout_id = queue(store, "scout", "Research thing")
    builder_id = queue(store, "builder", "Build thing")
    judge_note = queue(store, "treasurer", "Cash check")
    summary = orch.tick()  # one task per tick: scout (priority 0, oldest first)
    assert "task #1 done" in summary or "dispatched" in summary
    assert store.get_task(scout_id)["status"] == "done"
    assert store.get_task(builder_id)["status"] == "pending"
    assert store.get_task(judge_note)["status"] == "pending"
    # without the override env, nothing runs at all
    monkeypatch.delenv("KIRACI_ALLOW_UNSANDBOXED")
    orch2, store2 = make_orch(tmp_path, monkeypatch, DisabledSandbox())
    tid2 = queue(store2, "scout")
    summary2 = orch2.tick()
    assert "dispatch:none (sandbox unavailable)" in summary2
    assert store2.get_task(tid2)["status"] == "pending"