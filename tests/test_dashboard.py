import sqlite3
import threading
import urllib.error
import urllib.request

import pytest

from kiraci.dashboard import DashboardState, make_server
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.store import Store


@pytest.fixture
def server(tmp_path):
    db = str(tmp_path / "d.db")
    conn = connect(db)
    ledger = Ledger(conn)
    ledger.init_genesis()
    store = Store(conn)
    store.create_task(agent="scout", title="Evil <script>alert(1)</script>",
                      prompt="x", created_by="brain")
    conn.close()
    state = DashboardState(db, tmp_path)
    srv = make_server(state, 0)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{port}", srv
    srv.shutdown()
    srv.server_close()


def get(url, method="GET"):
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8")


def test_binds_loopback_only(tmp_path):
    state = DashboardState(str(tmp_path / "none.db"), tmp_path)
    srv = make_server(state, 0)
    try:
        host, _port = srv.server_address[:2]
        assert host == "127.0.0.1"
    finally:
        srv.server_close()


def test_get_pages_render(server):
    url, _ = server
    for path in ("/", "/ledger", "/tasks", "/research", "/agents"):
        code, _headers, body = get(url + path)
        assert code == 200, path
        assert "kiraci" in body


def test_agents_page_shows_spend_and_tasks(server):
    url, _ = server
    _, _, body = get(url + "/agents")
    assert "Agents - what they did" in body
    assert "spent" in body


def test_non_get_methods_return_405(server):
    url, _ = server
    for method in ("POST", "PUT", "DELETE", "HEAD"):
        code, _, _ = get(url + "/", method=method)
        assert code == 405, method


def test_database_connection_is_read_only(tmp_path):
    db = str(tmp_path / "d.db")
    connect(db).close()
    state = DashboardState(db, tmp_path)
    conn = state.conn()
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "INSERT INTO kv(key,value) VALUES ('x','y')")
    finally:
        conn.close()


def test_script_in_task_result_is_escaped(server):
    url, _ = server
    _, _, body = get(url + "/tasks")
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_security_headers_present(server):
    url, _ = server
    code, headers, _ = get(url + "/")
    assert code == 200
    assert headers["Content-Security-Policy"] == \
        "default-src 'none'; style-src 'unsafe-inline'"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Cache-Control"] == "no-store"


def test_overview_shows_balances_and_runs(server):
    url, _ = server
    _, _, body = get(url + "/")
    assert "infra" in body and "Last 20 runs" in body


def test_cache_fallback_when_readonly_open_fails(tmp_path, monkeypatch):
    """Under WAL the mode=ro open can fail; state then serves a backup copy."""
    db = str(tmp_path / "d.db")
    conn = connect(db)
    Ledger(conn).init_genesis()
    conn.close()
    state = DashboardState(db, tmp_path)

    import kiraci.dashboard as dash

    real_connect = sqlite3.connect

    def fake_connect(path, *a, **k):
        if isinstance(path, str) and "mode=ro" in path:
            raise sqlite3.OperationalError("readonly unavailable")
        return real_connect(path, *a, **k)

    monkeypatch.setattr(dash.sqlite3, "connect", fake_connect)
    data = state.overview()  # falls back to the in-memory backup copy
    assert data["balances"]["infra"] == 3000