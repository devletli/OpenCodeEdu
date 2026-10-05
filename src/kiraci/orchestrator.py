from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import builder_flow, product_check, usage, ventures
from . import metrics as metrics_mod
from . import payments as payments_mod
from . import sandbox as sandbox_mod
from . import skills as skills_mod
from .backup import run_backup
from .config import Config, load_config
from .db import connect
from .ledger import Ledger
from .logsetup import get_logger
from .notify import maybe_send_digest, notify_human, send_info
from .review import review_approvals
from .runner import Runner
from .sandbox import Sandbox
from .store import ORCHESTRATOR, Store, utcnow_iso
from .testing import FakeRunner
from .verify import verify_ledger

SURVIVAL_TOTAL_CENTS = 1000

#: agent -> list of (open, close) UTC windows. Priority-0 tasks ignore windows.
#: Continuous operation: every agent may dispatch 06:00-22:00 UTC whenever its
#: queue is non-empty (free models make idle gaps pointless). The 22:00-06:00
#: night blackout is enforced separately in tick() and stays absolute.
WINDOWS: dict[str, list[tuple[tuple[int, int], tuple[int, int]]]] = {
    "scout": [((6, 0), (22, 0))],
    "builder": [((6, 0), (22, 0))],
    "seller": [((6, 0), (22, 0))],
    "diplomat": [((6, 0), (22, 0))],
    "treasurer": [((6, 0), (22, 0))],
    "chronicler": [((6, 0), (22, 0))],
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


def genesis_age_days(conn: sqlite3.Connection, now: datetime) -> int | None:
    """Days since the first fund entry (the day-90 clock). None if no genesis."""
    ts = metrics_mod.genesis_ts(conn)
    if ts is None:
        return None
    try:
        genesis = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        try:
            genesis = datetime.fromisoformat(ts)
        except ValueError:
            return None
    return (now - genesis).days


def metrics_line(root: Path) -> str:
    latest = metrics_mod.latest_metrics(root)
    if latest is None:
        return "No metrics report exists yet."
    return f"Latest metrics report: {latest}."


def build_status(store: Store, ledger: Ledger, now: datetime) -> str:
    balances = ledger.balances()
    total = ledger.total_balance()
    burn = daily_burn_cents(ledger)
    counts = store.task_counts()
    open_human = store.open_human_tasks()
    pending = ledger.pending()
    last_tick = store.kv_get("last_tick", "never")
    tokens_today = ledger.spent_today("tokens")
    tokens_cap = ledger.policy.daily_caps_cents.get("tokens", 60)
    lines = [
        f"Date: {now.strftime('%Y-%m-%d %H:%M UTC')}  Phase: {current_phase(now)}",
        f"Balances (EUR): {{{', '.join(f'{k}: {v / 100:.2f}' for k, v in balances.items())}}}",
        (f"Total (ex-owner): EUR {total / 100:.2f}  "
         f"Burn (7d avg): EUR {burn / 100:.2f}/day  Runway: {runway_str(total, burn)}"),
        (f"Tokens today: EUR {tokens_today / 100:.2f} "
         f"(cap EUR {tokens_cap / 100:.2f})"),
        f"Frozen: {'YES - agent tools refuse' if store.is_frozen() else 'no'}",
        f"Open human tasks: {len(open_human)}  Pending approvals: {len(pending)}",
        f"Tasks by status: {counts}  Last tick: {last_tick}",
    ]
    return "\n".join(lines)


class Orchestrator:
    def __init__(self, *, root: Path | str, store: Store, ledger: Ledger,
                 config: Config, runner: Runner,
                 clock: Callable[[], datetime] | None = None,
                 sandbox: Sandbox | None = None) -> None:
        self.root = Path(root)
        self.store = store
        self.ledger = ledger
        self.config = config
        self.runner = runner
        self.sandbox = sandbox
        self.clock = clock or (lambda: datetime.now(UTC))
        self.stopped = False
        self.log = get_logger(self.root)

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
                    self.log.warning("startup notify failed: %s", e)
        resumed = self._resume_interrupted()
        if resumed:
            self.log.warning(f"resumed {resumed} interrupted task(s) to pending")

    def _resume_interrupted(self) -> int:
        """Restart recovery: tasks left `running` never had their run finish
        (the daemon died mid-task, e.g. a WSL reboot). Send them back to
        `pending` with attempts+1 so the attempts guard stays honest and the
        next ticks pick them up. `blocked` tasks keep waiting on the human."""
        n = 0
        for t in self.store.list_tasks(status="running", limit=200):
            self.store.set_status(
                t["id"], "pending",
                attempts=int(t.get("attempts", 0)) + 1,
                result_summary="interrupted by restart; requeued")
            n += 1
        return n

    def _apply_survival_mode(self, survival: bool) -> None:
        """Point runners at the cheapest model tier in survival mode.

        Runners without the flag (e.g. FakeRunner) are left alone. The
        ledger spend gate and the cost-0 dispatch filter are unchanged:
        this only changes WHICH model a dispatched run uses.
        """
        runner = self.runner
        if hasattr(runner, "survival_mode"):
            runner.survival_mode = survival

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

    def _job_due_exact(self, name: str, hhmm: str, now: datetime) -> bool:
        """For reconcile_times_utc entries: due once per day after the time."""
        day = now.strftime("%Y-%m-%d")
        if self.store.kv_get(f"job:{name}:{day}"):
            return False
        hh, mm = int(hhmm[:2]), int(hhmm[3:])
        return now.replace(hour=hh, minute=mm, second=0,
                           microsecond=0) <= now

    def _notify_verify_findings(self, findings: list[str]) -> None:
        (self.root / "data").mkdir(parents=True, exist_ok=True)
        (self.root / "data" / "PAUSE").touch()
        self.log.error("ledger verify findings: %s", "; ".join(findings[:10]))
        send_info("Ledger verification FAILED; the system paused itself. "
                  "Findings: " + "; ".join(findings[:10]),
                  self.store, root=self.root)

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
            f"Status:\n{status_text}\n\n{metrics_line(self.root)}\n\n"
            f"Recent finished tasks:\n{fin_lines}\n\n"
            f"Open human tasks:\n{human_lines}\n\n"
            "Create at most 5 new tasks with `queue_create_task`. Score ideas per "
            "KIRACI.md Section 5, reject below 6, prefer cheap reversible "
            "experiments, demand evidence. Titles of tasks that directly aim at "
            "revenue start with \"[revenue]\".\n"
            f"{extra}\n"
            f"{self._wind_down_instruction(now)}"
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

    def _wind_down_instruction(self, now: datetime) -> str:
        """Day-60 rule: runway under 30 days means the brain must plan a wind-down."""
        age = genesis_age_days(self.ledger.conn, now)
        if age is None or not 60 <= age < 90:
            return ""
        burn = daily_burn_cents(self.ledger)
        total = self.ledger.total_balance()
        runway = total / burn if burn > 0 else float("inf")
        if runway >= 30:
            return ""
        return (
            "WIND-DOWN: the runway is under 30 days past day 60. Plan to stop all "
            "paid model use (free runs only), list what to keep running, and name "
            "the cheapest path to one more euro of revenue.\n"
        )

    def _publish_handoff(self, now: datetime) -> list[str]:
        """After a builder merge: validate venture packages, zip, file publish tasks."""
        events: list[str] = []
        for v in ventures.list_ventures(self.store.conn, "building"):
            slug = v["slug"]
            if v["external_product_id"]:
                continue
            pkg = self.root / "products" / slug
            if not pkg.is_dir():
                continue
            problems = product_check.check_product(pkg)
            if not problems:
                try:
                    product_check.build_dist_zip(pkg)
                except OSError as e:
                    events.append(f"handoff {slug}: zip failed ({e})")
                    continue
                res = self.store.add_human_task(
                    kind="logged_in_action",
                    title=f"Publish listing: {v['name']}",
                    instructions=(
                        f"Publish the '{v['name']}' product in the storefront "
                        "dashboard:\n"
                        f"1. Create a new listing. Title, price (EUR) and "
                        f"description are in products/{slug}/listing.md - copy "
                        "the description verbatim (it ends with the AI "
                        "disclosure line).\n"
                        f"2. Upload products/{slug}/dist/{slug}.zip as the "
                        "customer deliverable.\n"
                        "3. Keep tax/discount settings neutral (prices are final; "
                        "the provider handles tax).\n"
                        "4. When the listing is live, close the loop with: "
                        f"python -m kiraci.cli venture set-product {v['id']} "
                        "<external_product_id>"),
                    dedupe_key=f"publish:{slug}",
                    created_by=ORCHESTRATOR)
                if res.get("status") == "created":
                    try:
                        notify_human(res["task"], root=self.root, store=self.store)
                    except (OSError, sqlite3.Error) as e:
                        self.log.warning("handoff notify failed: %s", e)
                    events.append(f"handoff {slug}: publish task filed")
                self.store.kv_set(f"publish_rounds:{slug}", "0")
                continue
            fix_title = f"[venture:{slug}] fix product package"
            still_open = any(
                t["title"] == fix_title and t["status"] in ("pending", "running")
                for t in self.store.list_tasks(limit=200))
            if still_open:
                continue
            rounds = int(self.store.kv_get(f"publish_rounds:{slug}", "0") or 0) + 1
            self.store.kv_set(f"publish_rounds:{slug}", str(rounds))
            if rounds > 2:
                ventures.update_venture(self.store, self.root, v["id"], "paused")
                journal = self.root / "journal" / f"{now.strftime('%Y-%m-%d')}.md"
                journal.parent.mkdir(parents=True, exist_ok=True)
                with journal.open("a", encoding="utf-8") as f:
                    f.write(f"\n## Venture #{v['id']} paused\n\nProduct package "
                            f"failed validation {rounds} times: "
                            + "; ".join(problems[:5]) + "\n")
                events.append(f"handoff {slug}: paused after {rounds} failed rounds")
            else:
                r = self.store.create_task(
                    agent="builder", title=fix_title,
                    prompt=("The product package at products/" + slug + "/ failed "
                            "validation. Fix every problem below, keep "
                            "deliverable/ intact:\n- " + "\n- ".join(problems)),
                    priority=4, created_by=ORCHESTRATOR)
                if r.get("status") == "created":
                    events.append(f"handoff {slug}: fix task queued (round {rounds})")
                else:
                    events.append(f"handoff {slug}: fix queue failed ({r.get('reason')})")
        return events

    def _maybe_poll(self, now: datetime) -> str | None:
        """Payment poll every poll_minutes, around the clock, no LLM."""
        mins = int(self.config.revenue_value("poll_minutes"))
        last = self.store.kv_get("payments_last_poll")
        if last:
            try:
                if now - datetime.fromisoformat(last) < timedelta(minutes=mins):
                    return None
            except ValueError:
                pass
        self.store.kv_set("payments_last_poll", now.isoformat())
        name = str(self.config.revenue_value("payment_provider"))
        key = os.environ.get("LEMONSQUEEZY_API_KEY", "")
        provider = None
        if key and name == "lemonsqueezy":
            provider = payments_mod.LemonSqueezyProvider(
                key, store_id=str(self.config.revenue_value("payment_store_id")))
        res = payments_mod.poll(
            self.store, self.ledger, provider_name=name, api_key=key,
            fee_percent=int(self.config.revenue_value("payment_fee_percent")),
            fee_fixed=int(self.config.revenue_value("payment_fee_fixed_cents")),
            provider=provider, now=now)
        status = res.get("status")
        if status == "no-key-no-live":
            return None
        if status == "no-key":
            if res.get("human_task") == "created":
                return "payments: env-payments task filed"
            return None
        if status == "fetch-failed":
            return f"payments: fetch failed ({res.get('reason')})"
        if status == "error":
            return f"payments: {res.get('reason')}"
        parts = [f"{k}={res.get(k, 0)}" for k in
                 ("recorded", "ignored", "fx_unhandled", "refunds") if res.get(k)]
        return "payments:" + (",".join(parts) if parts else f"fetched={res.get('fetched', 0)}")

    def _day90(self, now: datetime, blocked: bool) -> str | None:
        """One-time day-90 review: brain + chronicler write journal/day-90-review.md."""
        if self.store.kv_get("day90_done"):
            return None
        age = genesis_age_days(self.ledger.conn, now)
        if age is None or age < 90:
            return None
        if blocked:
            return "day90 deferred (paused/survival)"
        if (self.config.model_for("brain") is None
                or self.config.model_for("chronicler") is None):
            return "day90 skipped (no model)"
        status_text = build_status(self.store, self.ledger, now)
        timeout = int(self.config.limits.get("run_timeout_seconds", 1200))
        bprompt = (
            "Day-90 review for the Kiraci system. Write exactly one of the two "
            "outcomes: EITHER monthly income >= monthly expenses (break-even "
            "reached, with the numbers) OR a specific 'why it did not work' "
            "report. End with a recommendation: continue / change strategy / "
            f"shut down.\n\nStatus:\n{status_text}")
        cprompt = (
            "Write the day-90 retrospective for journal/day-90-review.md with the "
            "same structure: break-even verdict with numbers or a specific "
            "why-not report, plus a continue / change strategy / shut down "
            f"recommendation.\n\nStatus:\n{status_text}")
        bres = self.runner.run("brain", bprompt, self.root, timeout)
        cres = self.runner.run("chronicler", cprompt, self.root, timeout)
        if bres.skipped_reason is not None or cres.skipped_reason is not None:
            return "day90 skipped (run refused)"
        path = self.root / "journal" / "day-90-review.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# Day-90 review ({now.strftime('%Y-%m-%d')})\n\n## Brain\n{bres.text}\n\n"
            f"## Chronicler\n{cres.text}\n", encoding="utf-8")
        self.store.kv_set("day90_done", "1")
        send_info("Day-90 review is ready in journal/day-90-review.md. "
                  "Continuing is the owner's decision.", self.store, root=self.root)
        return "day90 review written"

    def _git_snapshot(self, now: datetime) -> str:
        def git(*args: str) -> subprocess.CompletedProcess[str]:
            env = dict(os.environ)
            env["GIT_CONFIG_NOSYSTEM"] = "1"
            return subprocess.run(
                ["git", *args], cwd=str(self.root), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                check=False, env=env,
            )

        # TASK2.md Phase 1.2: durable local record in SQLite (best-effort,
        # never crashes the tick). Git commit below is kept for compatibility.
        try:
            from .daemon import save_snapshot

            changed = git(
                "status", "--porcelain", "--",
                "research", "journal", "people", "skills",
            ).stdout.strip()
            save_snapshot(
                "git_snapshot",
                {
                    "date": now.strftime("%Y-%m-%d"),
                    "changed_files": changed[:4000],
                    "root": str(self.root),
                },
            )
        except (OSError, sqlite3.Error, ValueError) as e:
            print(f"kiraci: snapshot record failed: {e}", flush=True)

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
    def _sandbox_gate(self, now: datetime) -> str:
        """ok | blocked (required mode, sandbox unavailable) | override.

        mode `required` with a not-ok sandbox dispatches nothing real and
        writes a system notice (inbox line + info Telegram, NOT a human task)
        once per day. The unsandboxed override (KIRACI_SANDBOX=off AND
        KIRACI_ALLOW_UNSANDBOXED=1) only ever lets no-bash/no-write agents run.
        """
        if self.sandbox is None:  # FakeRunner/dry-run: nothing real is executed
            return "ok"
        st = self.sandbox.status()
        if st == "ok":
            return "ok"
        if (os.environ.get("KIRACI_SANDBOX") == "off"
                and os.environ.get("KIRACI_ALLOW_UNSANDBOXED") == "1"):
            return "override"
        day = now.strftime("%Y-%m-%d")
        if self.store.kv_get("sandbox_notice_day") != day:
            self.store.kv_set("sandbox_notice_day", day)
            detail = ("the sandbox is not usable on this host"
                      if st == "unavailable" else "the sandbox is disabled")
            send_info(
                "No agent runs dispatched: sandbox mode is 'required' but "
                f"{detail}. Install bubblewrap and enable unprivileged user "
                "namespaces (see deploy/README.md), or set KIRACI_SANDBOX=off "
                "with KIRACI_ALLOW_UNSANDBOXED=1 to run read-only agents "
                "unsandboxed.", self.store, root=self.root)
            self.log.warning("dispatch blocked: sandbox status=%s", st)
        return "blocked"

    def _dispatch(self, now: datetime, survival: bool) -> str:
        gate = self._sandbox_gate(now)
        if gate == "blocked":
            return "dispatch:none (sandbox unavailable)"
        cands = self.store.pending_tasks(utcnow_iso())
        for t in cands:
            if t["priority"] != 0 and not window_open(t["agent"], now):
                continue
            if gate == "override" and (
                    self.sandbox is None
                    or not self.sandbox.unsandboxed_agent_allowed(t["agent"])):
                continue
            if survival and (
                self.config.cost_for(t["agent"]) > 0
                or not (t["title"].startswith("[revenue]") or t["agent"] == "treasurer")
            ):
                continue
            if usage.paid_paused(self.store, now) and self.config.cost_for(t["agent"]) > 0:
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

    def _write_result(self, task: dict[str, Any], text: str, now: datetime) -> str:
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

    def _run_task(self, task: dict[str, Any], now: datetime, survival: bool) -> str:
        from .store import tomorrow_0005

        tid = task["id"]
        timeout = int(self.config.limits.get("run_timeout_seconds", 1200))
        max_attempts = int(self.config.limits.get("max_task_attempts", 3))
        if task["agent"] == "builder":
            outcome = builder_flow.run_builder_task(
                task_id=tid, store=self.store, runner=self.runner,
                config=self.config, repo_root=self.root, now=now,
            )
            extra = ""
            if outcome == "done":
                hand = self._publish_handoff(now)
                if hand:
                    extra = " [" + "; ".join(hand) + "]"
            self._note_outcome(None if outcome == "skipped" else outcome == "done"
                               or outcome == "rejected", now)
            return f"builder task #{tid} {outcome}{extra}"
        self.store.set_status(tid, "running")
        prompt = task["prompt"]
        sel = skills_mod.select_for_task(self.root, task["agent"],
                                         task["title"], prompt)
        if sel:
            prompt = prompt + "\n\n## Relevant skills from past work\n" + sel
        res = self.runner.run(task["agent"], prompt, self.root, timeout,
                              task_id=tid)
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
        text_to_save = res.text
        reran = False
        if task["agent"] == "scout":
            text_to_save, reran = self._scout_evidence(task, res.text)
        try:
            result_path = self._write_result(task, text_to_save, now)
        except OSError as e:
            result_path = ""
            res_text = f"[result file write failed: {e}]\n{text_to_save}"
        else:
            res_text = text_to_save
        ingested = ""
        if task["agent"] == "chronicler" and task["title"] == "Weekly retrospective":
            saved = []
            for name, content in skills_mod.extract_skill_blocks(res.text):
                if skills_mod.save_skill(self.root, name, content) is None:
                    saved.append(name)
            if saved:
                ingested = f" saved skills: {', '.join(saved)}"
        if reran:
            self.store.set_status(tid, "pending", result_path=result_path,
                                  result_summary=(res_text[:500] + ingested))
            self._note_outcome(None, now)
            return f"task #{tid} saved, evidence re-run queued{ingested}"
        self.store.set_status(tid, "done", result_path=result_path,
                              result_summary=(res_text[:500] + ingested))
        self._note_outcome(True, now)
        return f"task #{tid} done{ingested}"

    def _scout_evidence(self, task: dict[str, Any], text: str) -> tuple[str, bool]:
        """Banner outputs with too few sources; queue at most one re-run."""
        need = int(self.config.revenue_value("min_sources_per_research"))
        if len(ventures.find_urls(text)) >= need:
            return text, False
        key = f"evidence_rerun:{task['id']}"
        if self.store.kv_get(key) is None:
            self.store.set_status(
                task["id"], "pending",
                prompt=task["prompt"] + "\n\nYour last answer had too few sources. "
                "Add verifiable URLs or say clearly what could not be verified.",
                result_summary=f"evidence re-run queued ({need} sources needed)")
            self.store.kv_set(key, "1")
        return f"> UNVERIFIED: fewer than {need} sources\n{text}", True

    # ---------- tick ----------
    def tick(self) -> str:
        now = self.now()
        iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.store.kv_set("last_tick", iso)
        if (self.root / "data" / "KILL").exists():
            self.stopped = True
            return f"{iso} killed"
        events: list[str] = []
        if (self.root / "data" / "PAUSE").exists():
            # Paused blocks all LLM work, but the deterministic no-LLM jobs
            # (reconcile, verify, backup) keep running around the clock.
            events.append("paused")
            events.extend(self._always_jobs(now))
            try:
                maybe_send_digest(self.store, root=self.root)
            except (OSError, sqlite3.Error, ValueError) as e:
                self.log.warning("digest failed: %s", e)
            return f"{iso} phase={current_phase(now)} " + " ".join(events)
        survival = self.ledger.total_balance() < SURVIVAL_TOTAL_CENTS
        self._apply_survival_mode(survival)
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
        frozen = self.store.is_frozen()
        if frozen:
            events.append("frozen: llm blocked")

        if in_awake_hours(now):
            balances = self.ledger.balances()
            total = self.ledger.total_balance()
            burn = daily_burn_cents(self.ledger)
            counts = review_approvals(
                store=self.store, ledger=self.ledger, runner=self.runner,
                config=self.config, balances=balances,
                runway_str=runway_str(total, burn),
                judge_enabled=not paused and not survival and not frozen,
                repo_root=self.root,
                timeout_s=int(self.config.limits.get("run_timeout_seconds", 1200)),
                notify_fn=lambda t: notify_human(t, root=self.root, store=self.store),
            )
            filed = [f"{k}={v}" for k, v in counts.items() if v]
            events.append("review:" + (",".join(filed) if filed else "none"))

            adv = ventures.auto_advance(self.store, self.root)
            if adv:
                events.append("ventures:" + ",".join(adv))
            poll_ev = self._maybe_poll(now)
            if poll_ev:
                events.append(poll_ev)

            jobs = self._run_jobs(now, paused, survival, frozen)
            events.extend(jobs)

            if not paused and not frozen and not in_night(now):
                events.append(self._dispatch(now, survival))
            else:
                events.append("dispatch:none (night)" if in_night(now)
                              else "dispatch:none (paused)" if paused
                              else "dispatch:none (frozen)")
        else:
            events.append("night: watchdog only")
            poll_ev = self._maybe_poll(now)
            if poll_ev:
                events.append(poll_ev)

        events.extend(self._always_jobs(now))
        try:
            maybe_send_digest(self.store, root=self.root)
        except (OSError, sqlite3.Error, ValueError) as e:
            self.log.warning("digest failed: %s", e)
        return f"{iso} phase={current_phase(now)} " + " ".join(events)

    def _always_jobs(self, now: datetime) -> list[str]:
        """Deterministic, no-LLM jobs that run around the clock (even paused):
        cost-truth reconcile, daily ledger verify, daily backup."""
        events: list[str] = []
        events.extend(self._cost_truth_jobs(now))
        if self._job_due("verify", "22:00", now):
            events.append(self._verify_job(now))
            self._mark_job("verify", now)
        backup_time = str(self.config.backup_value("time_utc"))
        if self._job_due("backup", backup_time, now):
            events.append(self._backup_job(now))
            self._mark_job("backup", now)
        return events

    def _cost_truth_jobs(self, now: datetime) -> list[str]:
        """Reconcile at [cost_truth].reconcile_times_utc; hard stop check throttled."""
        events: list[str] = []
        times = self.config.cost_truth_value("reconcile_times_utc") or []
        for hhmm in times:
            if self._job_due_exact(f"reconcile:{hhmm}", str(hhmm), now):
                probe = usage.get_probe(self.config)
                res = usage.reconcile(self.store, self.ledger, self.config,
                                      probe, now)
                self.store.kv_set("last_reconcile", now.isoformat())
                self._mark_job(f"reconcile:{hhmm}", now)
                if res.get("status") == "no-probe":
                    events.append("reconcile: no probe (env-usage-probe task filed)")
                elif res.get("status") == "probe-unreadable":
                    events.append("reconcile: probe unreadable")
                else:
                    events.append(
                        f"reconcile: actual={res.get('actual')} "
                        f"booked={res.get('booked')} delta={res.get('delta')}")
        last_check = self.store.kv_get("hardstop_checked_ts")
        try:
            checked = datetime.fromisoformat(last_check) if last_check else None
        except ValueError:
            checked = None
        if checked is None or (now - checked).total_seconds() >= 1800:
            self.store.kv_set("hardstop_checked_ts", now.isoformat())
            probe = usage.get_probe(self.config)
            stop = usage.check_hard_stop(self.store, self.config, probe, now)
            if stop:
                events.append(stop)
        return events

    def _verify_job(self, now: datetime) -> str:
        findings = verify_ledger(self.ledger.conn)
        self.store.kv_set("last_verify", json.dumps(
            {"ts": now.isoformat(), "findings": findings}))
        if findings:
            self._notify_verify_findings(findings)
            return f"verify: {len(findings)} findings, PAUSED"
        return "verify: healthy"

    def _backup_job(self, now: datetime) -> str:
        res = run_backup(self.ledger.conn, self.root, self.config, now=now)
        self.store.kv_set("last_backup", json.dumps(
            {"ts": now.isoformat(), "path": res.get("path", ""),
             "status": res.get("status")}))
        if res.get("status") != "ok":
            findings = res.get("findings", [])
            self.log.error("backup failed: %s", "; ".join(findings)[:500])
            send_info("Backup job failed: " + "; ".join(findings)[:500],
                      self.store, root=self.root)
            return f"backup: {res.get('status')}"
        return f"backup: {res['path']}"

    def _run_jobs(self, now: datetime, paused: bool, survival: bool, frozen: bool = False) -> list[str]:
        events: list[str] = []
        if self._job_due("morning_report", "06:00", now):
            events.append(self._queue_helper_task(
                "treasurer", "Daily cash report",
                "Write today's opening cash report from the ledger: balances, "
                "daily burn rate, runway in days, pending approvals, unusual spending. "
                "Read every number from the ledger, never estimate. "
                + metrics_line(self.root)))
            self._mark_job("morning_report", now)
        if self._job_due("morning_plan", "06:30", now):
            if paused or survival or frozen:
                events.append("morning_plan skipped (paused/survival/frozen)")
            else:
                msg, _ = self._brain_session("morning_plan", now)
                events.append(msg)
            self._mark_job("morning_plan", now)
        if self._job_due("midday_review", "12:00", now):
            if paused or survival or frozen:
                events.append("midday_review skipped (paused/survival/frozen)")
            else:
                msg, _ = self._brain_session("midday_review", now)
                events.append(msg)
            self._mark_job("midday_review", now)
        if self._job_due("evening_close", "20:00", now):
            events.append(self._queue_helper_task(
                "treasurer", "End-of-day cash close",
                "Write the end-of-day cash report from the ledger: closing balances, "
                "today's spend by bucket, pending approvals. Numbers from the ledger only. "
                + metrics_line(self.root)))
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
                "into skill proposals. Output zero to three new skills, each as a "
                "block starting with a line `SKILL: <kebab-name>` followed by the "
                "markdown file content (with front matter: title, agents, tags)."))
            if paused or survival or frozen:
                events.append("weekly brain skipped (paused/survival/frozen)")
            else:
                msg, _ = self._brain_session("weekly_retro", now)
                events.append(msg)
            self._mark_job("weekly_retro", now)
        if self._job_due("metrics", "20:15", now, weekday=6):
            path = metrics_mod.write_metrics(self.store, self.ledger, self.root, now)
            headline = metrics_mod.metrics_headline(self.root, 5)
            send_info(f"Weekly metrics ready ({path.name}):\n{headline}",
                      self.store, root=self.root)
            events.append(f"metrics written ({path.name})")
            self._mark_job("metrics", now)
        day90 = self._day90(now, paused or survival)
        if day90:
            events.append(day90)
        if self.store.kv_get("bootstrapped") is None:
            msg, ran = self._brain_session("bootstrap", now, BOOTSTRAP_PARAGRAPH)
            events.append("bootstrap: " + msg)
            if ran:
                self.store.kv_set("bootstrapped", "1")
        return events

    # ---------- daemon ----------
    def run_forever(self) -> int:
        def _stop(signum: Any, frame: Any) -> None:
            self.stopped = True

        for sig in ("SIGTERM", "SIGINT"):
            try:
                signal.signal(getattr(signal, sig), _stop)
            except (AttributeError, OSError, ValueError):
                pass
        tick_s = int(self.config.limits.get("tick_seconds", 30))
        while not self.stopped:
            self.log.info("%s", self.tick())
            if self.stopped:
                break
            time.sleep(tick_s)
        return 0


#: Crash-restart backoff for `kiraci run`: first retry after 5 s, doubling
#: to a 300 s cap. Only nonzero exits and uncaught exceptions restart;
#: exit code 0 (the KILL-file stop) always stays stopped.
BACKOFF_FIRST_S = 5.0
BACKOFF_MAX_S = 300.0


def supervise(build_run: Callable[[], int], sleep: Callable[[float], None] = time.sleep,
              max_restarts: int | None = None) -> int:
    """Run build_run() until it exits 0, restarting crashes with backoff.

    build_run() must build a FRESH orchestrator (fresh DB connection) on
    every call: a crash may have left the previous connection unusable.
    max_restarts bounds retries for tests; production passes None (forever).
    """
    delay = BACKOFF_FIRST_S
    restarts = 0
    log = get_logger(Path.cwd())
    while True:
        try:
            code = build_run()
        except Exception as e:  # noqa: BLE001 - supervisor must survive anything
            log.error("orchestrator crashed: %s", e)
            code = 1
        if code == 0:
            return 0
        restarts += 1
        if max_restarts is not None and restarts > max_restarts:
            return code
        # NOTE: f-string, not %-args: the secret-redaction filter
        # stringifies all log args, which breaks numeric %-formats.
        log.warning(f"orchestrator exited {code}; restarting in "
                    f"{delay:.0f}s (restart #{restarts})")
        sleep(delay)
        delay = min(delay * 2, BACKOFF_MAX_S)


def build_orchestrator(*, dry_run: bool = False) -> Orchestrator:
    from .runner import OpencodeRunner

    root = Path.cwd().resolve()
    kiracidb = os.path.abspath(os.environ.get("KIRACI_DB", "data/kiraci.db"))
    os.environ["KIRACI_DB"] = kiracidb
    conn = connect(kiracidb)
    store = Store(conn)
    ledger = Ledger(conn)
    config = load_config()
    runner: Runner
    if dry_run:
        # No opencode, no spending, no sandbox: FakeRunner does nothing real.
        runner = FakeRunner(default="dry-run placeholder: no opencode, no spending")
        orch = Orchestrator(root=root, store=store, ledger=ledger,
                            config=config, runner=runner)
    else:
        sbx = sandbox_mod.Sandbox(config=config, root=root)
        runner = OpencodeRunner(ledger=ledger, store=store, config=config,
                                sandbox=sbx, root=root)
        orch = Orchestrator(root=root, store=store, ledger=ledger,
                            config=config, runner=runner, sandbox=sbx)
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
