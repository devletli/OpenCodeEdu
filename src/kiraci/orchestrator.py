from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import builder_flow
from .config import load_config
from .db import connect
from .ledger import Ledger
from .notify import maybe_send_digest, notify_human
from .review import review_approvals
from .store import ORCHESTRATOR, Store, utcnow_iso
from .testing import FakeRunner

SURVIVAL_TOTAL_CENTS = 1000

#: agent -> list of (open, close) UTC windows. Priority-0 tasks ignore windows.
WINDOWS: dict[str, list[tuple[tuple[int, int], tuple[int, int]]]] = {
    "scout": [((7, 0), (12, 0))],
    "builder": [((12, 30), (18, 0))],
    "seller": [((12, 30), (18, 0))],
    "diplomat": [((18, 0), (19, 0))],
    "treasurer": [((6, 0), (7, 0)), ((20, 0), (21, 0))],
    "chronicler": [((20, 0), (21, 0))],
}

CONTENT_DIRS = ("journal", "research", "people", "personas", "skills", "products", "tools")
ALL_DIRS = CONTENT_DIRS + ("workspace", "data/outputs")

BOOTSTRAP_PARAGRAPH = (
    "This is the first start. Decide which real-world accounts and logins are needed "
    "to earn money (for example a payment provider account that pays out to the owner, "
    "a domain or storefront account) and request them with `queue_request_human_action`. "
    "Batch them: at most 3 human tasks, each with exact step-by-step instructions and "
    "a URL, never containing secrets. Then create research tasks that do not depend "
    "on those accounts."
)


def _hm(now: datetime) -> tuple[int, int]:
    t = now.timetz() if now.tzinfo else now.time()
    return t.hour, t.minute


def window_open(agent: str, now: datetime) -> bool:
    h, m = _hm(now)
    nowm = h * 60 + m
    for (sh, sm), (eh, em) in WINDOWS.get(agent, []):
        if sh * 60 + sm <= nowm < eh * 60 + em:
            return True
    return False


def in_night(now: datetime) -> bool:
    h, m = _hm(now)
    return h * 60 + m >= 22 * 60 or h * 60 + m < 6 * 60


def in_awake_hours(now: datetime) -> bool:
    return not in_night(now)


def current_phase(now: datetime) -> str:
    h, mm = _hm(now)
    if h >= 22 or h < 6:
        return "sleep"
    if (h, mm) < (6, 30):
        return "wake-up"
    if (h, mm) < (7, 0):
        return "morning-meeting"
    if (h, mm) < (12, 0):
        return "research"
    if (h, mm) < (12, 30):
        return "midday"
    if (h, mm) < (18, 0):
        return "production"
    if (h, mm) < (19, 0):
        return "social"
    if (h, mm) < (20, 0):
        return "evening"
    return "close"


def daily_burn_cents(ledger: Ledger, days: int = 7) -> int:
    row = ledger.conn.execute(
        """SELECT COALESCE(-SUM(delta_cents),0) s FROM ledger
           WHERE kind='expense' AND date(ts) >= date('now', ?)""",
        (f"-{days - 1} days",),
    ).fetchone()
    return int(row["s"]) // days


def runway_str(total_cents: int, burn_per_day: int) -> str:
    if burn_per_day <= 0:
        return "unlimited (no recent burn)"
    return f"{total_cents / burn_per_day:.1f} days"


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-")
    return slug or "task"


def build_status(store: Store, ledger: Ledger, now: datetime) -> str:
    balances = ledger.balances()
    total = ledger.total_balance()
    burn = daily_burn_cents(ledger)
    counts = store.task_counts()
    open_human = store.open_human_tasks()
    pending = ledger.pending()
    last_tick = store.kv_get("last_tick", "never")
    lines = [
        f"Date: {now.strftime('%Y-%m-%d %H:%M UTC')}  Phase: {current_phase(now)}",
        f"Balances (EUR): {{{', '.join(f'{k}: {v / 100:.2f}' for k, v in balances.items())}}}",
        (f"Total (ex-owner): EUR {total / 100:.2f}  "
         f"Burn (7d avg): EUR {burn / 100:.2f}/day  Runway: {runway_str(total, burn)}"),
        f"Open human tasks: {len(open_human)}  Pending approvals: {len(pending)}",
        f"Tasks by status: {counts}  Last tick: {last_tick}",
    ]
    return "\n".join(lines)


class Orchestrator:
    def __init__(self, *, root, store, ledger, config, runner, clock=None):
        self.root = Path(root)
        self.store = store
        self.ledger = ledger
        self.config = config
        self.runner = runner
        self.clock = clock or (lambda: datetime.now(UTC))
        self.stopped = False

    def now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return now

    # ---------- startup ----------
    def startup(self) -> None:
        for d in ALL_DIRS:
            (self.root / d).mkdir(parents=True, exist_ok=True)
        for d in CONTENT_DIRS:
            keep = self.root / d / ".gitkeep"
            if not keep.exists():
                keep.write_text("", encoding="utf-8")
        missing = self.config.missing_tier_envs()
        if missing:
            result = self.store.add_human_task(
                kind="secret_provisioning",
                title="Configure model credentials",
                instructions=(
                    "The orchestrator cannot run some agents: these environment "
                    f"variables are missing: {', '.join(missing)}. Put them into "
                    "the .env file next to the service (format provider/model, "
                    "e.g. KIRACI_MODEL_CHEAP=openrouter/my-model). "
                    "Never send secrets through chat; edit .env on the host."
                ),
                dedupe_key="env-models",
                created_by=ORCHESTRATOR,
            )
            if result.get("status") == "created":
                try:
                    notify_human(result["task"], root=self.root, store=self.store)
                except (OSError, sqlite3.Error) as e:
                    print(f"kiraci: startup notify failed: {e}", file=sys.stderr)

    # ---------- jobs ----------
    def _job_due(self, name: str, hhmm: str, now: datetime, weekday: int | None = None) -> bool:
        if weekday is not None and now.weekday() != weekday:
            return False
        day = now.strftime("%Y-%m-%d")
        if self.store.kv_get(f"job:{name}:{day}"):
            return False
        hh, mm = int(hhmm[:2]), int(hhmm[3:])
        start = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        return start <= now < start + timedelta(hours=2)

    def _mark_job(self, name: str, now: datetime) -> None:
        self.store.kv_set(f"job:{name}:{now.strftime('%Y-%m-%d')}", "1")

    def _queue_helper_task(self, agent: str, title: str, prompt: str) -> str:
        r = self.store.create_task(agent=agent, title=title, prompt=prompt,
                                   priority=5, created_by=ORCHESTRATOR)
        if r.get("status") == "created":
            return f"queued {agent} task #{r['task_id']}"
        return f"queue failed: {r.get('reason')}"

    def _brain_session(self, job: str, now: datetime, extra: str = "") -> tuple[str, bool]:
        if self.config.model_for("brain") is None:
            return "brain skipped (no model)", False
        status_text = build_status(self.store, self.ledger, now)
        finished = self.store.finished_summaries(10)
        fin_lines = "\n".join(
            f"- #{t['id']} [{t['agent']}/{t['status']}] {t['title']}: "
            f"{t['result_summary'][:200]}"
            for t in finished
        ) or "(none yet)"
        open_h = self.store.open_human_tasks()
        human_lines = "\n".join(
            f"- #{t['id']} [{t['kind']}] {t['title']}" for t in open_h
        ) or "(none open)"
        prompt = (
            f"Kiraci planning session ({job}) on {now.strftime('%Y-%m-%d %H:%M UTC')}.\n"
            f"Status:\n{status_text}\n\nRecent finished tasks:\n{fin_lines}\n\n"
            f"Open human tasks:\n{human_lines}\n\n"
            "Create at most 5 new tasks with `queue_create_task` (always pass "
            "caller=\"brain\"). Score ideas per KIRACI.md Section 5, reject below 6, "
            "prefer cheap reversible experiments, demand evidence. Titles of tasks "
            "that directly aim at revenue start with \"[revenue]\".\n"
            f"{extra}\n"
            "Your final answer is a short summary: decisions taken, tasks created, and why."
        )
        timeout = int(self.config.limits.get("run_timeout_seconds", 1200))
        res = self.runner.run("brain", prompt, self.root, timeout)
        out_dir = self.root / "data" / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"brain-{now.strftime('%Y-%m-%d')}-{job}.md"
        try:
            out_path.write_text(res.text, encoding="utf-8")
        except OSError:
            pass
        if res.skipped_reason is not None:
            return f"brain skipped ({res.skipped_reason})", False
        return f"brain session ({'ok' if res.ok else 'failed'})", res.ok

    def _git_snapshot(self, now: datetime) -> str:
        def git(*args):
            return subprocess.run(
                ["git", *args], cwd=str(self.root), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                check=False,
            )

        git("add", "research", "journal", "people", "skills")
        if not git("status", "--porcelain", "--", "research", "journal",
                   "people", "skills").stdout.strip():
            return "snapshot: no changes"
        c = git("-c", "user.name=kiraci-bot", "-c", "user.email=bot@kiraci.local",
                "-c", f"core.hooksPath={os.devnull}",
                "commit", "-m", f"snapshot {now.strftime('%Y-%m-%d')}")
        if c.returncode == 0:
            return "snapshot committed"
        return "snapshot commit failed"

    # ---------- dispatch ----------
    def _dispatch(self, now: datetime, survival: bool) -> str:
        cands = self.store.pending_tasks(utcnow_iso())
        for t in cands:
            if t["priority"] != 0 and not window_open(t["agent"], now):
                continue
            if survival and (
                self.config.cost_for(t["agent"]) > 0
                or not (t["title"].startswith("[revenue]") or t["agent"] == "treasurer")
            ):
                continue
            if self.config.model_for(t["agent"]) is None:
                continue
            return self._run_task(t, now, survival)
        return "dispatched none"

    def _note_outcome(self, ok: bool | None, now: datetime) -> None:
        if ok is None:
            return
        if ok:
            self.store.kv_set("consec_failures", "0")
            return
        n = int(self.store.kv_get("consec_failures", "0") or 0) + 1
        self.store.kv_set("consec_failures", str(n))
        if n > int(self.config.limits.get("max_consecutive_failures", 5)):
            until = now + timedelta(minutes=60)
            self.store.kv_set("dispatch_paused_until", until.isoformat())

    def _dispatch_paused(self, now: datetime) -> bool:
        until = self.store.kv_get("dispatch_paused_until")
        if not until:
            return False
        try:
            return datetime.fromisoformat(until) > now
        except ValueError:
            return False

    def _write_result(self, task: dict, text: str, now: datetime) -> str:
        day = now.strftime("%Y-%m-%d")
        slug = slugify(task["title"])
        agent = task["agent"]
        if agent == "scout":
            path = self.root / "research" / f"{day}-{task['id']}-{slug}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        elif agent == "chronicler":
            path = self.root / "journal" / f"{day}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(f"\n## Task #{task['id']}: {task['title']}\n\n{text}\n")
        elif agent == "seller":
            path = self.root / "products" / "drafts" / f"{task['id']}-{slug}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        elif agent == "diplomat":
            path = self.root / "people" / "drafts" / f"{task['id']}-{slug}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        elif agent == "treasurer":
            path = self.root / "data" / "outputs" / f"{task['id']}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        else:
            return ""
        return str(path)

    def _run_task(self, task: dict, now: datetime, survival: bool) -> str:
        from .store import tomorrow_0005

        tid = task["id"]
        timeout = int(self.config.limits.get("run_timeout_seconds", 1200))
        max_attempts = int(self.config.limits.get("max_task_attempts", 3))
        if task["agent"] == "builder":
            outcome = builder_flow.run_builder_task(
                task_id=tid, store=self.store, runner=self.runner,
                config=self.config, repo_root=self.root, now=now,
            )
            self._note_outcome(None if outcome == "skipped" else outcome == "done"
                               or outcome == "rejected", now)
            return f"builder task #{tid} {outcome}"
        self.store.set_status(tid, "running")
        res = self.runner.run(task["agent"], task["prompt"], self.root, timeout)
        if res.skipped_reason is not None:
            self.store.set_status(tid, "pending", not_before=tomorrow_0005(now),
                                  result_summary=f"skipped: {res.skipped_reason}")
            self._note_outcome(None, now)
            return f"task #{tid} deferred to tomorrow ({res.skipped_reason})"
        if not res.ok:
            attempts = int(task.get("attempts", 0)) + 1
            summary = f"run failed (exit {res.exit_code}): {res.text[:500]}"
            if attempts >= max_attempts:
                self.store.set_status(tid, "failed", attempts=attempts,
                                      result_summary=summary)
            else:
                self.store.set_status(tid, "pending", attempts=attempts,
                                      result_summary=summary)
            self._note_outcome(False, now)
            return f"task #{tid} failed (attempt {attempts})"
        try:
            result_path = self._write_result(task, res.text, now)
        except OSError as e:
            result_path = ""
            res_text = f"[result file write failed: {e}]\n{res.text}"
        else:
            res_text = res.text
        self.store.set_status(tid, "done", result_path=result_path,
                              result_summary=res_text[:500])
        self._note_outcome(True, now)
        return f"task #{tid} done"

    # ---------- tick ----------
    def tick(self) -> str:
        now = self.now()
        iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.store.kv_set("last_tick", iso)
        if (self.root / "data" / "KILL").exists():
            self.stopped = True
            return f"{iso} killed"
        if (self.root / "data" / "PAUSE").exists():
            return f"{iso} paused"
        events: list[str] = []
        survival = self.ledger.total_balance() < SURVIVAL_TOTAL_CENTS
        if survival:
            events.append("SURVIVAL")

        free_mb = shutil.disk_usage(str(self.root)).free // (1024 * 1024)
        if free_mb < int(self.config.limits.get("min_free_disk_mb", 1024)):
            (self.root / "data" / "PAUSE").touch()
            line = f"\n[{iso}] WATCHDOG: free disk {free_mb} MB, paused.\n"
            inbox = self.root / "HUMAN_INBOX.md"
            with inbox.open("a", encoding="utf-8") as f:
                f.write(line)
            events.append("disk-full->PAUSE")

        paused = self._dispatch_paused(now)
        if paused:
            events.append("llm-paused")

        if in_awake_hours(now):
            balances = self.ledger.balances()
            total = self.ledger.total_balance()
            burn = daily_burn_cents(self.ledger)
            counts = review_approvals(
                store=self.store, ledger=self.ledger, runner=self.runner,
                config=self.config, balances=balances,
                runway_str=runway_str(total, burn),
                judge_enabled=not paused and not survival,
                repo_root=self.root,
                timeout_s=int(self.config.limits.get("run_timeout_seconds", 1200)),
                notify_fn=lambda t: notify_human(t, root=self.root, store=self.store),
            )
            filed = [f"{k}={v}" for k, v in counts.items() if v]
            events.append("review:" + (",".join(filed) if filed else "none"))

            jobs = self._run_jobs(now, paused, survival)
            events.extend(jobs)

            if not paused and not in_night(now):
                events.append(self._dispatch(now, survival))
            else:
                events.append("dispatch:none (night)" if in_night(now)
                              else "dispatch:none (paused)")
        else:
            events.append("night: watchdog only")

        try:
            maybe_send_digest(self.store, root=self.root)
        except (OSError, sqlite3.Error, ValueError) as e:
            print(f"kiraci: digest failed: {e}", file=sys.stderr)
        return f"{iso} phase={current_phase(now)} " + " ".join(events)

    def _run_jobs(self, now: datetime, paused: bool, survival: bool) -> list[str]:
        events: list[str] = []
        if self._job_due("morning_report", "06:00", now):
            events.append(self._queue_helper_task(
                "treasurer", "Daily cash report",
                "Write today's opening cash report from the ledger: balances, "
                "daily burn rate, runway in days, pending approvals, unusual spending. "
                "Read every number from the ledger, never estimate."))
            self._mark_job("morning_report", now)
        if self._job_due("morning_plan", "06:30", now):
            if paused or survival:
                events.append("morning_plan skipped (paused/survival)")
            else:
                msg, _ = self._brain_session("morning_plan", now)
                events.append(msg)
            self._mark_job("morning_plan", now)
        if self._job_due("midday_review", "12:00", now):
            if paused or survival:
                events.append("midday_review skipped (paused/survival)")
            else:
                msg, _ = self._brain_session("midday_review", now)
                events.append(msg)
            self._mark_job("midday_review", now)
        if self._job_due("evening_close", "20:00", now):
            events.append(self._queue_helper_task(
                "treasurer", "End-of-day cash close",
                "Write the end-of-day cash report from the ledger: closing balances, "
                "today's spend by bucket, pending approvals. Numbers from the ledger only."))
            self._mark_job("evening_close", now)
        if self._job_due("journal", "20:15", now):
            events.append(self._queue_helper_task(
                "chronicler", "Daily journal",
                "Write today's journal: what was done, earned/spent, learned, failed. "
                "Failures plainly, with a dead-venture note where fitting. "
                "Numbers from the ledger."))
            self._mark_job("journal", now)
        if self._job_due("git_snapshot", "20:30", now):
            events.append(self._git_snapshot(now))
            self._mark_job("git_snapshot", now)
        if self._job_due("weekly_retro", "20:30", now, weekday=6):
            events.append(self._queue_helper_task(
                "chronicler", "Weekly retrospective",
                "Write the weekly retrospective: what earned, what lost, which agent "
                "was inefficient, which assumption was wrong. Turn methods that worked "
                "into skill proposals."))
            if paused or survival:
                events.append("weekly brain skipped (paused/survival)")
            else:
                msg, _ = self._brain_session("weekly_retro", now)
                events.append(msg)
            self._mark_job("weekly_retro", now)
        if self.store.kv_get("bootstrapped") is None:
            msg, ran = self._brain_session("bootstrap", now, BOOTSTRAP_PARAGRAPH)
            events.append("bootstrap: " + msg)
            if ran:
                self.store.kv_set("bootstrapped", "1")
        return events

    # ---------- daemon ----------
    def run_forever(self) -> int:
        def _stop(signum, frame):
            self.stopped = True

        for sig in ("SIGTERM", "SIGINT"):
            try:
                signal.signal(getattr(signal, sig), _stop)
            except (AttributeError, OSError, ValueError):
                pass
        tick_s = int(self.config.limits.get("tick_seconds", 30))
        while not self.stopped:
            print(self.tick(), flush=True)
            if self.stopped:
                break
            time.sleep(tick_s)
        return 0


def build_orchestrator(*, dry_run: bool = False):
    from .runner import OpencodeRunner

    root = Path.cwd().resolve()
    kiracidb = os.path.abspath(os.environ.get("KIRACI_DB", "data/kiraci.db"))
    os.environ["KIRACI_DB"] = kiracidb
    conn = connect(kiracidb)
    store = Store(conn)
    ledger = Ledger(conn)
    config = load_config()
    if dry_run:
        runner = FakeRunner(default="dry-run placeholder: no opencode, no spending")
    else:
        runner = OpencodeRunner(ledger=ledger, store=store, config=config)
    orch = Orchestrator(root=root, store=store, ledger=ledger,
                        config=config, runner=runner)
    orch.startup()
    return orch


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kiraci.orchestrator")
    p.add_argument("--once", action="store_true", help="run a single tick and exit")
    p.add_argument("--dry-run", action="store_true",
                   help="use a fake runner: no opencode, no spending")
    args = p.parse_args(argv)
    orch = build_orchestrator(dry_run=args.dry_run)
    if args.once:
        print(orch.tick(), flush=True)
        return 0
    return orch.run_forever()


if __name__ == "__main__":
    raise SystemExit(main())
