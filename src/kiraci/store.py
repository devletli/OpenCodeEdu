from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS human_tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    kind          TEXT NOT NULL CHECK (kind IN
                  ('login','account_setup','identity_verification',
                   'payment_method_setup','secret_provisioning','red_tier_approval',
                   'logged_in_action')),
    title         TEXT NOT NULL,
    instructions  TEXT NOT NULL,
    url           TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','dismissed')),
    created_by    TEXT NOT NULL,
    dedupe_key    TEXT NOT NULL UNIQUE,
    resolved_at   TEXT,
    note          TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    agent         TEXT NOT NULL CHECK (agent IN
                  ('scout','builder','seller','treasurer','diplomat','chronicler')),
    title         TEXT NOT NULL,
    prompt        TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN
                  ('pending','running','blocked','done','failed','rejected','cancelled')),
    priority      INTEGER NOT NULL DEFAULT 5 CHECK (priority BETWEEN 0 AND 9),
    requires_review INTEGER NOT NULL DEFAULT 0,
    review        TEXT NOT NULL DEFAULT 'none' CHECK (review IN ('none','accepted','rejected')),
    blocked_on    INTEGER REFERENCES human_tasks(id),
    not_before    TEXT,
    attempts      INTEGER NOT NULL DEFAULT 0,
    branch        TEXT,
    result_path   TEXT,
    result_summary TEXT NOT NULL DEFAULT '',
    created_by    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    agent         TEXT NOT NULL,
    task_id       INTEGER,
    model         TEXT NOT NULL DEFAULT '',
    est_cost_cents INTEGER NOT NULL DEFAULT 0,
    duration_s    REAL NOT NULL DEFAULT 0,
    exit_code     INTEGER,
    status        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS ventures (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    name          TEXT NOT NULL UNIQUE,
    slug          TEXT NOT NULL UNIQUE,
    kind          TEXT NOT NULL CHECK (kind IN
                  ('digital_product','bounty','report','micro_saas','other')),
    hypothesis    TEXT NOT NULL,
    score         REAL NOT NULL CHECK (score BETWEEN 0 AND 10),
    status        TEXT NOT NULL DEFAULT 'researching' CHECK (status IN
                  ('researching','validating','building','live','paused','dead')),
    evidence      TEXT NOT NULL,
    external_product_id TEXT,
    death_note    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS payments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    provider      TEXT NOT NULL,
    order_id      TEXT NOT NULL,
    product_id    TEXT NOT NULL DEFAULT '',
    venture_id    INTEGER REFERENCES ventures(id),
    currency      TEXT NOT NULL,
    gross_cents   INTEGER NOT NULL,
    recorded_cents INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL CHECK (status IN
                  ('recorded','fx_unhandled','refunded','refund_recorded','ignored')),
    UNIQUE (provider, order_id)
);
"""

TASK_AGENTS = ("scout", "builder", "seller", "treasurer", "diplomat", "chronicler")

HUMAN_KINDS = (
    "login",
    "account_setup",
    "identity_verification",
    "payment_method_setup",
    "secret_provisioning",
    "red_tier_approval",
    "logged_in_action",
)

TASK_STATUSES = ("pending", "running", "blocked", "done", "failed", "rejected", "cancelled")

MAX_PENDING_TASKS = 10
MAX_TITLE_CHARS = 120
MAX_PROMPT_CHARS = 4000
MAX_INSTRUCTIONS_CHARS = 1500
HUMAN_TASKS_PER_DAY = 3

#: created_by value the orchestrator uses for its own human tasks. Tasks filed
#: under any other name count against the per-day agent limit.
ORCHESTRATOR = "orchestrator"


def utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%fZ")


def tomorrow_0005(now: datetime) -> str:
    """00:05 UTC of the next day, in ledger timestamp format."""
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return nxt.strftime("%Y-%m-%dT%H:%M:%fZ")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def find_secret(text: str) -> str | None:
    """Return a short description if text looks like it contains a secret, else None."""
    if not text:
        return None
    if re.search(r"sk-[A-Za-z0-9_\-]{8,}", text):
        return "looks like an API key (sk-...)"
    if re.search(r"Bearer\s+[A-Za-z0-9_\-.~+/=]{8,}", text):
        return "looks like a bearer token"
    if re.search(r"(?i)(?:password\s*:\s*\S+|passwd\s*=\s*\S+)", text):
        return "contains a password"
    for m in re.finditer(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{32,}={0,2}(?![A-Za-z0-9+/=])", text):
        token = m.group(0)
        if (
            len(token) >= 32
            and re.search(r"[A-Za-z]", token)
            and re.search(r"[0-9]", token)
        ):
            return "looks like a token or hash (long base64-like string)"
    if re.search(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,}(?![0-9a-fA-F])", text):
        return "looks like a token or hash (long hex string)"
    for m in re.finditer(r"(?<!\d)\d{13,19}(?!\d)", text):
        digits = m.group(0)
        if len(set(digits)) > 1 and _luhn_ok(digits):
            return "looks like a card number"
    return None


#: Patterns mirroring the v0.2 secret detector above (used for log redaction).
_REDACT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-.~+/=]{8,}"),
    re.compile(r"(?i)(?:password\s*:\s*\S+|passwd\s*=\s*\S+)"),
    re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{32,}={0,2}(?![A-Za-z0-9+/=])"),
    re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,}(?![0-9a-fA-F])"),
    re.compile(r"(?<!\d)\d{13,19}(?!\d)"),
)


def redact_secrets(text: str) -> str:
    """Mask anything the secret detector would flag (for logs)."""
    if not text:
        return text
    for rx in _REDACT_PATTERNS:
        text = rx.sub("[REDACTED]", text)
    return text


class Store:
    """Typed access to the queue tables (tasks, human_tasks, runs, kv)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @contextmanager
    def _tx(self) -> Iterator[None]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    # ---------- tasks ----------
    def create_task(
        self,
        *,
        agent: str,
        title: str,
        prompt: str,
        priority: int = 5,
        requires_review: bool = False,
        created_by: str,
        not_before: str | None = None,
    ) -> dict:
        if agent == "brain" or agent not in TASK_AGENTS:
            return {
                "status": "error",
                "reason": f"unknown task agent: {agent} (the brain is not a task agent)",
            }
        if not title or len(title) > MAX_TITLE_CHARS:
            return {"status": "error", "reason": "title is required, max 120 chars"}
        if not prompt or len(prompt) > MAX_PROMPT_CHARS:
            return {"status": "error", "reason": "prompt is required, max 4000 chars"}
        if not isinstance(priority, int) or not 0 <= priority <= 9:
            return {"status": "error", "reason": "priority must be an int 0-9"}
        if not created_by:
            return {"status": "error", "reason": "created_by (caller) is required"}
        with self._tx():
            n = self.conn.execute(
                "SELECT COUNT(*) c FROM tasks WHERE status='pending'"
            ).fetchone()["c"]
            if n >= MAX_PENDING_TASKS:
                return {"status": "error", "reason": "too many pending tasks (max 10)"}
            cur = self.conn.execute(
                """INSERT INTO tasks(agent,title,prompt,priority,requires_review,
                                     created_by,not_before)
                   VALUES (?,?,?,?,?,?,?)""",
                (agent, title, prompt, priority, 1 if requires_review else 0,
                 created_by, not_before),
            )
            return {"status": "created", "task_id": int(cur.lastrowid)}

    def get_task(self, task_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, status: str | None = None, limit: int = 30) -> list[dict]:
        limit = max(1, min(limit, 200))
        if status is None:
            rows = self.conn.execute(
                "SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)
            )
        else:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE status=? ORDER BY id DESC LIMIT ?",
                (status, limit),
            )
        return [dict(r) for r in rows]

    def pending_tasks(self, now_iso: str) -> list[dict]:
        """Pending tasks whose not_before has passed, lowest priority then oldest first."""
        rows = self.conn.execute(
            """SELECT * FROM tasks WHERE status='pending'
               AND (not_before IS NULL OR not_before <= ?)
               ORDER BY priority ASC, id ASC""",
            (now_iso,),
        )
        return [dict(r) for r in rows]

    def next_task(self, now_iso: str) -> dict | None:
        rows = self.pending_tasks(now_iso)
        return rows[0] if rows else None

    def set_status(self, task_id: int, status: str, **fields) -> dict:
        if status not in TASK_STATUSES:
            return {"status": "error", "reason": f"unknown task status: {status}"}
        allowed = {
            "priority", "requires_review", "review", "blocked_on", "not_before",
            "attempts", "branch", "result_path", "result_summary", "prompt", "title",
        }
        unknown = set(fields) - allowed
        if unknown:
            return {"status": "error", "reason": f"unknown fields: {sorted(unknown)}"}
        sets = ["status=?", "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')"]
        values: list = [status]
        for key in sorted(fields):
            sets.append(f"{key}=?")
            values.append(fields[key])
        values.append(task_id)
        with self._tx():
            cur = self.conn.execute(
                f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", values
            )
            if not cur.rowcount:
                return {"status": "error", "reason": "task not found"}
        return {"status": "ok", "task_id": task_id}

    def task_counts(self) -> dict[str, int]:
        out = {s: 0 for s in TASK_STATUSES}
        for r in self.conn.execute("SELECT status, COUNT(*) c FROM tasks GROUP BY status"):
            out[r["status"]] = int(r["c"])
        return out

    def finished_summaries(self, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            """SELECT id, agent, title, status, result_summary FROM tasks
               WHERE status IN ('done','failed','rejected')
               ORDER BY id DESC LIMIT ?""",
            (max(1, min(limit, 100)),),
        )
        return [dict(r) for r in rows]

    # ---------- human tasks ----------
    def add_human_task(
        self,
        *,
        kind: str,
        title: str,
        instructions: str,
        url: str = "",
        dedupe_key: str,
        created_by: str,
        blocks_task_id: int | None = None,
    ) -> dict:
        if kind not in HUMAN_KINDS:
            return {
                "status": "error",
                "reason": (
                    "humans are only contacted for logins/account actions "
                    f"(kind must be one of {', '.join(HUMAN_KINDS)}); "
                    "decide everything else yourself"
                ),
            }
        if not title or len(title) > MAX_TITLE_CHARS:
            return {"status": "error", "reason": "title is required, max 120 chars"}
        if not instructions or len(instructions) > MAX_INSTRUCTIONS_CHARS:
            return {"status": "error", "reason": "instructions required, max 1500 chars"}
        if not dedupe_key:
            return {"status": "error", "reason": "dedupe_key is required"}
        if not created_by:
            return {"status": "error", "reason": "created_by (caller) is required"}
        secret = find_secret(title) or find_secret(instructions) or find_secret(url)
        if secret:
            return {
                "status": "error",
                "reason": (
                    f"refused: text {secret}; secrets must never be sent through "
                    "the inbox (tell the human to put them in .env instead)"
                ),
            }
        with self._tx():
            existing = self.conn.execute(
                "SELECT * FROM human_tasks WHERE dedupe_key=?", (dedupe_key,)
            ).fetchone()
            if existing:
                return {"status": "exists", "task": dict(existing)}
            if created_by != ORCHESTRATOR:
                n = self.conn.execute(
                    """SELECT COUNT(*) c FROM human_tasks
                       WHERE date(ts)=date('now') AND created_by != ?""",
                    (ORCHESTRATOR,),
                ).fetchone()["c"]
                if n >= HUMAN_TASKS_PER_DAY:
                    return {
                        "status": "error",
                        "reason": (
                            "at most 3 new human tasks per day; batch your needs "
                            "into one task and continue with other work"
                        ),
                    }
            if blocks_task_id is not None:
                blocked = self.conn.execute(
                    "SELECT * FROM tasks WHERE id=?", (blocks_task_id,)
                ).fetchone()
                if blocked is None:
                    return {"status": "error", "reason": "blocked task not found"}
                if blocked["status"] not in ("pending", "running"):
                    return {"status": "error", "reason": "blocked task is not open"}
            cur = self.conn.execute(
                """INSERT INTO human_tasks(kind,title,instructions,url,created_by,dedupe_key)
                   VALUES (?,?,?,?,?,?)""",
                (kind, title, instructions, url, created_by, dedupe_key),
            )
            hid = int(cur.lastrowid)
            if blocks_task_id is not None:
                self.conn.execute(
                    """UPDATE tasks SET status='blocked', blocked_on=?,
                       updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""",
                    (hid, blocks_task_id),
                )
            row = self.conn.execute(
                "SELECT * FROM human_tasks WHERE id=?", (hid,)
            ).fetchone()
            return {"status": "created", "task": dict(row)}

    def get_human_task(self, task_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM human_tasks WHERE id=?", (task_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_human_task_by_key(self, dedupe_key: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM human_tasks WHERE dedupe_key=?", (dedupe_key,)
        ).fetchone()
        return dict(row) if row else None

    def list_human_tasks(self, status: str = "open") -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM human_tasks WHERE status=? ORDER BY id", (status,)
        )
        return [dict(r) for r in rows]

    def open_human_tasks(self) -> list[dict]:
        return self.list_human_tasks("open")

    def resolve_human_task(
        self, task_id: int, *, status: str = "done", note: str = ""
    ) -> dict:
        if status not in ("done", "dismissed"):
            return {"status": "error", "reason": "status must be done or dismissed"}
        with self._tx():
            cur = self.conn.execute(
                """UPDATE human_tasks SET status=?, resolved_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                   note=? WHERE id=? AND status='open'""",
                (status, note, task_id),
            )
            if not cur.rowcount:
                return {"status": "error", "reason": "no open human task found"}
            self.conn.execute(
                """UPDATE tasks SET status='pending', blocked_on=NULL,
                   updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                   WHERE blocked_on=? AND status='blocked'""",
                (task_id,),
            )
        return {"status": status, "task_id": task_id}

    def unblock(self, human_task_id: int) -> int:
        """Set tasks blocked on a human task back to pending. Returns count."""
        with self._tx():
            cur = self.conn.execute(
                """UPDATE tasks SET status='pending', blocked_on=NULL,
                   updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                   WHERE blocked_on=? AND status='blocked'""",
                (human_task_id,),
            )
            return cur.rowcount

    # ---------- runs ----------
    def log_run(
        self,
        *,
        agent: str,
        task_id: int | None = None,
        model: str = "",
        est_cost_cents: int = 0,
        duration_s: float = 0.0,
        exit_code: int | None = None,
        status: str,
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO runs(agent,task_id,model,est_cost_cents,duration_s,exit_code,status)
               VALUES (?,?,?,?,?,?,?)""",
            (agent, task_id, model, est_cost_cents, duration_s, exit_code, status),
        )
        return int(cur.lastrowid)

    def start_run(self, *, agent: str, task_id: int | None = None,
                  model: str = "", est_cost_cents: int = 0) -> int:
        """Allocate the runs row first so the broker session can bind to run_id."""
        cur = self.conn.execute(
            "INSERT INTO runs(agent,task_id,model,est_cost_cents,status)"
            " VALUES (?,?,?,?,'running')",
            (agent, task_id, model, est_cost_cents),
        )
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, *, duration_s: float,
                   exit_code: int | None, status: str) -> None:
        self.conn.execute(
            "UPDATE runs SET duration_s=?, exit_code=?, status=? WHERE id=?",
            (duration_s, exit_code, status, run_id),
        )

    # ---------- kv ----------
    def kv_get(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def kv_set(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO kv(key,value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
