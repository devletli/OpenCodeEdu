"""The only opencode-specific module.

Step 0 (opencode 1.18.31) showed `opencode run` supports exactly the flags this
module assumes: `--agent <name>`, `-m/--model provider/model`, positional message.
If a future opencode version changes these flags, adapt ONLY this module and note
it in DECISIONS.md.
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
#: also required, otherwise child processes cannot even start.
_ENV_ALLOW = ("PATH", "HOME", "LANG", "KIRACI_DB")
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
    def run(self, agent: str, prompt: str, cwd: Path, timeout_s: int) -> RunResult: ...


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
    ):
        self.ledger = ledger
        self.store = store
        self.config = config
        self.cmd_builder = cmd_builder or default_command
        kiracidb = os.environ.get("KIRACI_DB", "data/kiraci.db")
        self.kiracidb = os.path.abspath(kiracidb)

    def _child_env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOW}
        env["KIRACI_DB"] = self.kiracidb
        return env

    def run(self, agent: str, prompt: str, cwd: Path, timeout_s: int) -> RunResult:
        model = self.config.model_for(agent)
        if model is None:
            self.store.log_run(agent=agent, model="", est_cost_cents=0,
                               duration_s=0.0, exit_code=None, status="skipped")
            return RunResult(ok=False, text="", exit_code=None, duration_s=0.0,
                             skipped_reason="no model configured for this agent's tier")
        cost = self.config.cost_for(agent)
        if cost > 0:
            decision = self.ledger.request_spend(agent, "tokens", cost, f"run {agent}")
            if decision.get("status") != "approved":
                self.store.log_run(agent=agent, model=model, est_cost_cents=cost,
                                   duration_s=0.0, exit_code=None, status="skipped")
                return RunResult(
                    ok=False, text="", exit_code=None, duration_s=0.0,
                    skipped_reason=f"budget: {decision.get('reason', 'spend refused')}",
                )
        cmd = self.cmd_builder(agent, model, prompt)
        start = time.monotonic()
        try:
            if os.name == "posix":
                proc = subprocess.Popen(
                    cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, cwd=str(cwd), env=self._child_env(),
                    text=True, start_new_session=True,
                )
            else:
                proc = subprocess.Popen(
                    cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, cwd=str(cwd), env=self._child_env(),
                    text=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )
        except OSError as e:
            # A missing/broken binary must fail the run, never kill the daemon:
            # the task goes through the normal attempts/consec-failure path.
            self.store.log_run(agent=agent, model=model, est_cost_cents=cost,
                               duration_s=0.0, exit_code=None, status="error")
            return RunResult(ok=False, text=f"failed to start {cmd[0]!r}: {e}",
                             exit_code=None, duration_s=time.monotonic() - start)
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
        duration = time.monotonic() - start
        text = (out or "")[:MAX_OUTPUT_CHARS]
        self.store.log_run(agent=agent, model=model, est_cost_cents=cost,
                           duration_s=duration, exit_code=proc.returncode,
                           status=status)
        return RunResult(ok=status == "ok", text=text, exit_code=proc.returncode,
                         duration_s=duration)
