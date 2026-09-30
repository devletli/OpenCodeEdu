from __future__ import annotations

import sqlite3

#: Missing kv value means a v0.2 database.
V02_VERSION = 2
CURRENT_SCHEMA_VERSION = 3

HUMAN_TASKS_COLUMNS = (
    "id", "ts", "kind", "title", "instructions", "url", "status",
    "created_by", "dedupe_key", "resolved_at", "note",
)

HUMAN_TASKS_NEW = (
    "CREATE TABLE human_tasks_new ("
    "id            INTEGER PRIMARY KEY AUTOINCREMENT,"
    "ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),"
    "kind          TEXT NOT NULL CHECK (kind IN"
    " ('login','account_setup','identity_verification',"
    " 'payment_method_setup','secret_provisioning','red_tier_approval',"
    " 'logged_in_action')),"
    "title         TEXT NOT NULL,"
    "instructions  TEXT NOT NULL,"
    "url           TEXT NOT NULL DEFAULT '',"
    "status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','dismissed')),"
    "created_by    TEXT NOT NULL,"
    "dedupe_key    TEXT NOT NULL UNIQUE,"
    "resolved_at   TEXT,"
    "note          TEXT NOT NULL DEFAULT ''"
    ")"
)

VENTURES_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS ventures ("
    "id            INTEGER PRIMARY KEY AUTOINCREMENT,"
    "ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),"
    "updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),"
    "name          TEXT NOT NULL UNIQUE,"
    "slug          TEXT NOT NULL UNIQUE,"
    "kind          TEXT NOT NULL CHECK (kind IN"
    " ('digital_product','bounty','report','micro_saas','other')),"
    "hypothesis    TEXT NOT NULL,"
    "score         REAL NOT NULL CHECK (score BETWEEN 0 AND 10),"
    "status        TEXT NOT NULL DEFAULT 'researching' CHECK (status IN"
    " ('researching','validating','building','live','paused','dead')),"
    "evidence      TEXT NOT NULL,"
    "external_product_id TEXT,"
    "death_note    TEXT NOT NULL DEFAULT ''"
    ")"
)

PAYMENTS_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS payments ("
    "id            INTEGER PRIMARY KEY AUTOINCREMENT,"
    "ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),"
    "provider      TEXT NOT NULL,"
    "order_id      TEXT NOT NULL,"
    "product_id    TEXT NOT NULL DEFAULT '',"
    "venture_id    INTEGER REFERENCES ventures(id),"
    "currency      TEXT NOT NULL,"
    "gross_cents   INTEGER NOT NULL,"
    "recorded_cents INTEGER NOT NULL DEFAULT 0,"
    "status        TEXT NOT NULL CHECK (status IN"
    " ('recorded','fx_unhandled','refunded','refund_recorded','ignored')),"
    "UNIQUE (provider, order_id)"
    ")"
)


def schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM kv WHERE key='schema_version'").fetchone()
    return int(row["value"]) if row else V02_VERSION


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _human_tasks_has_logged_in_action(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='human_tasks'").fetchone()
    return row is not None and "logged_in_action" in (row["sql"] or "")


def migrate(conn: sqlite3.Connection) -> int:
    """Upgrade a v0.2 database to the v0.3 shape. Idempotent.

    Runs in a single transaction. Returns the resulting schema version.
    Fresh databases (created from the updated SCHEMA strings) only get the
    version stamp: every step below detects the new shape and skips itself.
    """
    if schema_version(conn) >= CURRENT_SCHEMA_VERSION:
        return CURRENT_SCHEMA_VERSION
    conn.execute("BEGIN IMMEDIATE")
    try:
        # NOTE: only conn.execute below, never executescript: executescript
        # implicitly commits any pending transaction, which would break the
        # single-transaction guarantee (and the final COMMIT).
        if "venture_id" not in _columns(conn, "ledger"):
                conn.execute("ALTER TABLE ledger ADD COLUMN venture_id INTEGER")
        if "venture_id" not in _columns(conn, "approvals"):
            conn.execute("ALTER TABLE approvals ADD COLUMN venture_id INTEGER")
        if not _human_tasks_has_logged_in_action(conn):
            # SQLite cannot alter a CHECK: build the new table under a temp
            # name, copy, drop, rename. tasks.blocked_on keeps pointing at
            # "human_tasks" because nothing ever references the temp name.
            conn.execute(HUMAN_TASKS_NEW)
            cols = ", ".join(HUMAN_TASKS_COLUMNS)
            conn.execute(
                f"INSERT INTO human_tasks_new ({cols}) SELECT {cols} FROM human_tasks")
            conn.execute("DROP TABLE human_tasks")
            conn.execute("ALTER TABLE human_tasks_new RENAME TO human_tasks")
        conn.execute(VENTURES_SCHEMA)
        conn.execute(PAYMENTS_SCHEMA)
        conn.execute(
            "INSERT INTO kv(key,value) VALUES ('schema_version','3') "
            "ON CONFLICT(key) DO UPDATE SET value='3'")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return CURRENT_SCHEMA_VERSION
