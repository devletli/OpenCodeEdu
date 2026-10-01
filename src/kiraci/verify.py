"""Ledger integrity verification. Deterministic, no LLM, runs daily.

verify_ledger(conn) returns a list of findings (empty = healthy):
- PRAGMA integrity_check
- both append-only triggers exist with the expected SQL
- the hash chain is unbroken
- genesis entries sum to 10000 cents across the four buckets
- every executed approval has exactly one expense entry with the same amount
- every expense entry is explained by an approval, a reconciliation or an
  income refund ref; refund entries by a refund or reconciliation ref
- no bucket is negative unless explained by a reconciliation entry
- every recorded payment equals the income entries with its order: ref
- ref values are unique
"""

from __future__ import annotations

import sqlite3

from .ledger import entry_hash


def _trigger_ok(conn: sqlite3.Connection, name: str, action: str) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
        (name,)).fetchone()
    if row is None or not row["sql"]:
        return False
    normalized = " ".join(row["sql"].split())
    return (f"BEFORE {action} ON ledger" in normalized
            and "RAISE(ABORT, 'ledger is append-only')" in normalized)


def verify_ledger(conn: sqlite3.Connection) -> list[str]:
    conn.row_factory = sqlite3.Row  # defensive: works on any connection
    findings: list[str] = []

    row = conn.execute("PRAGMA integrity_check").fetchone()
    if row is None or row[0] != "ok":
        msg = row[0] if row else "no result"
        findings.append(f"integrity_check failed: {msg}")

    for name, action in (("ledger_no_update", "UPDATE"), ("ledger_no_delete", "DELETE")):
        if not _trigger_ok(conn, name, action):
            findings.append(f"append-only trigger missing or altered: {name}")

    # hash chain
    prev = ""
    for r in conn.execute(
        "SELECT id, ts, kind, bucket, delta_cents, agent, ref, note, venture_id,"
        " hash FROM ledger ORDER BY id"
    ):
        want = entry_hash(prev, r["ts"], r["kind"], r["bucket"], r["delta_cents"],
                          r["agent"], r["ref"], r["note"], r["venture_id"])
        if r["hash"] != want:
            findings.append(f"hash chain broken at ledger id {r['id']}")
            break
        prev = r["hash"]

    # genesis
    funds = conn.execute(
        "SELECT bucket, SUM(delta_cents) s FROM ledger WHERE kind='fund'"
        " GROUP BY bucket").fetchall()
    if funds:
        total = sum(int(r["s"]) for r in funds)
        if total != 10000:
            findings.append(f"genesis funds sum to {total}, expected 10000")

    # executed approvals <-> entries
    for r in conn.execute(
        "SELECT id, amount_cents, entry_id FROM approvals WHERE status='executed'"
    ):
        if r["entry_id"] is None:
            findings.append(f"executed approval {r['id']} has no entry")
            continue
        e = conn.execute(
            "SELECT kind, delta_cents FROM ledger WHERE id=?", (r["entry_id"],)
        ).fetchone()
        if e is None or e["kind"] != "expense" or int(e["delta_cents"]) != -int(r["amount_cents"]):
            findings.append(
                f"executed approval {r['id']} lacks a matching expense entry")

    # expense/refund entries explained
    explained = {
        r["entry_id"] for r in conn.execute(
            "SELECT entry_id FROM approvals WHERE entry_id IS NOT NULL")}
    for r in conn.execute(
        "SELECT id, kind, bucket, ref FROM ledger WHERE kind IN ('expense','refund')"
    ):
        ref = r["ref"] or ""
        if r["id"] in explained or ref.startswith("reconcile:"):
            continue
        if r["kind"] == "expense":
            findings.append(f"unexplained expense entry {r['id']} (ref {ref!r})")
        elif not ref.startswith("refund:"):
            findings.append(f"unexplained refund entry {r['id']} (ref {ref!r})")

    # negative buckets need a reconciliation explanation
    for r in conn.execute(
        "SELECT bucket, SUM(delta_cents) s FROM ledger GROUP BY bucket"
    ):
        if int(r["s"]) < 0:
            has = conn.execute(
                "SELECT 1 FROM ledger WHERE bucket=? AND ref LIKE 'reconcile:%' LIMIT 1",
                (r["bucket"],)).fetchone()
            if not has:
                findings.append(
                    f"bucket {r['bucket']} negative without reconciliation")

    # payments <-> income entries
    for p in conn.execute(
        "SELECT id, order_id, recorded_cents FROM payments WHERE status='recorded'"
    ):
        got = conn.execute(
            "SELECT COALESCE(SUM(delta_cents),0) s FROM ledger WHERE ref LIKE ?",
            (f"{p['order_id']}:%",)).fetchone()
        if int(got["s"]) != int(p["recorded_cents"]):
            findings.append(
                f"payment {p['id']} ({p['order_id']}) recorded_cents mismatch")

    dup = conn.execute(
        "SELECT ref FROM ledger WHERE ref IS NOT NULL GROUP BY ref"
        " HAVING COUNT(*) > 1").fetchall()
    for r in dup:
        findings.append(f"duplicate ref: {r['ref']}")

    return findings