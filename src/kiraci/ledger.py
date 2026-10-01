from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from .rules import BUCKETS, DEFAULT_POLICY, GENESIS, Policy, decide


def ledger_ts() -> str:
    """Ledger timestamp, generated in Python and stored explicitly (hash input).

    Format matches the SQLite default (strftime '%Y-%m-%dT%H:%M:%fZ' ->
    milliseconds), e.g. 2026-10-01T10:26:06.052Z.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def entry_hash(prev_hash: str, ts: str, kind: str, bucket: str, delta: int,
               agent: str, ref: str | None, note: str,
               venture_id: int | None) -> str:
    """Hash-chain link. None fields become empty strings."""
    raw = "|".join([
        prev_hash or "", ts, kind, bucket, str(delta), agent,
        ref or "", note, str(venture_id) if venture_id is not None else "",
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Ledger:
    def __init__(self, conn: sqlite3.Connection, policy: Policy = DEFAULT_POLICY):
        self.conn = conn
        self.policy = policy

    # ---------- internal helpers ----------
    @contextmanager
    def _tx(self) -> Iterator[None]:
        self.conn.execute("BEGIN IMMEDIATE")  # write lock: prevents race conditions
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def _insert(self, kind: str, bucket: str, delta: int, agent: str,
                ref: str | None, note: str, venture_id: int | None = None) -> int:
        prev = self.conn.execute(
            "SELECT hash FROM ledger ORDER BY id DESC LIMIT 1").fetchone()
        ts = ledger_ts()
        h = entry_hash(prev["hash"] if prev else "", ts, kind, bucket, delta,
                       agent, ref, note, venture_id)
        cur = self.conn.execute(
            "INSERT INTO ledger(ts,kind,bucket,delta_cents,agent,ref,note,"
            "venture_id,hash) VALUES (?,?,?,?,?,?,?,?,?)",
            (ts, kind, bucket, delta, agent, ref, note, venture_id, h),
        )
        return int(cur.lastrowid)

    def _log_approval(self, agent: str, bucket: str, amount: int, purpose: str,
                      tier: str, status: str, reason: str,
                      decided_by: str | None = None, entry_id: int | None = None,
                      venture_id: int | None = None) -> int:
        cur = self.conn.execute(
            """INSERT INTO approvals(agent,bucket,amount_cents,purpose,tier,status,reason,
                                     decided_by,decided_at,entry_id,venture_id)
               VALUES (?,?,?,?,?,?,?,?,CASE WHEN ? IS NULL THEN NULL
                       ELSE strftime('%Y-%m-%dT%H:%M:%fZ','now') END,?,?)""",
            (agent, bucket, amount, purpose, tier, status, reason,
             decided_by, decided_by, entry_id, venture_id),
        )
        return int(cur.lastrowid)

    def _balances(self) -> dict[str, int]:
        out = {b: 0 for b in BUCKETS}
        for r in self.conn.execute("SELECT bucket, SUM(delta_cents) s FROM ledger GROUP BY bucket"):
            out[r["bucket"]] = int(r["s"])
        return out

    def _spent_today(self, bucket: str) -> int:
        row = self.conn.execute(
            """SELECT COALESCE(-SUM(delta_cents),0) s FROM ledger
               WHERE kind='expense' AND bucket=? AND date(ts)=date('now')""",
            (bucket,),
        ).fetchone()
        return int(row["s"])

    # ---------- read access (open to agents) ----------
    def balances(self) -> dict[str, int]:
        return self._balances()

    def total_balance(self) -> int:
        return sum(v for k, v in self._balances().items() if k != "owner")

    def recent(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM ledger ORDER BY id DESC LIMIT ?", (max(1, min(limit, 200)),)
        )
        return [dict(r) for r in rows]

    def pending(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM approvals WHERE status='pending' ORDER BY id"
        )
        return [dict(r) for r in rows]

    # ---------- spend requests (open to agents) ----------
    def request_spend(self, agent: str, bucket: str, amount_cents: int, purpose: str,
                      venture_id: int | None = None) -> dict:
        with self._tx():
            bal = self._balances()
            d = decide(
                self.policy,
                bucket=bucket,
                amount=amount_cents,
                bucket_balance=bal.get(bucket, 0),
                total_balance=sum(v for k, v in bal.items() if k != "owner"),
                spent_today=self._spent_today(bucket),
            )
            if d.status == "approved":
                entry_id = self._insert("expense", bucket, -amount_cents, agent, None,
                                        purpose, venture_id)
                aid = self._log_approval(agent, bucket, amount_cents, purpose, d.tier,
                                         "executed", d.reason, "policy", entry_id,
                                         venture_id)
                return {"status": "approved", "approval_id": aid, "entry_id": entry_id,
                        "reason": d.reason}
            if d.status == "pending":
                aid = self._log_approval(agent, bucket, amount_cents, purpose, d.tier,
                                         "pending", d.reason, venture_id=venture_id)
                return {"status": "pending", "approval_id": aid, "tier": d.tier,
                        "reason": d.reason}
            # rejected: still log for auditing (skip amount <= 0 to satisfy the CHECK)
            if amount_cents > 0:
                self._log_approval(agent, bucket, amount_cents, purpose, "none",
                                   "rejected", d.reason, "policy",
                                   venture_id=venture_id)
            return {"status": "rejected", "reason": d.reason}

    # ---------- HUMAN / SYSTEM ONLY (never exposed over MCP) ----------
    def init_genesis(self) -> None:
        with self._tx():
            if self.conn.execute("SELECT COUNT(*) c FROM ledger").fetchone()["c"]:
                raise RuntimeError("ledger is already initialized")
            for bucket, amount in GENESIS.items():
                self._insert("fund", bucket, amount, "system", f"genesis:{bucket}",
                             "genesis budget")

    def record_income(self, amount_cents: int, ref: str, note: str = "",
                      agent: str = "webhook", venture_id: int | None = None) -> dict:
        """Income split: 50% experiment, 30% emergency, 20% owner. Idempotent via ref."""
        if amount_cents <= 0:
            raise ValueError("income must be positive")
        if not ref:
            raise ValueError("payment reference (ref) is required")
        with self._tx():
            if self.conn.execute("SELECT 1 FROM ledger WHERE ref=?", (f"{ref}:experiment",)).fetchone():
                return {"status": "duplicate", "ref": ref}
            reinvest = amount_cents * 50 // 100
            reserve = amount_cents * 30 // 100
            owner = amount_cents - reinvest - reserve
            for bucket, part in (("experiment", reinvest), ("emergency", reserve), ("owner", owner)):
                if part > 0:
                    self._insert("income", bucket, part, agent, f"{ref}:{bucket}",
                                 note, venture_id)
            return {"status": "recorded", "experiment": reinvest, "emergency": reserve,
                    "owner": owner}

    def record_refund(self, amount_cents: int, ref: str, note: str = "",
                      agent: str = "webhook", venture_id: int | None = None) -> dict:
        """Mirror of record_income with negative deltas. Idempotent via ref.

        Refunds are the ONLY path that may push a bucket negative; spends still
        require a positive balance (see decide()).
        """
        if amount_cents <= 0:
            raise ValueError("refund must be positive")
        if not ref:
            raise ValueError("payment reference (ref) is required")
        with self._tx():
            if self.conn.execute("SELECT 1 FROM ledger WHERE ref=?", (f"{ref}:experiment",)).fetchone():
                return {"status": "duplicate", "ref": ref}
            reinvest = amount_cents * 50 // 100
            reserve = amount_cents * 30 // 100
            owner = amount_cents - reinvest - reserve
            for bucket, part in (("experiment", reinvest), ("emergency", reserve), ("owner", owner)):
                if part > 0:
                    self._insert("refund", bucket, -part, agent, f"{ref}:{bucket}",
                                 note, venture_id)
            return {"status": "recorded", "experiment": -reinvest, "emergency": -reserve,
                    "owner": -owner}

    def record_reconciliation(self, bucket: str, delta_cents: int, ref: str,
                              note: str = "") -> dict:
        """Book the difference between real provider spend and the ledger.

        Negative delta = expense (we under-booked), positive delta = refund
        (we over-booked). Agent is always `system`; idempotent through ref.
        This is the ONLY ledger write allowed to drive a bucket below zero:
        reality wins, and a negative bucket then blocks further spending
        through decide().
        """
        if not ref:
            raise ValueError("reconciliation reference (ref) is required")
        if delta_cents == 0:
            return {"status": "noop", "ref": ref}
        kind = "expense" if delta_cents < 0 else "refund"
        with self._tx():
            if self.conn.execute("SELECT 1 FROM ledger WHERE ref=?", (ref,)).fetchone():
                return {"status": "duplicate", "ref": ref}
            entry_id = self._insert(kind, bucket, delta_cents, "system", ref, note)
            return {"status": "recorded", "entry_id": entry_id,
                    "delta_cents": delta_cents}

    def approve(self, approval_id: int, decided_by: str) -> dict:
        with self._tx():
            row = self.conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
            if row is None or row["status"] != "pending":
                return {"status": "error", "reason": "no pending approval found"}
            if row["amount_cents"] > self._balances().get(row["bucket"], 0):
                self.conn.execute(
                    """UPDATE approvals SET status='rejected',
                       reason='insufficient balance at approval time',
                       decided_by=?, decided_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""",
                    (decided_by, approval_id))
                return {"status": "rejected", "reason": "insufficient balance"}
            entry_id = self._insert("expense", row["bucket"], -row["amount_cents"],
                                    row["agent"], None, row["purpose"],
                                    row["venture_id"])
            self.conn.execute(
                """UPDATE approvals SET status='executed', decided_by=?, entry_id=?,
                   decided_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""",
                (decided_by, entry_id, approval_id))
            return {"status": "executed", "entry_id": entry_id}

    def reject(self, approval_id: int, decided_by: str, reason: str = "rejected by human") -> dict:
        with self._tx():
            cur = self.conn.execute(
                """UPDATE approvals SET status='rejected', reason=?, decided_by=?,
                   decided_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                   WHERE id=? AND status='pending'""",
                (reason, decided_by, approval_id))
            return {"status": "rejected" if cur.rowcount else "error"}
