"""Continuous health watchdog with active recovery scenarios.

Runs as a plain process (`kiraci health`), no systemd dependency: every
`health_interval_s` it checks tick freshness, orphaned runs, disk space,
ledger integrity, backlog and sandbox state, and executes a recovery
scenario per failing check. Findings that need a human go through the
usual inbox/info channel, rate-limited.

Safety rules (mirroring the constitution, not extending it):
- A present `data/KILL` file means the owner stopped the system: report
  only, never start or change anything.
- Recovery never spends money, never approves anything, never runs agents:
  it restarts the daemon process, requeues orphaned tasks, and pauses on
  integrity findings. All state changes are the same ones the orchestrator
  itself would make.
- Only one health loop runs per root (pidfile); only one daemon is ever
  started (an existing fresh tick suppresses the start scenario).
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import heartbeat as heartbeat_mod
from .config import Config
from .ledger import Ledger
from .notify import send_info
from .store import Store
from .verify import verify_ledger

PIDFILE = "data/health.pid"

#: A `running` task older than this never had its run finish: the daemon
#: died mid-task (e.g. WSL reboot). Younger `running` rows belong to the
#: live daemon and must be left alone.
STALE_RUNNING_S = 30 * 60

#: One notice per key per window; recovery itself is retried every cycle.
NOTICE_EVERY_S = 6 * 3600

#: Pending queue above this only notifies (never auto-drops work).
BACKLOG_PENDING_N = 50

@dataclass
class Finding:
    name: str
    ok: bool
    detail: str = ""
    severity: str = "info"  # info | warn | crit


def _spawn_detached(argv: list[str], cwd: str) -> subprocess.Popen[Any]:
    log = Path(cwd) / "data" / "logs" / "health-spawn.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    # Intentionally unclosed: the handle is inherited by the child process.
    out = log.open("ab")
    kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": out,
                              "stderr": subprocess.STDOUT, "cwd": cwd}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    else:  # pragma: no cover - WSL/Linux is the supported host
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    return subprocess.Popen(argv, **kwargs)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class HealthRunner:
    root: Path
    store: Store
    ledger: Ledger
    config: Config
    clock: Callable[[], datetime] = _utcnow
    spawn: Callable[[list[str], str], Any] = _spawn_detached
    disk_usage: Callable[[str], Any] = shutil.disk_usage
    verify: Callable[[Any], list[str]] = verify_ledger
    # Logging facade: deliberately loose so tests can pass any stub.
    log: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        if self.log is None:
            from .logsetup import get_logger
            self.log = get_logger(self.root)

    def now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return now

    # ---------- checks ----------
    def check(self, now: datetime) -> list[Finding]:
        out: list[Finding] = []
        if (self.root / "data" / "KILL").exists():
            out.append(Finding("killed", True, "owner stopped: report only"))
            return out
        out.append(self._check_tick(now))
        out.append(self._check_orphans(now))
        out.append(self._check_disk())
        out.append(self._check_ledger())
        out.append(self._check_backlog())
        out.append(self._check_sandbox())
        return out

    def _check_tick(self, now: datetime) -> Finding:
        stale_after = float(self.config.ops_value("heartbeat_stale_minutes"))
        age = heartbeat_mod.heartbeat_age_minutes(self.store, now)
        if age is None:
            return Finding("tick", False, "no heartbeat recorded", "crit")
        if age <= stale_after:
            return Finding("tick", True, f"last tick {age:.1f} min ago")
        return Finding("tick", False,
                       f"last tick {age:.1f} min ago (limit {stale_after:g})",
                       "crit")

    def _check_orphans(self, now: datetime) -> Finding:
        stale = self._stale_running(now)
        if not stale:
            return Finding("orphans", True, "no orphaned runs")
        return Finding("orphans", False, f"{len(stale)} orphaned run(s)",
                       "warn")

    def _check_disk(self) -> Finding:
        try:
            free_mb = self.disk_usage(str(self.root)).free // (1024 * 1024)
        except OSError as e:
            return Finding("disk", False, f"disk usage unreadable: {e}", "warn")
        minimum = int(self.config.limits.get("min_free_disk_mb", 1024))
        if free_mb < minimum:
            return Finding("disk", False,
                           f"only {free_mb} MB free (min {minimum})", "crit")
        return Finding("disk", True, f"{free_mb} MB free")

    def _check_ledger(self) -> Finding:
        try:
            findings = self.verify(self.ledger.conn)
        except Exception as e:  # noqa: BLE001 - a broken check is itself critical
            return Finding("ledger", False, f"verify crashed: {e}", "crit")
        if findings:
            return Finding("ledger", False,
                           "; ".join(findings[:5]), "crit")
        return Finding("ledger", True, "verify clean")

    def _check_backlog(self) -> Finding:
        counts = self.store.task_counts()
        pending = int(counts.get("pending", 0))
        if pending > BACKLOG_PENDING_N:
            return Finding("backlog", False,
                           f"{pending} pending tasks (limit {BACKLOG_PENDING_N})",
                           "warn")
        return Finding("backlog", True, f"{pending} pending")

    def _check_sandbox(self) -> Finding:
        from .sandbox import Sandbox

        st = Sandbox(config=self.config, root=self.root).status()
        if st == "ok":
            return Finding("sandbox", True, "sandbox usable")
        return Finding("sandbox", True, f"sandbox {st} (host fix needed)")

    # ---------- recovery ----------
    def recover(self, findings: list[Finding], now: datetime) -> list[str]:
        """Execute one scenario per failing check. Returns action descriptions."""
        if (self.root / "data" / "KILL").exists():
            return []
        actions: list[str] = []
        by_name = {f.name: f for f in findings}
        tick = by_name.get("tick")
        if tick is not None and not tick.ok:
            actions.extend(self._recover_daemon(now))
        orphans = by_name.get("orphans")
        if orphans is not None and not orphans.ok:
            actions.extend(self._recover_orphans(now))
        disk = by_name.get("disk")
        if disk is not None and not disk.ok and disk.severity == "crit":
            actions.extend(self._recover_pause(
                now, "disk", f"Health check: {disk.detail}. System paused; "
                             "free disk space, then run `kiraci resume`."))
        ledger = by_name.get("ledger")
        if ledger is not None and not ledger.ok:
            actions.extend(self._recover_pause(
                now, "ledger", f"Health check: ledger verify FAILED "
                               f"({ledger.detail}). System paused."))
        return actions

    def _recover_daemon(self, now: datetime) -> list[str]:
        if self.store.kv_get("health_daemon_started"):
            return []  # already restarted once; wait for its first tick
        try:
            proc = self.spawn(
                [sys.executable, "-m", "kiraci.cli", "run"], str(self.root))
            pid = getattr(proc, "pid", "?")
        except OSError as e:
            self.log.error("health: daemon start failed: %s", e)
            return [f"daemon start failed: {e}"]
        self.store.kv_set("health_daemon_started", now.isoformat())
        self._notice_once(now, "daemon-restart",
                          "Health check restarted the Kiraci daemon "
                          f"(pid {pid}) after a stale/missing heartbeat.")
        return [f"daemon restarted (pid {pid})"]

    def _recover_orphans(self, now: datetime) -> list[str]:
        stale = self._stale_running(now)
        for t in stale:
            self.store.set_status(
                t["id"], "pending",
                attempts=int(t.get("attempts", 0)) + 1,
                result_summary="health check: orphaned run requeued")
        if stale:
            self._notice_once(
                now, "orphans", f"Health check requeued {len(stale)} "
                                "orphaned task(s) to pending.")
        return [f"requeued {len(stale)} orphaned task(s)"] if stale else []

    def _recover_pause(self, now: datetime, key: str, message: str) -> list[str]:
        (self.root / "data").mkdir(parents=True, exist_ok=True)
        (self.root / "data" / "PAUSE").touch()
        self.log.error("health: %s", message)
        self._notice_once(now, f"pause-{key}", message)
        return [f"paused ({key})"]

    def _stale_running(self, now: datetime) -> list[dict[str, Any]]:
        cutoff = now - timedelta(seconds=STALE_RUNNING_S)
        stale = []
        for t in self.store.list_tasks(status="running", limit=200):
            updated = _parse_ts(t.get("updated_at"))
            if updated is not None and updated < cutoff:
                stale.append(t)
        return stale

    def _notice_once(self, now: datetime, key: str, message: str) -> None:
        last = self.store.kv_get(f"health_notice:{key}")
        if last:
            try:
                if now - datetime.fromisoformat(last) < timedelta(
                        seconds=NOTICE_EVERY_S):
                    return
            except ValueError:
                pass
        self.store.kv_set(f"health_notice:{key}", now.isoformat())
        try:
            send_info(message, self.store, root=self.root)
        except (OSError, ValueError) as e:
            self.log.warning("health notice failed: %s", e)

    # ---------- loop ----------
    def cycle(self) -> tuple[list[Finding], list[str]]:
        now = self.now()
        findings = self.check(now)
        actions = self.recover(findings, now)
        bad = [f"{f.name}:{f.detail}" for f in findings if not f.ok]
        acted = f" actions=[{'; '.join(actions)}]" if actions else ""
        line = (f"{now.strftime('%Y-%m-%dT%H:%M:%SZ')} "
                f"health {'OK' if not bad else 'ISSUES [' + '; '.join(bad) + ']'}"
                f"{acted}")
        print(line, flush=True)
        return findings, actions

    def run_forever(self, *, sleep: Callable[[float], None] = time.sleep,
                    cycles: int | None = None) -> int:
        if not claim_pidfile(self.root):
            print("health check already running for this root", flush=True)
            return 2
        stopped: list[bool] = []

        def _stop(signum: Any, frame: Any) -> None:
            stopped.append(True)

        for sig in ("SIGTERM", "SIGINT"):
            try:
                signal.signal(getattr(signal, sig), _stop)
            except (AttributeError, OSError, ValueError):
                pass
        interval = float(self.config.ops_value("health_interval_s"))
        done = 0
        while not stopped:
            try:
                self.cycle()
            except Exception as e:  # noqa: BLE001 - the watchdog must not die
                self.log.error("health cycle crashed: %s", e)
            done += 1
            if cycles is not None and done >= cycles:
                break
            waited = 0.0
            while not stopped and waited < interval:
                step = min(1.0, interval - waited)
                sleep(step)
                waited += step
        return 0


def _parse_ts(raw: object) -> datetime | None:
    """Parse ledger/store timestamps (ISO, incl. the `Z` UTC suffix)."""
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def claim_pidfile(root: Path) -> bool:
    """True when this process owns the health pidfile (or claims a stale one)."""
    path = Path(root) / "data" / "health.pid"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        old = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        old = None
    if old is not None and old != os.getpid():
        try:
            os.kill(old, 0)
        except OSError:
            old = None  # stale pidfile: process is gone
        else:
            return False
    path.write_text(str(os.getpid()), encoding="utf-8")
    return True
