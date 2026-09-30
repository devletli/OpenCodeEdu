from datetime import UTC, datetime

from kiraci.config import Config
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.orchestrator import Orchestrator
from kiraci.store import Store
from kiraci.testing import FakeRunner


def make_orch(tmp_path, monkeypatch, now, outputs):
    for var in ("KIRACI_MODEL_STRONG", "KIRACI_MODEL_MID", "KIRACI_MODEL_CHEAP"):
        monkeypatch.setenv(var, "test/model")
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    store = Store(conn)
    config = Config(
        models={"brain": "strong", "scout": "cheap"},
        costs={}, limits={"run_timeout_seconds": 60})
    clock = {"now": now}
    orch = Orchestrator(root=tmp_path, store=store, ledger=ledger,
                        config=config, runner=FakeRunner(outputs=outputs),
                        clock=lambda: clock["now"])
    orch.startup()
    store.kv_set("bootstrapped", "1")
    return orch, clock, store


def research_file(tmp_path):
    files = list((tmp_path / "research").glob("*.md"))
    assert len(files) == 1
    return files[0]


def test_two_urls_banner_and_single_rerun(tmp_path, monkeypatch):
    now = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    orch, _clock, store = make_orch(tmp_path, monkeypatch, now, outputs={
        "scout": ["see https://a.example/1 and https://b.example/2",
                  "full https://a.example/1 https://b.example/2 https://c.example/3"]})
    r = store.create_task(agent="scout", title="Research widgets", prompt="go",
                          created_by="brain")
    tid = r["task_id"]
    orch.tick()
    task = store.get_task(tid)
    assert task["status"] == "pending"  # re-run queued, not done
    assert research_file(tmp_path).read_text(encoding="utf-8").startswith(
        "> UNVERIFIED")
    assert store.kv_get(f"evidence_rerun:{tid}") == "1"
    orch.tick()
    task = store.get_task(tid)
    assert task["status"] == "done"
    assert not research_file(tmp_path).read_text(
        encoding="utf-8").startswith("> UNVERIFIED")
    orch.tick()
    assert len(orch.runner.calls_for("scout")) == 2  # exactly one re-run


def test_three_urls_clean(tmp_path, monkeypatch):
    now = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    orch, _clock, store = make_orch(tmp_path, monkeypatch, now, outputs={
        "scout": ["x https://a.example/1 https://b.example/2 https://c.example/3"]})
    r = store.create_task(agent="scout", title="Research widgets", prompt="go",
                          created_by="brain")
    orch.tick()
    assert store.get_task(r["task_id"])["status"] == "done"
    assert not research_file(tmp_path).read_text(
        encoding="utf-8").startswith("> UNVERIFIED")
    assert store.kv_get(f"evidence_rerun:{r['task_id']}") is None
