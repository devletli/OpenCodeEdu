import re
import sqlite3
import threading
import urllib.error
import urllib.parse
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
    store.add_human_task(kind="login", title="Log in to the storefront",
                         instructions="Open the dashboard URL and sign in.",
                         url="https://example.com/login",
                         dedupe_key="t-login", created_by="scout")
    store.add_human_task(kind="login", title="Second login",
                         instructions="Another account.",
                         dedupe_key="t-login-2", created_by="scout")
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8")


def csrf_from_confirm(body):
    m = re.search(r"name='csrf' value='([0-9a-f]+)'", body)
    assert m, "confirm page must carry a CSRF token"
    return m.group(1)


def test_resolve_db_path_prefers_env(tmp_path, monkeypatch):
    from kiraci.dashboard import resolve_db_path

    monkeypatch.delenv("KIRACI_DB", raising=False)
    assert resolve_db_path(tmp_path).endswith("kiraci.db")
    monkeypatch.setenv("KIRACI_DB", str(tmp_path / "custom.db"))
    assert resolve_db_path(tmp_path) == str(tmp_path / "custom.db")


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
    # POST / is still 405; only /human/<id>/done|dismiss accept POST.
    for method in ("PUT", "DELETE", "HEAD"):
        code, _, _ = get(url + "/", method=method)
        assert code == 405, method
    code, _, _ = get(url + "/", method="POST")
    assert code == 405
    code, _, _ = get(url + "/no-such-path", method="POST")
    assert code == 405


def test_human_pages_render(server):
    url, _ = server
    code, _, body = get(url + "/human")
    assert code == 200
    assert "Log in to the storefront" in body
    code, _, body = get(url + "/human/1")
    assert code == 200
    assert "Log in to the storefront" in body
    assert "name='csrf'" in body
    code, _, _ = get(url + "/human/999")
    assert code == 404


def test_human_post_needs_valid_csrf(server):
    url, _ = server
    code, _, _ = post_form(url + "/human/1/done", {"note": "x"})
    assert code == 403
    code, _, _ = post_form(url + "/human/1/done",
                            {"csrf": "0" * 32, "note": "x"})
    assert code == 403
    # Task is still open.
    _, _, body = get(url + "/human")
    assert "Log in to the storefront" in body


def test_human_done_flow(server):
    url, _ = server
    _, _, confirm = get(url + "/human/1")
    token = csrf_from_confirm(confirm)
    code, headers, _ = post_form(url + "/human/1/done",
                                 {"csrf": token, "note": "logged in"})
    assert code == 303
    assert headers.get("Location") == "/human"
    _, _, body = get(url + "/human")
    assert "Log in to the storefront" not in body
    assert "Second login" in body
    # Resolving twice fails: already resolved.
    code, _, _ = post_form(url + "/human/1/done",
                            {"csrf": token, "note": "again"})
    assert code == 404


def test_human_dismiss_flow(server):
    url, _ = server
    _, _, confirm = get(url + "/human/2")
    token = csrf_from_confirm(confirm)
    code, _, _ = post_form(url + "/human/2/dismiss",
                            {"csrf": token, "note": "not needed"})
    assert code == 303
    _, _, body = get(url + "/human")
    assert "Second login" not in body


def test_human_secret_note_rejected(server):
    url, _ = server
    _, _, confirm = get(url + "/human/2")
    token = csrf_from_confirm(confirm)
    code, _, _ = post_form(url + "/human/2/done",
                            {"csrf": token,
                             "note": "password: hunter2-secret"})
    assert code == 400
    _, _, body = get(url + "/human")
    assert "Second login" in body


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