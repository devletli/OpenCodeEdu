from __future__ import annotations

import sqlite3

from .ledger import entry_hash

#: Missing kv value means a v0.2 database.
V02_VERSION = 2
V03_VERSION = 3
V04_VERSION = 4
CURRENT_SCHEMA_VERSION = 5

#: Exact trigger SQL; verify.py checks these exist verbatim.
APPEND_ONLY_TRIGGERS = (
    ("ledger_no_update",
     ("CREATE TRIGGER ledger_no_update\n"
      "BEFORE UPDATE ON ledger\n"
      "BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END")),
    ("ledger_no_delete",
     ("CREATE TRIGGER ledger_no_delete\n"
      "BEFORE DELETE ON ledger\n"
      "BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END")),
)

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


IDEMPOTENCY_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS idempotency_keys ("
    "key TEXT PRIMARY KEY,"
    "result TEXT NOT NULL,"
    "ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
    ")"
)

FREEZE_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS freeze_state ("
    "id INTEGER PRIMARY KEY CHECK (id = 1),"
    "frozen INTEGER NOT NULL DEFAULT 0 CHECK (frozen IN (0, 1))"
    ")"
)


def migrate(conn: sqlite3.Connection) -> int:
    """Upgrade a v0.2/v0.3/v0.4 database to the current shape. Idempotent.

    v2->v3: venture_id columns, human_tasks CHECK rebuild, ventures+payments.
    v3->v4: the ledger hash chain. The backfill rewrites every row in id order
    inside ONE transaction; the two append-only triggers are dropped and
    recreated here - the only place allowed to do that. Fresh databases (from
    the updated SCHEMA strings) only get the version stamp: every step below
    detects the new shape and skips itself.
    v4->v5: idempotency_keys + freeze_state tables (plain creates, no backfill).
    """
    if schema_version(conn) >= CURRENT_SCHEMA_VERSION:
        return CURRENT_SCHEMA_VERSION
    conn.execute("BEGIN IMMEDIATE")
    try:
        # NOTE: only conn.execute below, never executescript: executescript
        # implicitly commits pending transactions, which would break the
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
        if "hash" not in _columns(conn, "ledger"):
            conn.execute("ALTER TABLE ledger ADD COLUMN hash TEXT")
            _backfill_hash_chain(conn)
        conn.execute(IDEMPOTENCY_SCHEMA)
        conn.execute(FREEZE_SCHEMA)
        conn.execute(
            "INSERT INTO kv(key,value) VALUES ('schema_version','5') "
            "ON CONFLICT(key) DO UPDATE SET value='5'")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return CURRENT_SCHEMA_VERSION


def _backfill_hash_chain(conn: sqlite3.Connection) -> None:
    """Drop the append-only triggers, backfill the chain, recreate them."""
    conn.execute("DROP TRIGGER IF EXISTS ledger_no_update")
    conn.execute("DROP TRIGGER IF EXISTS ledger_no_delete")
    prev = ""
    rows = conn.execute(
        "SELECT id, ts, kind, bucket, delta_cents, agent, ref, note, venture_id"
        " FROM ledger ORDER BY id").fetchall()
    for r in rows:
        h = entry_hash(prev, r["ts"], r["kind"], r["bucket"], r["delta_cents"],
                       r["agent"], r["ref"], r["note"], r["venture_id"])
        conn.execute("UPDATE ledger SET hash=? WHERE id=?", (h, r["id"]))
        prev = h
    for name, sql in APPEND_ONLY_TRIGGERS:
        conn.execute(sql)
