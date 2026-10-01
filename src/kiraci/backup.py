"""Backups with integrity verification and rotation. Deterministic, no LLM.

`Connection.backup()` into data/backups/kiraci-YYYYMMDD.db, integrity_check +
verify_ledger on the copy, gzip, keep_daily daily and keep_weekly weekly
(Sunday) copies. If KIRACI_BACKUP_DIR is set the gzip is copied there too
(a mounted or synced folder the human provides). Failures never crash the
daemon; a failed backup surfaces as a system notice (caller's job).
"""

from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .verify import verify_ledger


def _verify_copy(path: Path) -> list[str]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        findings = [] if (row and row[0] == "ok") else [
            f"integrity_check failed: {row[0] if row else 'no result'}"]
        findings += verify_ledger(conn)
    finally:
        conn.close()
    return findings


def _rotate(directory: Path, *, keep_daily: int, keep_weekly: int) -> list[str]:
    removed: list[str] = []
    files = sorted(directory.glob("kiraci-*.db.gz"), reverse=True)
    kept = 0
    weeklies = 0
    for p in files:
        day = p.stem.removeprefix("kiraci-").removesuffix(".db")
        try:
            dt = datetime.strptime(day, "%Y%m%d").replace(tzinfo=UTC).date()
        except ValueError:
            continue
        is_sunday = dt.weekday() == 6
        if is_sunday and weeklies < keep_weekly:
            weeklies += 1
            continue
        if kept < keep_daily:
            kept += 1
            continue
        p.unlink(missing_ok=True)
        removed.append(p.name)
    return removed


def run_backup(conn: sqlite3.Connection, root: Path, config, *,
               now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    backup_dir = Path(root) / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    name = f"kiraci-{now.strftime('%Y%m%d')}.db"
    plain = backup_dir / name
    try:
        plain.unlink(missing_ok=True)
        dst = sqlite3.connect(plain)
        try:
            conn.backup(dst)
        finally:
            dst.close()
        findings = _verify_copy(plain)
        gz = backup_dir / f"{name}.gz"
        with open(plain, "rb") as f_in, gzip.open(gz, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        plain.unlink(missing_ok=True)
        removed = _rotate(
            backup_dir, keep_daily=int(config.backup_value("keep_daily")),
            keep_weekly=int(config.backup_value("keep_weekly")))
        extra = ""
        env_dir = os_env_backup_dir()
        if env_dir:
            target = Path(env_dir) / f"{name}.gz"
            try:
                shutil.copyfile(gz, target)
                extra = str(target)
            except OSError as e:
                findings.append(f"backup dir copy failed: {e}")
        if findings:
            return {"status": "unhealthy", "path": str(gz), "findings": findings,
                    "external": extra}
        return {"status": "ok", "path": str(gz), "findings": [],
                "removed": removed, "external": extra}
    except (OSError, sqlite3.Error) as e:
        return {"status": "failed", "findings": [f"backup failed: {e}"]}


def os_env_backup_dir() -> str:
    return os.environ.get("KIRACI_BACKUP_DIR", "")