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
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

#: Truncation limit for stored run output.
MAX_OUTPUT_CHARS = 200_000

#: Child environment allowlist. On Windows SYSTEMROOT/USERPROFILE/TEMP/TMP are
#: also required, otherwise child processes cannot even start. KIRACI_DB is
#: deliberately absent: agents never see the database.
_ENV_ALLOW = ("PATH", "HOME", "LANG", "KIRACI_IPC_DIR")
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
    """
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
        ledger,
        store,
        config,
        cmd_builder: Callable[[str, str, str], list[str]] | None = None,
        sandbox=None,
        root: Path | None = None,
    ):
        self.ledger = ledger
        self.store = store
        self.config = config
        self.cmd_builder = cmd_builder or default_command
        self.sandbox = sandbox
        self.root = Path(root).resolve() if root else Path.cwd().resolve()
        kiracidb = os.environ.get("KIRACI_DB", "data/kiraci.db")
        self.kiracidb = os.path.abspath(kiracidb)

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
        model = self.config.model_for(agent)
        if model is None:
            self.store.log_run(agent=agent, model="", est_cost_cents=0,
                               duration_s=0.0, exit_code=None, status="skipped")
            return RunResult(ok=False, text="", exit_code=None, duration_s=0.0,
                             skipped_reason="no model configured for this agent's tier")
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
                cmd = self.sandbox.build_command(
                    project=self.root, ipc_dir=ipc_dir, sandbox_home=home,
                    worktree=wt, cwd=in_cwd, cmd=cmd,
                    bwrap=str(self.config.sandbox_value("bwrap")))
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
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
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

    def _start_broker(self, run_id: str, agent: str, ipc_dir: Path):
        """The broker creates its OWN database connection (never shared)."""
        from .broker import BrokerSession

        session = BrokerSession(run_id, agent, ipc_dir, root=self.root)
        session.start()
        return session