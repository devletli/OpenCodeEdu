import json
import os
import time

import pytest

from kiraci.broker import HANDLERS, HUMAN_ONLY_OPERATIONS, BrokerSession, _read_request
from kiraci.config import Config
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.store import Store


@pytest.fixture
def wired(tmp_path, monkeypatch):
    monkeypatch.setenv("KIRACI_DB", str(tmp_path / "b.db"))
    conn = connect(str(tmp_path / "b.db"))
    ledger = Ledger(conn)
    ledger.init_genesis()
    store = Store(conn)
    config = Config(models={"scout": "cheap"}, costs={},
                    revenue={"venture_budget_cents": 1500,
                             "max_active_ventures": 3,
                             "min_sources_per_research": 3})
    return {"conn": conn, "ledger": ledger, "store": store, "config": config,
            "tmp": tmp_path}


def make_session(wired, agent, *, root=None):
    run_dir = wired["tmp"] / "ipc" / agent
    s = BrokerSession("run-1", agent, run_dir, root=root or wired["tmp"],
                      connect_fn=lambda: connect(str(wired["tmp"] / "b.db")),
                      config=wired["config"])
    s.start()
    return s


def send_and_wait(session, server, tool, args, timeout=5.0):
    # Atomic write (temp file + rename), exactly like the real IPC client:
    # the broker polls every 100 ms and must never see a partial file.
    # A plain write_text raced the poller under load ("not valid JSON").
    name = f"{temp_counter[0]}.json"
    temp_counter[0] += 1
    target = session.ipc_dir / "requests" / name
    tmp = target.with_name(f"{name}.{os.getpid()}.tmp")
    tmp.write_text(
        json.dumps({"server": server, "tool": tool, "args": args}),
        encoding="utf-8")
    os.replace(tmp, target)
    resp = session.ipc_dir / "responses" / name
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if resp.exists():
            return json.loads(resp.read_text(encoding="utf-8"))
        time.sleep(0.02)
    raise AssertionError("no response from broker")


temp_counter = [0]


def test_identity_is_assigned_by_the_system_not_the_agent(wired):
    """A client claiming to be judge inside a builder session books as builder."""
    s = make_session(wired, "builder")
    try:
        resp = send_and_wait(s, "ledger", "request_spend", {
            "agent": "judge",  # spoofed identity - must be ignored
            "bucket": "infra", "amount_eur": 1.0, "purpose": "x"})
        assert resp["ok"] is True
        row = wired["conn"].execute(
            "SELECT agent FROM ledger WHERE kind='expense'").fetchone()
        assert row["agent"] == "builder"
    finally:
        s.cleanup()


def test_tools_outside_allowlist_are_rejected(wired):
    s = make_session(wired, "scout")
    try:
        resp = send_and_wait(s, "ledger", "request_spend",
                             {"bucket": "infra", "amount_eur": 1.0,
                              "purpose": "x"})
        assert resp["ok"] is False
        assert "not allowed" in resp["error"]
        # scout may list tasks
        resp2 = send_and_wait(s, "queue", "list_tasks", {})
        assert resp2["ok"] is True
    finally:
        s.cleanup()


def test_requests_of_finished_or_unknown_runs_are_ignored(wired, tmp_path):
    orphan = tmp_path / "ipc" / "ghost"
    (orphan / "requests").mkdir(parents=True)
    (orphan / "requests" / "t.json").write_text(
        json.dumps({"server": "queue", "tool": "list_tasks", "args": {}}),
        encoding="utf-8")
    time.sleep(0.3)  # no session ever polls this directory
    assert not (orphan / "responses" / "t.json").exists()
    assert (orphan / "requests" / "t.json").exists()  # untouched


def test_symlinked_oversized_nested_nonjson_requests_rejected(wired, tmp_path):
    s = make_session(wired, "scout")
    reqdir = s.ipc_dir / "requests"
    try:
        # non-json file: ignored entirely
        (reqdir / "notes.txt").write_text("hello", encoding="utf-8")
        # oversized
        (reqdir / "big.json").write_text("x" * (64 * 1024 + 1), encoding="utf-8")
        # deeply nested
        deep = {"a": None}
        node = deep
        for _ in range(8):
            node["a"] = {"a": None}
            node = node["a"]
        (reqdir / "deep.json").write_text(
            json.dumps({"server": "queue", "tool": "list_tasks", "args": deep}),
            encoding="utf-8")
        # non-json content in a .json file
        (reqdir / "bad.json").write_text("not json at all {{{", encoding="utf-8")
        # symlinked (POSIX; skipped where symlinks are unavailable)
        target = tmp_path / "target.json"
        target.write_text("{}", encoding="utf-8")
        try:
            os.symlink(target, reqdir / "link.json")
            symlinked = True
        except OSError:
            symlinked = False
        time.sleep(0.5)
        names = {p.name for p in (s.ipc_dir / "responses").iterdir()}
        assert "big.json" in names and "deep.json" in names and "bad.json" in names
        if symlinked:
            assert "link.json" in names
        # error messages never echo file content
        for name in ("big.json", "deep.json", "bad.json"):
            payload = json.loads(
                (s.ipc_dir / "responses" / name).read_text(encoding="utf-8"))
            assert payload["ok"] is False
            assert "x" * 100 not in payload["error"]
            assert "not json at all" not in payload["error"]
        if symlinked:
            payload = json.loads(
                (s.ipc_dir / "responses" / "link.json").read_text(encoding="utf-8"))
            assert payload["ok"] is False
    finally:
        s.cleanup()


def test_request_limit_200_holds(wired):
    s = make_session(wired, "scout")
    reqdir = s.ipc_dir / "requests"
    try:
        for i in range(205):
            (reqdir / f"r{i:03d}.json").write_text(
                json.dumps({"server": "queue", "tool": "list_tasks", "args": {}}),
                encoding="utf-8")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if len(list((s.ipc_dir / "responses").glob("*.json"))) >= 205:
                break
            time.sleep(0.05)
        time.sleep(0.2)  # let the broker finish writing the last responses
        errors = 0
        ok = 0
        for p in (s.ipc_dir / "responses").glob("*.json"):
            payload = json.loads(p.read_text(encoding="utf-8"))
            ok += payload["ok"] is True
            errors += payload["ok"] is False
        assert ok == 200
        assert errors == 5
    finally:
        s.cleanup()


def test_processed_requests_are_deleted(wired):
    s = make_session(wired, "scout")
    try:
        send_and_wait(s, "queue", "list_tasks", {})
        assert list((s.ipc_dir / "requests").glob("*.json")) == []
    finally:
        s.cleanup()


def test_directory_removed_after_run(wired):
    s = make_session(wired, "scout")
    run_dir = s.ipc_dir
    s.cleanup()
    assert not run_dir.exists()


def test_no_broker_handler_for_human_only_operations():
    overlap = set(HANDLERS) & set(HUMAN_ONLY_OPERATIONS)
    assert overlap == set(), overlap
    for name in ("ledger_approve", "ledger_reject", "ledger_record_income",
                 "ledger_record_refund", "ledger_init_genesis",
                 "queue_resolve_human_task", "queue_dismiss_human_task",
                 "queue_set_product", "queue_restore"):
        assert name not in HANDLERS


def test_human_only_ops_unreachable_by_construction(wired):
    s = make_session(wired, "treasurer")
    try:
        for server, tool in (("ledger", "approve"), ("ledger", "record_income"),
                             ("queue", "resolve_human_task")):
            resp = send_and_wait(s, server, tool, {})
            assert resp["ok"] is False
    finally:
        s.cleanup()


def test_two_parallel_sessions_do_not_mix_identities(wired):
    s_builder = make_session(wired, "builder")
    s_treas = make_session(wired, "treasurer")
    try:
        (s_builder.ipc_dir / "requests" / "a.json").write_text(
            json.dumps({"server": "queue", "tool": "request_human_action",
                        "args": {"kind": "login", "title": "Need login",
                                 "instructions": "Do it.", "dedupe_key": "k1"}}),
            encoding="utf-8")
        (s_treas.ipc_dir / "requests" / "a.json").write_text(
            json.dumps({"server": "ledger", "tool": "list_pending", "args": {}}),
            encoding="utf-8")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if ((s_builder.ipc_dir / "responses" / "a.json").exists()
                    and (s_treas.ipc_dir / "responses" / "a.json").exists()):
                break
            time.sleep(0.02)
        r_builder = json.loads(
            (s_builder.ipc_dir / "responses" / "a.json").read_text(encoding="utf-8"))
        r_treas = json.loads(
            (s_treas.ipc_dir / "responses" / "a.json").read_text(encoding="utf-8"))
        assert r_builder["ok"] is True
        assert r_treas["ok"] is True
        task = wired["conn"].execute(
            "SELECT created_by FROM human_tasks WHERE dedupe_key='k1'").fetchone()
        assert task["created_by"] == "builder"  # not treasurer, not spoofed
    finally:
        s_builder.cleanup()
        s_treas.cleanup()


def test_experiment_gate_enforced_in_broker(wired):
    s = make_session(wired, "builder")
    try:
        resp = send_and_wait(s, "ledger", "request_spend", {
            "bucket": "experiment", "amount_eur": 1.0, "purpose": "x"})
        assert resp["result"]["status"] == "rejected"
        assert "venture_id" in resp["result"]["reason"]
    finally:
        s.cleanup()


def test_read_request_rejects_non_object():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "r.json"
        p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with pytest.raises(ValueError, match="shallow JSON object"):
            _read_request(p)