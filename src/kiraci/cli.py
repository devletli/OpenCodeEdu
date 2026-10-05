from __future__ import annotations

import argparse
import getpass
import gzip
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from . import heartbeat as heartbeat_mod
from . import ventures
from .backup import run_backup
from .config import load_config
from .db import connect
from .ledger import Ledger
from .metrics import metrics_headline
from .orchestrator import build_status, current_phase
from .sandbox import Sandbox
from .store import Store, find_secret
from .verify import verify_ledger


def cmd_status(ledger: Ledger, store: Store) -> dict:
    now = datetime.now(UTC)
    text = build_status(store, ledger, now)
    attention = store.conn.execute(
        "SELECT provider, order_id, currency, gross_cents, status FROM payments"
        " WHERE status IN ('fx_unhandled','ignored') ORDER BY id").fetchall()
    config = load_config()
    root = Path.cwd()
    sandbox = Sandbox(config=config, root=root)
    hb_age = heartbeat_mod.heartbeat_age_minutes(store, now)
    return {
        "status_text": text,
        "balances_eur": {k: v / 100 for k, v in ledger.balances().items()},
        "phase": current_phase(now),
        "open_human_tasks": store.open_human_tasks(),
        "pending_approvals": ledger.pending(),
        "task_counts": store.task_counts(),
        "last_tick": store.kv_get("last_tick", "never"),
        "ventures": ventures.list_ventures(store.conn),
        "payments_needing_attention": [dict(r) for r in attention],
        "tokens_spent_today_cents": ledger.spent_today("tokens"),
        "spend_today_by_bucket_cents": {
            b: ledger.spent_today(b) for b in ledger.balances()},
        "metrics_headline": metrics_headline(root),
        "sandbox_status": sandbox.status(),
        "cost_multiplier": store.kv_get("cost_multiplier", "1.0"),
        "paid_paused_until": store.kv_get("paid_paused_until"),
        "last_reconcile": store.kv_get("last_reconcile"),
        "last_backup": store.kv_get("last_backup"),
        "last_verify": store.kv_get("last_verify"),
        "heartbeat_age_minutes": (round(hb_age, 1) if hb_age is not None else None),
    }


def _restore_ok_heartbeat(root: Path, db_path: Path) -> tuple[bool, str]:
    """Refuse unless data/KILL exists and the last heartbeat is older than 2 min."""
    if not (root / "data" / "KILL").exists():
        return False, "restore requires data/KILL (stop the daemon first)"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT value FROM kv WHERE key='last_tick'").fetchone()
    finally:
        conn.close()
    if not row:
        return True, "no heartbeat recorded"
    try:
        last = datetime.fromisoformat(row["value"])
    except ValueError:
        return True, "heartbeat unparseable"
    age = (datetime.now(UTC) - last).total_seconds()
    if age <= 120:
        return False, f"last heartbeat is only {age:.0f}s old; wait 2 minutes"
    return True, f"heartbeat {age:.0f}s old"


def _verify_backup_file(path: Path) -> list[str]:
    """integrity_check + verify_ledger on a backup copy (plain or gzip)."""
    try:
        if path.suffix == ".gz":
            with tempfile.TemporaryDirectory() as td:
                plain = Path(td) / "verify.db"
                with gzip.open(path, "rb") as f_in, open(plain, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                conn = sqlite3.connect(plain)
                conn.row_factory = sqlite3.Row
                try:
                    row = conn.execute("PRAGMA integrity_check").fetchone()
                    findings = [] if (row and row[0] == "ok") else [
                        "integrity_check failed"]
                    return findings + verify_ledger(conn)
                finally:
                    conn.close()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            findings = [] if (row and row[0] == "ok") else ["integrity_check failed"]
            return findings + verify_ledger(conn)
        finally:
            conn.close()
    except (OSError, sqlite3.DatabaseError):
        return ["backup file unreadable"]


def cmd_restore(root: Path, backup_file: Path, yes: bool) -> dict:
    """Human-only restore. Refuses unless KILL exists and heartbeat is stale."""
    if not yes:
        return {"status": "refused", "reason": "add --yes to actually restore"}
    db_path = Path(os.path.abspath(os.environ.get("KIRACI_DB", "data/kiraci.db")))
    if not db_path.exists():
        return {"status": "refused", "reason": f"database not found: {db_path}"}
    ok, why = _restore_ok_heartbeat(root, db_path)
    if not ok:
        return {"status": "refused", "reason": why}
    findings = _verify_backup_file(backup_file)
    if findings:
        return {"status": "refused", "reason": "backup failed verification",
                "findings": findings[:10]}
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    keep = db_path.with_name(f"{db_path.name}.before-restore-{stamp}")
    shutil.move(str(db_path), str(keep))
    for suffix in ("-wal", "-shm"):
        Path(str(db_path) + suffix).unlink(missing_ok=True)
    if backup_file.suffix == ".gz":
        with gzip.open(backup_file, "rb") as f_in, open(db_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    else:
        shutil.copyfile(backup_file, db_path)
    conn = connect(str(db_path))
    try:
        version = conn.execute(
            "SELECT value FROM kv WHERE key='schema_version'").fetchone()
        findings = verify_ledger(conn)
    finally:
        conn.close()
    return {"status": "restored", "kept_old_db": str(keep), "installed": str(db_path),
            "schema_version": version["value"] if version else None,
            "verify_findings": findings[:10]}


def main() -> None:
    """Human-only CLI. Agents must never be given shell access to this."""
    p = argparse.ArgumentParser(prog="kiraci")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the genesis budget")
    sub.add_parser("balances", help="show bucket balances in EUR")
    sub.add_parser("pending", help="list requests awaiting approval")
    a = sub.add_parser("approve", help="approve a pending request")
    a.add_argument("id", type=int)
    r = sub.add_parser("reject", help="reject a pending request")
    r.add_argument("id", type=int)
    r.add_argument("--reason", default="rejected by human")
    i = sub.add_parser("income", help="record income and split it across buckets")
    i.add_argument("--amount-eur", type=float, required=True)
    i.add_argument("--ref", required=True, help="payment provider transaction id")
    i.add_argument("--note", default="")
    sub.add_parser("status", help="full system status")
    h = sub.add_parser("human", help="human inbox tasks")
    hsub = h.add_subparsers(dest="hcmd", required=True)
    hsub.add_parser("list", help="list open human tasks")
    ha = hsub.add_parser("add", help="file a human task")
    ha.add_argument("--kind", required=True)
    ha.add_argument("--title", required=True)
    ha.add_argument("--instructions", required=True)
    ha.add_argument("--url", default="")
    ha.add_argument("--key", required=True, help="dedupe key")
    hd = hsub.add_parser("done", help="resolve a human task")
    hd.add_argument("id", type=int)
    hd.add_argument("--note", default="")
    hx = hsub.add_parser("dismiss", help="dismiss a human task")
    hx.add_argument("id", type=int)
    t = sub.add_parser("tasks", help="queued tasks")
    tsub = t.add_subparsers(dest="tcmd", required=True)
    tl = tsub.add_parser("list", help="list tasks")
    tl.add_argument("--status", default=None)
    v = sub.add_parser("venture", help="ventures (human-only)")
    vsub = v.add_subparsers(dest="vcmd", required=True)
    vsub.add_parser("list", help="list ventures")
    vs = vsub.add_parser("show", help="show a venture")
    vs.add_argument("id", type=int)
    vp = vsub.add_parser("set-product",
                         help="attach a storefront product id (goes live)")
    vp.add_argument("id", type=int)
    vp.add_argument("external_product_id")
    vz = vsub.add_parser("pause", help="pause a venture")
    vz.add_argument("id", type=int)
    vk = vsub.add_parser("kill", help="kill a venture (needs a 80+ char note)")
    vk.add_argument("id", type=int)
    vk.add_argument("--note", required=True)
    sub.add_parser("kill", help="stop the daemon after this tick")
    sub.add_parser("resume", help="clear KILL and PAUSE files")
    sub.add_parser("pause", help="pause dispatch")
    rn = sub.add_parser("run", help="start the orchestrator (restarts crashes)")
    rn.add_argument("--dry-run", action="store_true",
                    help="fake runner: no opencode, no spending")
    rn.add_argument("--once", action="store_true",
                    help="run a single tick and exit (no supervision)")
    hl = sub.add_parser("health", help="health watchdog (recovery scenarios)")
    hl.add_argument("--once", action="store_true",
                    help="single check+recover cycle, then exit")
    sub.add_parser("verify", help="run the ledger integrity checks")
    sub.add_parser("backup", help="run a backup now")
    sub.add_parser("heartbeat-check", help="alert (once/hour) when the daemon is stale")
    rs = sub.add_parser("restore", help="restore the database from a backup (human-only)")
    rs.add_argument("file", help="backup file (.db or .db.gz)")
    rs.add_argument("--yes", action="store_true", help="actually perform the restore")
    args = p.parse_args()

    root = Path.cwd()
    if args.cmd == "run":
        from .orchestrator import build_orchestrator, supervise

        if args.once:
            orch = build_orchestrator(dry_run=args.dry_run)
            print(orch.tick(), flush=True)
            return
        sys.exit(supervise(
            lambda: build_orchestrator(dry_run=args.dry_run).run_forever()))
    if args.cmd == "restore":
        out = cmd_restore(root, Path(args.file), args.yes)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        if out.get("status") != "restored":
            sys.exit(1)
        return
    if args.cmd == "heartbeat-check":
        conn = connect()
        try:
            code, msg = heartbeat_mod.heartbeat_check(
                Store(conn), root, load_config())
        finally:
            conn.close()
        print(msg)
        sys.exit(code)

    conn = connect()
    ledger = Ledger(conn)
    store = Store(conn)
    who = getpass.getuser()
    if args.cmd == "init":
        ledger.init_genesis()
        out = ledger.balances()
    elif args.cmd == "balances":
        out = {k: v / 100 for k, v in ledger.balances().items()}
    elif args.cmd == "pending":
        out = ledger.pending()
    elif args.cmd == "approve":
        out = ledger.approve(args.id, who)
    elif args.cmd == "reject":
        out = ledger.reject(args.id, who, args.reason)
    elif args.cmd == "income":
        out = ledger.record_income(round(args.amount_eur * 100), args.ref, args.note)
    elif args.cmd == "status":
        out = cmd_status(ledger, store)
    elif args.cmd == "human":
        if args.hcmd == "list":
            out = store.open_human_tasks()
        elif args.hcmd == "add":
            out = store.add_human_task(
                kind=args.kind, title=args.title, instructions=args.instructions,
                url=args.url, dedupe_key=args.key, created_by=who,
            )
        elif args.hcmd == "done":
            secret = find_secret(args.note)
            if secret:
                out = {"status": "error",
                       "reason": f"refused: note {secret}; secrets do not belong here"}
            else:
                out = store.resolve_human_task(args.id, note=args.note)
        else:
            out = store.resolve_human_task(args.id, status="dismissed")
    elif args.cmd == "tasks":
        out = store.list_tasks(status=args.status)
    elif args.cmd == "venture":
        if args.vcmd == "list":
            out = ventures.list_ventures(store.conn)
        elif args.vcmd == "show":
            venture = ventures.get_venture(store.conn, args.id)
            if venture is None:
                out = {"status": "error", "reason": "unknown venture id"}
            else:
                spent = ventures.venture_spent_cents(store.conn, args.id)
                earned = ventures.venture_income_cents(store.conn, args.id)
                orders = [dict(r) for r in store.conn.execute(
                    "SELECT * FROM payments WHERE venture_id=? ORDER BY id",
                    (args.id,))]
                out = {"status": "ok", "venture": venture,
                       "spent_cents": spent, "income_cents": earned,
                       "payments": orders}
        elif args.vcmd == "set-product":
            out = ventures.set_external_product(
                store, root, args.id, args.external_product_id)
        elif args.vcmd == "pause":
            try:
                out = ventures.update_venture(store, root, args.id, "paused")
            except ValueError as e:
                out = {"status": "error", "reason": str(e)}
        else:
            try:
                out = ventures.update_venture(store, root, args.id, "dead",
                                              death_note=args.note)
            except ValueError as e:
                out = {"status": "error", "reason": str(e)}
    elif args.cmd == "kill":
        (root / "data" / "KILL").touch()
        out = {"status": "ok", "detail": "KILL file created"}
    elif args.cmd == "resume":
        (root / "data" / "KILL").unlink(missing_ok=True)
        (root / "data" / "PAUSE").unlink(missing_ok=True)
        out = {"status": "ok", "detail": "KILL and PAUSE cleared"}
    elif args.cmd == "health":
        from .health import HealthRunner

        runner = HealthRunner(root=root, store=store, ledger=ledger,
                              config=load_config())
        if args.once:
            findings, _ = runner.cycle()
            sys.exit(0 if all(f.ok or f.severity != "crit" for f in findings)
                     else 1)
        sys.exit(runner.run_forever())
    elif args.cmd == "verify":
        findings = verify_ledger(conn)
        out = {"status": "healthy" if not findings else "findings",
               "findings": findings}
    elif args.cmd == "backup":
        out = run_backup(conn, root, load_config())
    else:
        (root / "data" / "PAUSE").touch()
        out = {"status": "ok", "detail": "PAUSE file created"}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
