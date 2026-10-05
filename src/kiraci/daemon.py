"""Snapshot daemon persistence (TASK2.md Phase 1.2).

Runtime journal/research/product artifacts are recorded in a local SQLite
database instead of committing them to git on the main branch. The git
snapshot in the orchestrator is kept for backward compatibility but the
SQLite record is the durable local log.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS daemon_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    module TEXT NOT NULL,
    payload JSON NOT NULL
);
"""


def default_db_path() -> Path:
    override = os.environ.get("KIRACI_STATE_DB")
    if override:
        return Path(override)
    return Path("data/state.db")


def init_db(db_path: Path | str | None = None) -> Path:
    path = Path(db_path) if db_path is not None else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path), timeout=10) as conn:
        conn.execute(SCHEMA)
        conn.commit()
    return path


def save_snapshot(
    module: str,
    payload: dict[str, Any],
    db_path: Path | str | None = None,
) -> int:
    """Persist one snapshot record. Returns the row id."""
    if not module:
        raise ValueError("module is required")
    path = init_db(db_path)
    with sqlite3.connect(str(path), timeout=10) as conn:
        cur = conn.execute(
            "INSERT INTO daemon_snapshots (module, payload) VALUES (?, ?)",
            (module, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
        row_id = cur.lastrowid
        assert row_id is not None  # INSERT always yields a row id
        return int(row_id)


def list_snapshots(
    limit: int = 50,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Most recent snapshot records, newest first."""
    path = init_db(db_path)
    limit = max(1, min(limit, 500))
    with sqlite3.connect(str(path), timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, timestamp, module, payload FROM daemon_snapshots"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
