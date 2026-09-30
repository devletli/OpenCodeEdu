import sqlite3

from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.migrate import CURRENT_SCHEMA_VERSION, migrate, schema_version
from kiraci.store import Store

#: v0.2 shape: no venture_id columns, old human_tasks kind list, no new tables.
V02_DDL = """
CREATE TABLE ledger (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    kind         TEXT NOT NULL CHECK (kind IN ('fund','income','expense','refund')),
    bucket       TEXT NOT NULL,
    delta_cents  INTEGER NOT NULL CHECK (delta_cents <> 0),
    agent        TEXT NOT NULL,
    ref          TEXT UNIQUE,
    note         TEXT NOT NULL DEFAULT ''
);
CREATE TRIGGER ledger_no_update
BEFORE UPDATE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER ledger_no_delete
BEFORE DELETE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TABLE approvals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    agent         TEXT NOT NULL,
    bucket        TEXT NOT NULL,
    amount_cents  INTEGER NOT NULL CHECK (amount_cents > 0),
    purpose       TEXT NOT NULL,
    tier          TEXT NOT NULL CHECK (tier IN ('auto','yellow','red','none')),
    status        TEXT NOT NULL CHECK (status IN ('pending','executed','rejected')),
    reason        TEXT NOT NULL DEFAULT '',
    decided_by    TEXT,
    decided_at    TEXT,
    entry_id      INTEGER REFERENCES ledger(id)
);
CREATE TABLE human_tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    kind          TEXT NOT NULL CHECK (kind IN
                  ('login','account_setup','identity_verification',
                   'payment_method_setup','secret_provisioning','red_tier_approval')),
    title         TEXT NOT NULL,
    instructions  TEXT NOT NULL,
    url           TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','dismissed')),
    created_by    TEXT NOT NULL,
    dedupe_key    TEXT NOT NULL UNIQUE,
    resolved_at   TEXT,
    note          TEXT NOT NULL DEFAULT ''
);
CREATE TABLE tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    agent         TEXT NOT NULL,
    title         TEXT NOT NULL,
    prompt        TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    priority      INTEGER NOT NULL DEFAULT 5,
    requires_review INTEGER NOT NULL DEFAULT 0,
    review        TEXT NOT NULL DEFAULT 'none',
    blocked_on    INTEGER REFERENCES human_tasks(id),
    not_before    TEXT,
    attempts      INTEGER NOT NULL DEFAULT 0,
    branch        TEXT,
    result_path   TEXT,
    result_summary TEXT NOT NULL DEFAULT '',
    created_by    TEXT NOT NULL
);
CREATE TABLE runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    agent         TEXT NOT NULL,
    task_id       INTEGER,
    model         TEXT NOT NULL DEFAULT '',
    est_cost_cents INTEGER NOT NULL DEFAULT 0,
    duration_s    REAL NOT NULL DEFAULT 0,
    exit_code     INTEGER,
    status        TEXT NOT NULL
);
CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def make_v02_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(V02_DDL)
    conn.execute(
        "INSERT INTO ledger(kind,bucket,delta_cents,agent,ref,note)"
        " VALUES ('fund','infra',3000,'system','genesis:infra','genesis')")
    conn.execute(
        """INSERT INTO human_tasks(kind,title,instructions,created_by,dedupe_key)
           VALUES ('login','Need login','Do it.','scout','k1')""")
    conn.execute(
        """INSERT INTO tasks(agent,title,prompt,status,blocked_on,created_by)
           VALUES ('scout','T','p','blocked',1,'brain')""")
    conn.commit()
    return conn


def _columns(conn, table):
    return [(r["name"], r["type"]) for r in conn.execute(f"PRAGMA table_info({table})")]


def test_migrate_upgrades_v02_shape():
    conn = make_v02_db()
    assert schema_version(conn) == 2
    assert migrate(conn) == CURRENT_SCHEMA_VERSION == 3
    assert schema_version(conn) == 3
    assert "venture_id" in [n for n, _ in _columns(conn, "ledger")]
    assert "venture_id" in [n for n, _ in _columns(conn, "approvals")]
    # old rows kept
    assert conn.execute("SELECT COUNT(*) c FROM ledger").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM human_tasks").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"] == 1
    # new kind accepted
    conn.execute(
        """INSERT INTO human_tasks(kind,title,instructions,created_by,dedupe_key)
           VALUES ('logged_in_action','Publish','Steps.','orchestrator','pub:1')""")
    conn.commit()
    # blocked task still resolves through the rebuilt table
    store = Store(conn)
    assert store.resolve_human_task(1)["status"] == "done"
    assert store.get_task(1)["status"] == "pending"


def test_ledger_stays_append_only_after_migrate():
    conn = make_v02_db()
    migrate(conn)
    for sql in ("DELETE FROM ledger", "UPDATE ledger SET delta_cents = 1"):
        try:
            conn.execute(sql)
        except sqlite3.DatabaseError:
            continue
        raise AssertionError(f"append-only broken: {sql}")


def test_migrate_twice_changes_nothing():
    conn = make_v02_db()
    migrate(conn)

    def snapshot(c):
        tables = ["ledger", "approvals", "human_tasks", "tasks", "runs", "kv",
                  "ventures", "payments"]
        out = {}
        for t in tables:
            out[t] = _columns(c, t)
            out[t + ":n"] = c.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
        return out

    before = snapshot(conn)
    assert migrate(conn) == 3
    assert snapshot(conn) == before


def test_fresh_db_has_same_shape():
    fresh = connect(":memory:")
    migrated = make_v02_db()
    migrate(migrated)
    tables = ["ledger", "approvals", "human_tasks", "tasks", "runs", "kv",
              "ventures", "payments"]
    for t in tables:
        assert _columns(fresh, t) == _columns(migrated, t), t
    assert schema_version(fresh) == 3


def test_venture_id_flows_to_ledger_and_approvals():
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    r = ledger.request_spend("builder", "infra", 100, "x", venture_id=7)
    assert r["status"] == "approved"
    row = conn.execute("SELECT venture_id FROM ledger WHERE id=?",
                       (r["entry_id"],)).fetchone()
    assert row["venture_id"] == 7
    p = ledger.request_spend("builder", "infra", 500, "y", venture_id=7)
    assert p["status"] == "pending"
    ledger.approve(p["approval_id"], "dev")
    row = conn.execute("SELECT venture_id FROM ledger ORDER BY id DESC LIMIT 1"
                       ).fetchone()
    assert row["venture_id"] == 7


def test_record_refund_mirrors_split_and_goes_negative():
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    assert ledger.record_income(1000, "o1")["status"] == "recorded"
    out = ledger.record_refund(1000, "refund:o1", "customer refund")
    assert out == {"status": "recorded", "experiment": -500,
                   "emergency": -300, "owner": -200}
    assert ledger.record_refund(1000, "refund:o1", "again")["status"] == "duplicate"
    kinds = [r["kind"] for r in conn.execute(
        "SELECT kind FROM ledger WHERE ref LIKE 'refund:o1:%' ORDER BY id")]
    assert kinds == ["refund", "refund", "refund"]
    assert ledger.balances()["experiment"] == 2500 + 500 - 500
    # refunds may push a bucket negative while spends still cannot
    big = ledger.record_refund(10000, "refund:big", "whale")
    assert big["status"] == "recorded"
    assert ledger.balances()["experiment"] < 0
    assert ledger.request_spend("a", "experiment", 100, "x")["status"] == "rejected"
