"""Tests for the SQLite snapshot daemon log (TASK2 Phase 1.2)."""

import sqlite3

import pytest

from kiraci.daemon import default_db_path, init_db, list_snapshots, save_snapshot


def test_init_db_creates_table_and_is_idempotent(tmp_path):
    db = tmp_path / "state.db"
    assert init_db(db) == db
    assert init_db(db) == db
    conn = sqlite3.connect(db)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(daemon_snapshots)")]
        assert {"id", "timestamp", "module", "payload"} <= set(cols)
    finally:
        conn.close()


def test_save_and_list_roundtrip(tmp_path):
    db = tmp_path / "state.db"
    first = save_snapshot("git_snapshot", {"date": "2026-01-01"}, db)
    second = save_snapshot("git_snapshot", {"date": "2026-01-02"}, db)
    assert second == first + 1
    rows = list_snapshots(db_path=db)
    assert [r["id"] for r in rows] == [second, first]  # newest first
    assert rows[0]["module"] == "git_snapshot"


def test_list_limit_bounds(tmp_path):
    db = tmp_path / "state.db"
    for i in range(5):
        save_snapshot("m", {"i": i}, db)
    assert len(list_snapshots(limit=2, db_path=db)) == 2
    assert len(list_snapshots(limit=10000, db_path=db)) == 5


def test_save_rejects_empty_module(tmp_path):
    with pytest.raises(ValueError):
        save_snapshot("", {}, tmp_path / "state.db")


def test_env_override_selects_db(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("KIRACI_STATE_DB", str(tmp_path / "custom.db"))
    assert default_db_path() == Path(str(tmp_path / "custom.db"))
    save_snapshot("m", {})
    assert (tmp_path / "custom.db").is_file()
