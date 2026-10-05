"""The only opencode-specific module.

Step 0 (opencode 1.18.31) showed `opencode run` supports exactly the flags this
module assumes: `--agent <name>`, `-m/--model provider/model`, positional message.
If a future opencode version changes these flags, adapt ONLY this module and note
it in DECISIONS.md.

v0.4 run flow: allocate the runs row first (run_id), prepare the per-run IPC
directory, start a BrokerSession, execute the command - sandboxed via bubblewrap
when the sandbox reports ok, otherwise directly with a stripped environment (the
orchestrator gates who may run unsandboxed) - and always clean up in a finally
block. KIRACI_DB is never passed to agents: they talk to the broker over IPC.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from . import sandbox as sandbox_mod
from .config import TIER_ENV, Config
from .ledger import Ledger
from .store import Store

if TYPE_CHECKING:
    from .broker import BrokerSession

#: Truncation limit for stored run output.
MAX_OUTPUT_CHARS = 200_000

#: Output signatures meaning "this model is unusable right now, try the next
#: one in the tier": rate limits, exhausted free quota, overloaded provider,
#: or a removed/unknown model. Auth failures (bad key) and timeouts are NOT
#: quota: rotating models cannot fix those, so they return as-is.
_QUOTA_PATTERNS = (
    r"429",
    r"rate.?limit",
    r"free-models-per-(day|min)",
    r"\bquota\b",
    r"insufficient.{0,20}credit",
    r"\b503\b|\b529\b|overloaded|capacity",
    r"model (not found|does not exist)|no endpoints|404",
)
_QUOTA_RE = re.compile("|".join(f"(?:{p})" for p in _QUOTA_PATTERNS),
                       re.IGNORECASE)
_AUTH_RE = re.compile(r"401|unauthorized|invalid.{0,20}(api.?key|key)",
                      re.IGNORECASE)


def quota_exhausted(text: str) -> bool:
    """True when a FAILED run's output says the model is unusable right now.

    Only called for failed runs: a successful run never rotates, even if its
    text mentions e.g. an HTTP 404 from a web fetch.
    """
    t = text or ""
    if _AUTH_RE.search(t):
        return False
    if "[TIMEOUT after" in t:
        return False
    return bool(_QUOTA_RE.search(t))

#: Child environment allowlist. On Windows SYSTEMROOT/USERPROFILE/TEMP/TMP are
#: also required, otherwise child processes cannot even start. KIRACI_DB is
#: deliberately absent: agents never see the database.
_ENV_ALLOW: tuple[str, ...] = ("PATH", "HOME", "LANG", "KIRACI_IPC_DIR")
if os.name == "nt":
    _ENV_ALLOW = _ENV_ALLOW + ("SYSTEMROOT", "USERPROFILE", "TEMP", "TMP")


@dataclass
class RunResult:
    ok: bool
    text: str
    exit_code: int | None
    duration_s: float
    skipped_reason: str | None = None


class Runner(Protocol):
    def run(self, agent: str, prompt: str, cwd: Path, timeout_s: int,
            task_id: int | None = ...) -> RunResult: ...


def default_command(agent: str, model: str, prompt: str) -> list[str]:
    return [resolve_opencode_binary(), "run", "--agent", agent, "--model",
            model, prompt]


def resolve_opencode_binary() -> str:
    """Locate a directly-executable opencode binary.

    On Windows `opencode` on PATH is usually an npm/nvm shim (.cmd/.ps1 or an
    extensionless shell stub) that CreateProcess cannot execute directly
    (FileNotFoundError). In that case look for the real binary next to the
    shim (npm layout: node_modules/opencode-ai/bin/opencode.exe).
    Resolved once at runner construction, while the parent env (full PATH)
    is still intact.

    On POSIX, a native Linux build is preferred over any Windows-interop
    path (e.g. /mnt/c/...): the interop boundary drops unknown environment
    variables for child processes, which silently breaks KIRACI_IPC_DIR
    delivery to MCP servers (verified live: children saw a Windows env
    without our variables).
    """
    if os.name == "posix":
        for cand in (Path.home() / ".opencode" / "bin" / "opencode",
                     Path("/usr/local/bin/opencode")):
            try:
                if cand.is_file() and os.access(cand, os.X_OK):
                    return str(cand)
            except OSError:
                continue
    found = shutil.which("opencode")
    if found and found.lower().endswith(".exe"):
        return found
    if found:
        sibling = (Path(found).parent / "node_modules" / "opencode-ai"
                   / "bin" / "opencode.exe")
        if sibling.is_file():
            return str(sibling)
        same_dir = Path(found).parent / "opencode.exe"
        if same_dir.is_file():
            return str(same_dir)
    if found:
        return found
    print("kiraci: opencode not found on PATH", file=sys.stderr)
    return "opencode"


class OpencodeRunner:
    """Runs agents via the opencode CLI with a ledger spend gate for paid runs.

    `skipped_reason` convention: a reason starting with "budget:" means the
    ledger refused the spend (the orchestrator defers the task to tomorrow);
    any other reason is environmental (e.g. no model configured).
    """

    def __init__(
        self,
        *,
        ledger: Ledger,
        store: Store,
        config: Config,
        cmd_builder: Callable[[str, str, str], list[str]] | None = None,
        sandbox: Any = None,
        root: Path | None = None,
    ) -> None:
        self.ledger = ledger
        self.store = store
        self.config = config
        self.cmd_builder = cmd_builder or default_command
        self.sandbox = sandbox
        self.root = Path(root).resolve() if root else Path.cwd().resolve()
        kiracidb = os.environ.get("KIRACI_DB", "data/kiraci.db")
        self.kiracidb = os.path.abspath(kiracidb)
        #: Set by the orchestrator every tick. When True, every agent runs
        #: on the cheap-tier model chain (survival mode). The ledger spend
        #: gate still applies on top.
        self.survival_mode = False

    def _child_env(self, ipc_dir: Path | None) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOW}
        if ipc_dir is not None:
            env["KIRACI_IPC_DIR"] = str(ipc_dir)
        return env

    def _worktree_for(self, agent: str, cwd: Path) -> Path | None:
        """Only builder and judge-on-builder-output get a writable worktree."""
        try:
            if cwd.resolve() == self.root:
                return None
        except OSError:
            return None
        if agent in ("builder", "judge"):
            return cwd
        return None

    def run(self, agent: str, prompt: str, cwd: Path, timeout_s: int,
            task_id: int | None = None) -> RunResult:
        """Run an agent, rotating through the tier's model chain on quota errors.

        Each tier env var may hold a comma-separated chain (primary first).
        When a run fails with a quota/rate-limit/removed-model signature, the
        next model is tried immediately in the same call; the winning model
        sticks (kv) until the daily reset retries the primary.
        """
        tier = "cheap" if self.survival_mode else self.config.tier_for(agent)
        models = self.config.tier_models(tier)
        if not models:
            self.store.log_run(agent=agent, model="", est_cost_cents=0,
                               duration_s=0.0, exit_code=None, status="skipped")
            return RunResult(ok=False, text="", exit_code=None, duration_s=0.0,
                             skipped_reason="no model configured for this agent's tier")
        self._maybe_reset_fallbacks()
        start = self._fallback_index(tier, len(models))
        ordered = [models[(start + i) % len(models)] for i in range(len(models))]
        res: RunResult | None = None
        for pos, model in enumerate(ordered):
            res = self._execute(agent, model, prompt, cwd, timeout_s, task_id)
            if res.ok or res.skipped_reason is not None or not quota_exhausted(res.text):
                if pos > 0:
                    self._set_fallback_index(tier, models.index(model))
                return res
            print(f"kiraci: {model} quota-exhausted, trying next model in"
                  f" tier {tier}", file=sys.stderr)
        assert res is not None  # ordered is non-empty (models checked above)
        return res

    def _fallback_index(self, tier: str | None, n: int) -> int:
        try:
            i = int(self.store.kv_get(f"model_fallback_idx:{tier}") or 0)
        except (TypeError, ValueError):
            i = 0
        return i % n if n else 0

    def _set_fallback_index(self, tier: str | None, i: int) -> None:
        self.store.kv_set(f"model_fallback_idx:{tier}", str(i))

    def _maybe_reset_fallbacks(self) -> None:
        """New UTC day: retry primaries first again (free quotas reset daily)."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self.store.kv_get("model_fallback_day") != today:
            for tier in TIER_ENV:
                self.store.kv_set(f"model_fallback_idx:{tier}", "0")
            self.store.kv_set("model_fallback_day", today)

    def _execute(self, agent: str, model: str, prompt: str, cwd: Path,
                 timeout_s: int, task_id: int | None) -> RunResult:
        from . import usage
        cost = usage.paid_estimate_cents(self.store, self.config, agent)
        if cost > 0:
            decision = self.ledger.request_spend(agent, "tokens", cost, f"run {agent}")
            if decision.get("status") != "approved":
                self.store.log_run(agent=agent, model=model, est_cost_cents=cost,
                                   duration_s=0.0, exit_code=None, status="skipped")
                return RunResult(
                    ok=False, text="", exit_code=None, duration_s=0.0,
                    skipped_reason=f"budget: {decision.get('reason', 'spend refused')}",
                )
        run_id = self.store.start_run(agent=agent, task_id=task_id, model=model,
                                      est_cost_cents=cost)
        cmd = self.cmd_builder(agent, model, prompt)
        ipc_dir: Path | None = None
        session = None
        if self.sandbox is not None:
            ipc_dir = self.sandbox.ipc_dir(str(run_id))
            home = self.sandbox.sandbox_home(str(run_id))
            session = self._start_broker(str(run_id), agent, ipc_dir)
            wt = self._worktree_for(agent, Path(cwd))
            in_cwd = wt if wt is not None else self.root
            if self.sandbox.status() == "ok":
                # The sandbox PATH must contain the directory of the resolved
                # opencode binary; the venv python used to spawn the MCP
                # servers lives right next to it (systemd sets the same idea
                # via PATH=/opt/kiraci/.venv/bin:...).
                oc_dir = str(Path(cmd[0]).resolve().parent)
                cmd = sandbox_mod.build_command(
                    project=self.root, ipc_dir=ipc_dir, sandbox_home=home,
                    worktree=wt, cwd=in_cwd, cmd=cmd,
                    bwrap=str(self.config.sandbox_value("bwrap")),
                    path_env=f"{oc_dir}:{sandbox_mod.DEFAULT_PATH_ENV}")
        start = time.monotonic()
        try:
            try:
                if os.name == "posix":
                    proc = subprocess.Popen(
                        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, cwd=str(cwd),
                        env=self._child_env(ipc_dir),
                        text=True, start_new_session=True,
                    )
                else:
                    proc = subprocess.Popen(
                        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, cwd=str(cwd),
                        env=self._child_env(ipc_dir),
                        text=True,
                        creationflags=getattr(
                            subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                    )
            except OSError as e:
                # A missing/broken binary must fail the run, never kill the
                # daemon: the task goes through the normal attempts path.
                self.store.finish_run(run_id, duration_s=time.monotonic() - start,
                                      exit_code=None, status="error")
                return RunResult(ok=False, text=f"failed to start {cmd[0]!r}: {e}",
                                 exit_code=None,
                                 duration_s=time.monotonic() - start)
            try:
                out, _ = proc.communicate(timeout=timeout_s)
                status = "ok" if proc.returncode == 0 else "failed"
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
                else:
                    proc.kill()
                out, _ = proc.communicate()
                out = (out or "") + f"\n[TIMEOUT after {timeout_s}s]"
                status = "timeout"
        finally:
            if session is not None:
                session.cleanup()
            if self.sandbox is not None:
                self.sandbox.cleanup(str(run_id))
        duration = time.monotonic() - start
        text = (out or "")[:MAX_OUTPUT_CHARS]
        self.store.finish_run(run_id, duration_s=duration,
                              exit_code=proc.returncode, status=status)
        return RunResult(ok=status == "ok", text=text, exit_code=proc.returncode,
                         duration_s=duration)

    def _start_broker(self, run_id: str, agent: str, ipc_dir: Path) -> BrokerSession:
        """The broker creates its OWN database connection (never shared)."""
        from .broker import BrokerSession

        session = BrokerSession(run_id, agent, ipc_dir, root=self.root)
        session.start()
        return session