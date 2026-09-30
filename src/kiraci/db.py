from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .store import QUEUE_SCHEMA

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    kind         TEXT NOT NULL CHECK (kind IN ('fund','income','expense','refund')),
    bucket       TEXT NOT NULL,
    delta_cents  INTEGER NOT NULL CHECK (delta_cents <> 0),
    agent        TEXT NOT NULL,
    ref          TEXT UNIQUE,
    note         TEXT NOT NULL DEFAULT ''
);

CREATE TRIGGER IF NOT EXISTS ledger_no_update
BEFORE UPDATE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;

CREATE TRIGGER IF NOT EXISTS ledger_no_delete
BEFORE DELETE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;

CREATE TABLE IF NOT EXISTS approvals (
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

CREATE INDEX IF NOT EXISTS idx_ledger_bucket ON ledger(bucket);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or os.environ.get("KIRACI_DB", "data/kiraci.db")
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.executescript(QUEUE_SCHEMA)
    return conn
