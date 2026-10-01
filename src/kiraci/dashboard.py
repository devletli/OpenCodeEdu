"""Read-only observability dashboard. stdlib http.server only.

Binds to 127.0.0.1 ONLY (hard-coded, no option to change) - access it through
an SSH tunnel. GET is the only allowed method; the database is opened
read-only (mode=ro URI); when that fails under WAL while the daemon writes, a
cached in-memory copy made with the backup API every 10 seconds is served.
Every dynamic value is html.escape()d: agent output is untrusted. No
JavaScript. Resolves/dismisses/approvals do NOT exist here by design.
"""

from __future__ import annotations

import html
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CACHE_REFRESH_S = 10

STYLE = ("body{font-family:system-ui,sans-serif;margin:1.5rem;background:#fafafa}"
         "table{border-collapse:collapse;width:100%;margin:.5rem 0}"
         "td,th{border:1px solid #ccc;padding:.25rem .5rem;text-align:left}"
         "th{background:#eee}h1{font-size:1.2rem}h2{font-size:1rem;margin-top:1rem}"
         "pre{white-space:pre-wrap;background:#fff;border:1px solid #ddd;padding:.5rem}")


class DashboardState:
    """Read-only database access with a WAL-safe in-memory fallback."""

    def __init__(self, db_path: str, root: Path):
        self.db_path = str(db_path)
        self.root = Path(root)
        self._lock = threading.Lock()
        self._cache: sqlite3.Connection | None = None
        self._cache_ts = 0.0

    def conn(self) -> sqlite3.Connection:
        uri = f"file:{self.db_path}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=2)
            conn.row_factory = sqlite3.Row
            conn.execute("SELECT 1 FROM kv LIMIT 1").fetchone()
            return conn
        except sqlite3.Error:
            return self._cached_conn()

    def _cached_conn(self) -> sqlite3.Connection:
        import time
        with self._lock:
            now = time.monotonic()
            if self._cache is None or now - self._cache_ts > CACHE_REFRESH_S:
                if self._cache is not None:
                    self._cache.close()
                    self._cache = None
                fresh = sqlite3.connect(":memory:")
                fresh.row_factory = sqlite3.Row
                try:
                    src = sqlite3.connect(self.db_path)
                    try:
                        src.backup(fresh)
                    finally:
                        src.close()
                    self._cache = fresh
                    self._cache_ts = now
                except sqlite3.Error:
                    fresh.close()
                    raise
            return self._cache

    # ---------- page data ----------
    def overview(self) -> dict:
        conn = self.conn()
        try:
            kv = {r["key"]: r["value"] for r in conn.execute("SELECT key,value FROM kv")}
            balances = {r["bucket"]: int(r["s"]) for r in conn.execute(
                "SELECT bucket, COALESCE(SUM(delta_cents),0) s FROM ledger"
                " GROUP BY bucket")}
            runs = [dict(r) for r in conn.execute(
                "SELECT id, ts, agent, task_id, est_cost_cents, status FROM runs"
                " ORDER BY id DESC LIMIT 20")]
            ventures = [dict(r) for r in conn.execute(
                "SELECT id, name, status, score FROM ventures ORDER BY id")]
            payments = [dict(r) for r in conn.execute(
                "SELECT provider, order_id, currency, gross_cents, status FROM"
                " payments WHERE status IN ('fx_unhandled','ignored') ORDER BY id")]
            human = [dict(r) for r in conn.execute(
                "SELECT id, kind, title, status FROM human_tasks"
                " WHERE status='open' ORDER BY id")]
            return {"kv": kv, "balances": balances, "runs": runs,
                    "ventures": ventures, "payments": payments, "human": human,
                    "spend": self.spend_breakdown()}
        finally:
            conn.close()

    def ledger_rows(self, limit: int = 200) -> list[dict]:
        conn = self.conn()
        try:
            return [dict(r) for r in conn.execute(
                "SELECT id, ts, kind, bucket, delta_cents, agent, ref, note"
                " FROM ledger ORDER BY id DESC LIMIT ?", (limit,))]
        finally:
            conn.close()

    def task_rows(self) -> list[dict]:
        conn = self.conn()
        try:
            return [dict(r) for r in conn.execute(
                "SELECT id, ts, agent, title, status, priority, attempts,"
                " result_summary FROM tasks ORDER BY id DESC LIMIT 100")]
        finally:
            conn.close()

    def research_files(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        rdir = self.root / "research"
        if rdir.is_dir():
            for p in sorted(rdir.glob("*.md")):
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")[:500]
                except OSError:
                    continue
                out.append((p.name, text))
        return out

    def spend_breakdown(self) -> dict:
        """Where the money went: expenses grouped by bucket and by agent."""
        conn = self.conn()
        try:
            by_bucket = [dict(r) for r in conn.execute(
                "SELECT bucket, SUM(-delta_cents) s, COUNT(*) n FROM ledger"
                " WHERE kind='expense' GROUP BY bucket ORDER BY s DESC")]
            by_agent = [dict(r) for r in conn.execute(
                "SELECT agent, SUM(-delta_cents) s, COUNT(*) n FROM ledger"
                " WHERE kind='expense' GROUP BY agent ORDER BY s DESC")]
            return {"by_bucket": by_bucket, "by_agent": by_agent}
        finally:
            conn.close()

    def agent_activity(self) -> list[dict]:
        """Every agent: total spend, recent runs, tasks and their outcomes."""
        conn = self.conn()
        try:
            agents = [r["agent"] for r in conn.execute(
                "SELECT agent, COALESCE(SUM(-delta_cents),0) s FROM ("
                "SELECT agent, delta_cents FROM ledger UNION ALL"
                " SELECT agent, 0 FROM tasks UNION ALL"
                " SELECT agent, 0 FROM runs) GROUP BY agent ORDER BY s DESC")]
            out = []
            for a in agents:
                spend = int(conn.execute(
                    "SELECT COALESCE(SUM(-delta_cents),0) s FROM ledger"
                    " WHERE kind='expense' AND agent=?", (a,)).fetchone()["s"])
                runs = [dict(r) for r in conn.execute(
                    "SELECT id, ts, est_cost_cents, duration_s, exit_code,"
                    " status FROM runs WHERE agent=? ORDER BY id DESC LIMIT 10",
                    (a,))]
                tasks = [dict(r) for r in conn.execute(
                    "SELECT id, title, status, attempts, result_summary"
                    " FROM tasks WHERE agent=? ORDER BY id DESC LIMIT 20", (a,))]
                out.append({"agent": a, "spend_cents": spend,
                            "runs": runs, "tasks": tasks})
            return out
        finally:
            conn.close()


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return (f"<table><tr>{head}</tr>{body}</table>" if body
            else "<p><em>empty</em></p>")


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def render_overview(data: dict) -> str:
    balances = " ".join(f"{k}: {v / 100:.2f}" for k, v in sorted(data["balances"].items()))
    total = sum(v for k, v in data["balances"].items() if k != "owner")
    kv = data["kv"]
    rows = [
        ["Balances (EUR)", esc(balances)],
        ["Total ex-owner (EUR)", esc(total / 100)],
        ["Last tick", esc(kv.get("last_tick", "never"))],
        ["Sandbox notice day", esc(kv.get("sandbox_notice_day", "-"))],
        ["Paid paused until", esc(kv.get("paid_paused_until", "-"))],
        ["Cost multiplier", esc(kv.get("cost_multiplier", "1.0"))],
        ["Last reconcile", esc(kv.get("last_reconcile", "never"))],
        ["Last backup", esc(kv.get("last_backup", "never"))],
        ["Last verify", esc(kv.get("last_verify", "never"))],
    ]
    out = ["<h1>Kiraci overview</h1>", _table(["", "value"], rows),
           "<h2>Where the money went</h2>",
           _table(["bucket", "spent (EUR)", "entries"],
                  [[esc(r["bucket"]), esc(r["s"] / 100), esc(r["n"])]
                   for r in data["spend"]["by_bucket"]]),
           _table(["agent", "spent (EUR)", "entries"],
                  [[esc(r["agent"]), esc(r["s"] / 100), esc(r["n"])]
                   for r in data["spend"]["by_agent"]]),
           "<h2>Open human tasks</h2>",
           _table(["id", "kind", "title"],
                  [[esc(t["id"]), esc(t["kind"]), esc(t["title"])]
                   for t in data["human"]]),
           "<h2>Ventures</h2>",
           _table(["id", "name", "status", "score"],
                  [[esc(v["id"]), esc(v["name"]), esc(v["status"]), esc(v["score"])]
                   for v in data["ventures"]]),
           "<h2>Payments needing attention</h2>",
           _table(["provider", "order", "currency", "gross", "status"],
                  [[esc(p["provider"]), esc(p["order_id"]), esc(p["currency"]),
                    esc(p["gross_cents"]), esc(p["status"])] for p in data["payments"]]),
           "<h2>Last 20 runs</h2>",
           _table(["id", "ts", "agent", "task", "est cost", "status"],
                  [[esc(r["id"]), esc(r["ts"]), esc(r["agent"]), esc(r["task_id"]),
                    esc(r["est_cost_cents"]), esc(r["status"])] for r in data["runs"]])]
    return "\n".join(out)


def render_agents(data: list[dict]) -> str:
    out = ["<h1>Agents - what they did</h1>"]
    for a in data:
        spent = esc(f"{a['spend_cents'] / 100:.2f}")
        out.append(f"<h2>{esc(a['agent'])} (spent {spent} EUR)</h2>")
        out.append("<h3>Runs</h3>")
        out.append(_table(
            ["id", "ts", "est cost (c)", "duration (s)", "exit", "status"],
            [[esc(r["id"]), esc(r["ts"]), esc(r["est_cost_cents"]),
              esc(round(r["duration_s"], 1)), esc(r["exit_code"]), esc(r["status"])]
             for r in a["runs"]]))
        out.append("<h3>Tasks</h3>")
        out.append(_table(
            ["id", "title", "status", "attempts", "result"],
            [[esc(t["id"]), esc(t["title"]), esc(t["status"]),
              esc(t["attempts"]), esc((t["result_summary"] or "")[:200])]
             for t in a["tasks"]]))
    return "\n".join(out)


class DashboardHandler(BaseHTTPRequestHandler):
    state: DashboardState

    def _page(self, body: str, code: int = 200) -> None:
        nav = ("<p><a href='/'>overview</a> | <a href='/agents'>agents</a> | "
               "<a href='/ledger'>ledger</a> | <a href='/tasks'>tasks</a> | "
               "<a href='/research'>research</a></p>")
        doc = (f"<!doctype html><html><head><meta charset='utf-8'>"
               f"<title>kiraci</title><style>{STYLE}</style></head>"
               f"<body>{nav}{body}</body></html>")
        raw = doc.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        try:
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._page(render_overview(self.state.overview()))
            elif path == "/agents":
                self._page(render_agents(self.state.agent_activity()))
            elif path == "/ledger":
                rows = self.state.ledger_rows()
                self._page(
                    "<h1>Ledger (last 200)</h1>" + _table(
                        ["id", "ts", "kind", "bucket", "delta", "agent", "ref",
                         "note"],
                        [[esc(r["id"]), esc(r["ts"]), esc(r["kind"]), esc(r["bucket"]),
                          esc(r["delta_cents"]), esc(r["agent"]), esc(r["ref"]),
                          esc(r["note"])] for r in rows]))
            elif path == "/tasks":
                rows = self.state.task_rows()
                self._page(
                    "<h1>Tasks</h1>" + _table(
                        ["id", "ts", "agent", "title", "status", "prio", "att",
                         "summary"],
                        [[esc(r["id"]), esc(r["ts"]), esc(r["agent"]), esc(r["title"]),
                          esc(r["status"]), esc(r["priority"]), esc(r["attempts"]),
                          esc(r["result_summary"])] for r in rows]))
            elif path == "/research":
                items = self.state.research_files()
                parts = ["<h1>Research</h1>"]
                for name, text in items:
                    parts.append(f"<h2>{esc(name)}</h2><pre>{esc(text)}</pre>")
                self._page("\n".join(parts))
            else:
                self._page("<h1>404</h1>", code=404)
        except (sqlite3.Error, ValueError, KeyError) as e:
            self._page(f"<h1>database error</h1><pre>{esc(e)}</pre>", code=500)

    def do_POST(self) -> None:
        self._method_not_allowed()

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def do_HEAD(self) -> None:
        self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:  # quiet: no stdout spam
        pass


def make_server(state: DashboardState, port: int) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (DashboardHandler,), {"state": state})
    # Loopback ONLY: hard-coded, never configurable.
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(root: Path, config) -> None:
    port = int(config.ops_value("dashboard_port"))
    db_path = str(Path(root) / "data" / "kiraci.db")
    srv = make_server(DashboardState(db_path, root), port)
    print(f"kiraci dashboard on http://127.0.0.1:{port} (loopback only)")
    srv.serve_forever()