import json
import sqlite3
import threading
import time

import pytest

from kiraci import ipc
from kiraci.ipc import IpcError


@pytest.fixture
def ipc_root(tmp_path):
    root = tmp_path / "ipc"
    (root / "requests").mkdir(parents=True)
    (root / "responses").mkdir(parents=True)
    return root


def _fake_broker(root: object, result, delay: float = 0.0) -> threading.Thread:
    def worker():
        deadline = time.monotonic() + 5
        req = None
        while time.monotonic() < deadline:
            found = sorted((root / "requests").glob("*.json"))
            if found:
                req = found[0]
                break
            time.sleep(0.01)
        if req is None:
            return
        time.sleep(delay)
        json.loads(req.read_text(encoding="utf-8"))
        (root / "responses" / req.name).write_text(
            json.dumps({"ok": True, "result": result}), encoding="utf-8")
        req.unlink()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t


def test_call_roundtrip_reads_response(ipc_root):
    _fake_broker(ipc_root, {"status": "approved", "approval_id": 1})
    out = ipc.call("ledger", "request_spend",
                   {"bucket": "tokens", "amount_eur": 0.5, "purpose": "x"},
                   ipc_path=ipc_root)
    assert out == {"status": "approved", "approval_id": 1}


def test_request_is_written_atomically(ipc_root):
    _fake_broker(ipc_root, {"ok": 1})
    ipc.call("ledger", "get_balances", {}, ipc_path=ipc_root)
    leftovers = list((ipc_root / "requests").glob(".*"))
    assert leftovers == []  # no temp files left behind


def test_error_response_raises_clear_error(ipc_root):
    def worker():
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            found = sorted((ipc_root / "requests").glob("*.json"))
            if found:
                break
            time.sleep(0.01)
        req = found[0]
        (ipc_root / "responses" / req.name).write_text(
            json.dumps({"ok": False, "error": "tool not allowed"}), encoding="utf-8")

    threading.Thread(target=worker, daemon=True).start()
    with pytest.raises(ipc.IpcError, match="not allowed"):
        ipc.call("ledger", "approve", {}, ipc_path=ipc_root)


def test_timeout_gives_clear_error(ipc_root):
    t0 = time.monotonic()
    with pytest.raises(ipc.IpcError, match="did not answer"):
        ipc.call("ledger", "get_balances", {}, ipc_path=ipc_root, timeout_s=0.3)
    assert time.monotonic() - t0 >= 0.2


def test_missing_ipc_dir_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("KIRACI_IPC_DIR", raising=False)
    with pytest.raises(IpcError, match="KIRACI_IPC_DIR"):
        ipc.call("ledger", "get_balances", {}, ipc_path=None)


def test_missing_directories_are_a_clear_error(tmp_path):
    with pytest.raises(ipc.IpcError, match="missing"):
        ipc.call("ledger", "get_balances", {}, ipc_path=tmp_path / "nope")


def test_importing_mcp_clients_never_opens_a_database(monkeypatch):
    called = []
    real_connect = sqlite3.connect

    def spy(*args, **kwargs):
        called.append(args)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spy)
    import importlib

    from kiraci import mcp_server, queue_mcp

    importlib.reload(mcp_server)
    importlib.reload(queue_mcp)
    assert called == []


def test_mcp_tools_keep_real_signatures():
    """FastMCP builds schemas by signature introspection: a *args/**kwargs
    guard wrapper would leak 'args'/'kwargs' as required fields (found live)."""
    import inspect

    from kiraci import mcp_server, queue_mcp

    assert list(inspect.signature(mcp_server.get_balances).parameters) == []
    assert list(inspect.signature(mcp_server.request_spend).parameters)[:4] == \
        ["agent", "bucket", "amount_eur", "purpose"]
    assert list(inspect.signature(mcp_server.list_pending).parameters) == []
    assert "caller" in inspect.signature(queue_mcp.create_task).parameters
    assert list(inspect.signature(queue_mcp.list_ventures).parameters) == \
        ["status"]


def test_guard_returns_error_dict_on_ipc_error(monkeypatch):
    from kiraci import ipc, mcp_server

    def boom(server, tool, args, **kwargs):
        raise ipc.IpcError("broker did not answer x")

    monkeypatch.setattr(mcp_server, "call", boom)
    out = mcp_server.get_balances()
    assert out == {"status": "error", "reason": "broker did not answer x"}


def test_list_tools_reraise_ipc_error(monkeypatch):
    """List-typed tools must never return an error dict: it violates their
    MCP output schema (seen live: list_ventures returned {'status': ...}
    and FastMCP raised a validation error). IpcError propagates instead,
    which FastMCP turns into a proper retryable tool error."""
    from kiraci import ipc, mcp_server, queue_mcp

    def boom(server, tool, args, **kwargs):
        raise ipc.IpcError("broker did not answer x")

    monkeypatch.setattr(mcp_server, "call", boom)
    monkeypatch.setattr(queue_mcp, "call", boom)
    for fn in (mcp_server.list_pending, mcp_server.recent_entries,
               queue_mcp.list_tasks, queue_mcp.list_human_tasks,
               queue_mcp.list_ventures):
        with pytest.raises(ipc.IpcError, match="did not answer"):
            fn()