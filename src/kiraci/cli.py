from __future__ import annotations

import argparse
import getpass
import json

from .db import connect
from .ledger import Ledger


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
    args = p.parse_args()

    ledger = Ledger(connect())
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
    else:
        out = ledger.record_income(round(args.amount_eur * 100), args.ref, args.note)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
