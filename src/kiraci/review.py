from __future__ import annotations

import re
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import Config
    from .ledger import Ledger
    from .store import Store

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _executed_yellow_today_cents(ledger: Ledger) -> int:
    row = ledger.conn.execute(
        """SELECT COALESCE(SUM(amount_cents),0) s FROM approvals
           WHERE tier='yellow' AND status='executed'
           AND date(decided_at)=date('now')"""
    ).fetchone()
    return int(row["s"])


def _approval_status(ledger: Ledger, approval_id: int) -> str | None:
    row = ledger.conn.execute(
        "SELECT status FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    return row["status"] if row else None


def _judge_verdict(text: str) -> str:
    """Extract the judge's verdict from opencode's formatted run output.

    The formatted output prefixes a session header ("> judge · model") and
    echoes tool calls, so the judge's final answer — whose first line is
    exactly ACCEPT or REJECT — sits after the transcript. Take the last bare
    verdict line (the final answer comes last); anything unparsable REJECTs
    (fail closed).
    """
    verdict = "REJECT"
    for ln in text.splitlines():
        ln = _ANSI_RE.sub("", ln).strip()
        if ln in ("ACCEPT", "REJECT"):
            verdict = ln
    return verdict


def review_approvals(
    *,
    store: Store,
    ledger: Ledger,
    runner: Any,
    config: Config,
    balances: dict[str, Any],
    runway_str: str,
    judge_enabled: bool,
    repo_root: Path,
    timeout_s: int,
    notify_fn: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Review pending approvals. Yellow via the judge agent, red via Human Inbox.

    Returns counts: yellow_accepted/rejected/deferred, red_filed, red_closed.
    """
    out = {"yellow_accepted": 0, "yellow_rejected": 0, "yellow_deferred": 0,
           "red_filed": 0, "red_closed": 0}
    pending = ledger.pending()
    cap = int(config.limits.get("yellow_daily_auto_approve_cents", 1000))
    spent_today = _executed_yellow_today_cents(ledger)

    if judge_enabled:
        for ap in pending:
            if ap["tier"] != "yellow" or ap["agent"] == "judge":
                continue
            if spent_today + ap["amount_cents"] > cap:
                out["yellow_deferred"] += 1
                continue
            bal_eur = {k: v / 100 for k, v in balances.items()}
            prompt = (
                f"You are reviewing spend approval #{ap['id']}: agent={ap['agent']} "
                f"wants EUR {ap['amount_cents'] / 100:.2f} from bucket {ap['bucket']} "
                f"for \"{ap['purpose']}\".\n"
                f"Balances (EUR): {bal_eur}. Runway: {runway_str}.\n"
                "Criteria: the purpose is specific and tied to the current strategy; "
                "the amount is proportional; nothing on the forbidden list "
                "(KIRACI.md Section 5); when unsure REJECT.\n"
                "Your answer's first non-empty line must be exactly ACCEPT or REJECT, "
                "followed by one line of reasoning."
            )
            res = runner.run("judge", prompt, Path(repo_root), timeout_s)
            if res.skipped_reason is not None or _judge_verdict(res.text) != "ACCEPT":
                if res.skipped_reason is not None:
                    reason = res.skipped_reason
                elif res.text.strip():
                    # The judge's final answer is at the tail of the output;
                    # the first line is just the opencode session header.
                    nonempty = [ln for ln in res.text.splitlines() if ln.strip()]
                    reason = nonempty[-1][:200]
                else:
                    reason = "empty judge answer"
                ledger.reject(ap["id"], "judge", str(reason)[:500])
                out["yellow_rejected"] += 1
            else:
                decided = ledger.approve(ap["id"], "judge")
                if decided.get("status") == "executed":
                    spent_today += ap["amount_cents"]
                    out["yellow_accepted"] += 1
                else:
                    out["yellow_rejected"] += 1

    for ap in pending:
        if ap["tier"] != "red":
            continue
        amount = f"EUR {ap['amount_cents'] / 100:.2f}"
        result = store.add_human_task(
            kind="red_tier_approval",
            title=f"Approve {amount} from {ap['bucket']} ({ap['purpose'][:60]})",
            instructions=(
                f"Agent {ap['agent']} requests {amount} from bucket {ap['bucket']} "
                f"for: {ap['purpose']}. To approve run "
                f"`python -m kiraci.cli approve {ap['id']}`, to reject run "
                f"`python -m kiraci.cli reject {ap['id']}`."
            ),
            dedupe_key=f"approval:{ap['id']}",
            created_by="orchestrator",
        )
        if result.get("status") == "created":
            out["red_filed"] += 1
            if notify_fn is not None:
                try:
                    notify_fn(result["task"])
                except (OSError, sqlite3.Error) as e:
                    print(f"kiraci: red-approval notify failed: {e}", file=sys.stderr)

    for ht in store.list_human_tasks("open"):
        if ht["kind"] != "red_tier_approval" or not ht["dedupe_key"].startswith("approval:"):
            continue
        try:
            aid = int(ht["dedupe_key"].split(":", 1)[1])
        except ValueError:
            continue
        status = _approval_status(ledger, aid)
        if status is not None and status != "pending":
            store.resolve_human_task(ht["id"], note=f"approval {status}")
            out["red_closed"] += 1
    return out
