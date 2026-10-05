from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ledger import Ledger
    from .store import Store


def genesis_ts(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT ts FROM ledger WHERE kind='fund' ORDER BY id LIMIT 1").fetchone()
    return row["ts"] if row else None


def _burn_per_day(conn: sqlite3.Connection, days: int = 7) -> int:
    row = conn.execute(
        """SELECT COALESCE(-SUM(delta_cents),0) s FROM ledger
           WHERE kind='expense' AND date(ts) >= date('now', ?)""",
        (f"-{days - 1} days",)).fetchone()
    return int(row["s"]) // days


def _total(conn: sqlite3.Connection, kind: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(delta_cents),0) s FROM ledger WHERE kind=?",
        (kind,)).fetchone()
    return int(row["s"])


def _eur(cents: int) -> str:
    return f"{cents / 100:.2f}"


def build_report(store: Store, ledger: Ledger, now: datetime) -> str:
    conn = ledger.conn
    balances = ledger.balances()
    total = ledger.total_balance()
    burn = _burn_per_day(conn)
    income = _total(conn, "income")
    expenses = -_total(conn, "expense")
    refunds = -_total(conn, "refund")
    ratio = f"{income / expenses:.2f}" if expenses > 0 else "n/a"
    runway = f"{total / burn:.1f} days" if burn > 0 else "unlimited"

    runs = conn.execute(
        "SELECT agent, COUNT(*) n, COALESCE(SUM(est_cost_cents),0) c"
        " FROM runs GROUP BY agent ORDER BY agent").fetchall()
    live = conn.execute(
        "SELECT id, name, slug, external_product_id FROM ventures"
        " WHERE status='live' ORDER BY id").fetchall()
    dead = conn.execute(
        "SELECT id, name FROM ventures WHERE status='dead' ORDER BY id").fetchall()
    pay_status = conn.execute(
        "SELECT status, COUNT(*) n, COALESCE(SUM(recorded_cents),0) c"
        " FROM payments GROUP BY status ORDER BY status").fetchall()
    per_venture = conn.execute(
        """SELECT v.id, v.name, v.status,
                  COALESCE(SUM(CASE WHEN p.status='recorded' THEN p.recorded_cents END),0) rev,
                  COUNT(CASE WHEN p.status='recorded' THEN 1 END) orders
           FROM ventures v LEFT JOIN payments p ON p.venture_id = v.id
           GROUP BY v.id ORDER BY v.id""").fetchall()
    spend = conn.execute(
        """SELECT venture_id, COALESCE(-SUM(delta_cents),0) s FROM ledger
           WHERE kind='expense' AND venture_id IS NOT NULL
           GROUP BY venture_id""").fetchall()
    spend_by = {r["venture_id"]: int(r["s"]) for r in spend}
    income_rows = conn.execute(
        """SELECT venture_id, COALESCE(SUM(delta_cents),0) s FROM ledger
           WHERE kind IN ('income','refund') AND venture_id IS NOT NULL
           GROUP BY venture_id""").fetchall()
    income_by = {r["venture_id"]: int(r["s"]) for r in income_rows}
    open_h = conn.execute(
        "SELECT COUNT(*) c FROM human_tasks WHERE status='open'").fetchone()["c"]
    closed_h = conn.execute(
        "SELECT COUNT(*) c FROM human_tasks WHERE status IN ('done','dismissed')"
    ).fetchone()["c"]

    lines = [
        f"# Kiraci metrics ({now.strftime('%Y-%m-%d %H:%M UTC')})",
        "",
        "## Cash",
        f"- Net cash (ex-owner): EUR {_eur(total)}",
        f"- Daily burn (7d avg): EUR {_eur(burn)}/day, runway {runway}",
        (f"- Income total: EUR {_eur(income)}, expenses: EUR {_eur(expenses)}, "
         f"refunds: EUR {_eur(refunds)}, income/expense ratio: {ratio}"),
        f"- Buckets: {', '.join(f'{k}={_eur(v)}' for k, v in balances.items())}",
        "",
        "## Agent runs",
    ]
    if runs:
        lines += [f"- {r['agent']}: {r['n']} runs, est. cost EUR {_eur(int(r['c']))}"
                  for r in runs]
    else:
        lines.append("- no runs recorded")
    lines += ["", "## Ventures (products live, revenue, spend, ROI)"]
    if per_venture:
        for r in per_venture:
            sp = spend_by.get(r["id"], 0)
            inc = income_by.get(r["id"], 0)
            roi = f"{inc / sp:.2f}" if sp > 0 else ("n/a" if inc == 0 else "inf")
            lines.append(
                f"- #{r['id']} {r['name']} [{r['status']}]: {r['orders']} orders, "
                f"revenue EUR {_eur(int(r['rev']))}, spend EUR {_eur(sp)}, "
                f"ledger income EUR {_eur(inc)}, ROI {roi}")
    else:
        lines.append("- no ventures yet")
    if live:
        lines.append(f"Products live: {', '.join(r['slug'] for r in live)}")
    if dead:
        lines.append(f"Dead ventures: {', '.join(r['name'] for r in dead)}")
    lines += ["", "## Payments needing attention"]
    if pay_status:
        lines += [f"- {r['status']}: {r['n']} orders, recorded EUR {_eur(int(r['c']))}"
                  for r in pay_status]
    else:
        lines.append("- no orders seen yet")
    lines += ["", "## Human inbox",
              f"- Open: {open_h}, closed: {closed_h}"]
    return "\n".join(lines) + "\n"


def metrics_filename(now: datetime) -> str:
    return f"metrics-{now.strftime('%Y')}-W{now.strftime('%V')}.md"


def write_metrics(store: Store, ledger: Ledger, root: Path | str,
                  now: datetime) -> Path:
    out_dir = Path(root) / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / metrics_filename(now)
    path.write_text(build_report(store, ledger, now), encoding="utf-8")
    return path


def latest_metrics(root: Path | str) -> Path | None:
    out_dir = Path(root) / "data" / "outputs"
    files = sorted(out_dir.glob("metrics-*.md"))
    return files[-1] if files else None


def metrics_headline(root: Path | str, max_lines: int = 8) -> str:
    latest = latest_metrics(root)
    if latest is None:
        return "no metrics report yet"
    try:
        lines = latest.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "no metrics report yet"
    return "\n".join(lines[:max_lines])
