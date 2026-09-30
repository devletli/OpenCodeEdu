from __future__ import annotations

import argparse
import getpass
import json
from datetime import UTC, datetime
from pathlib import Path

from . import ventures
from .db import connect
from .ledger import Ledger
from .metrics import metrics_headline
from .orchestrator import build_status, current_phase
from .store import Store, find_secret


def cmd_status(ledger: Ledger, store: Store) -> dict:
    now = datetime.now(UTC)
    text = build_status(store, ledger, now)
    attention = store.conn.execute(
        "SELECT provider, order_id, currency, gross_cents, status FROM payments"
        " WHERE status IN ('fx_unhandled','ignored') ORDER BY id").fetchall()
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
        "metrics_headline": metrics_headline(Path.cwd()),
    }


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
    args = p.parse_args()

    conn = connect()
    ledger = Ledger(conn)
    store = Store(conn)
    who = getpass.getuser()
    root = Path.cwd()
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
    else:
        (root / "data" / "PAUSE").touch()
        out = {"status": "ok", "detail": "PAUSE file created"}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
