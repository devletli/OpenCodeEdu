"""Bubblewrap sandbox for every agent run.

The command is always built as a list (never shell=True). Mount order matters:
later mounts overlay earlier ones, so the per-run IPC directory (the only
visible path under data/) and the writable worktree are mounted last. The
network stays shared - the model provider must be reachable.

Residual risks (documented in DECISIONS.md and deploy/README.md): the
model-provider credential has to be readable inside the sandbox and outbound
network access is unrestricted, so a prompt-injected agent could try to
exfiltrate that key. Mitigation is outside the software: the human uses a
dedicated provider key with a provider-side spending limit and can rotate it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

DEFAULT_PATH_ENV = "/usr/local/bin:/usr/bin:/bin"

#: Agents that never get a writable worktree or bash access; only these may
#: run unsandboxed when KIRACI_SANDBOX=off and KIRACI_ALLOW_UNSANDBOXED=1.
UNSANDBOXED_ALLOWED_AGENTS = frozenset(
    {"brain", "scout", "seller", "diplomat", "chronicler", "treasurer"})

_PROBE_TTL_S = 60.0


def build_command(
    *, project: Path, ipc_dir: Path, sandbox_home: Path, worktree: Path | None,
    cwd: Path, cmd: list[str], bwrap: str = "bwrap", path_env: str = DEFAULT_PATH_ENV,
) -> list[str]:
    """Build the bwrap argv for one agent run. Pure: touches nothing."""
    project = Path(project)
    c = [
        bwrap,
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--tmpfs", "/home",
        "--tmpfs", str(project / "data"),
        "--ro-bind", "/dev/null", str(project / ".env"),
        "--bind", str(sandbox_home), "/home/sandbox",
        "--bind", str(ipc_dir), str(ipc_dir),
    ]
    if worktree is not None:
        c += ["--bind", str(worktree), str(worktree)]
    c += [
        "--unshare-pid", "--unshare-ipc", "--unshare-uts",
        "--new-session", "--die-with-parent",
        "--clearenv",
        "--setenv", "PATH", path_env,
        "--setenv", "HOME", "/home/sandbox",
        "--setenv", "LANG", "C.UTF-8",
        "--setenv", "KIRACI_IPC_DIR", str(ipc_dir),
        "--chdir", str(cwd),
        "--", *cmd,
    ]
    return c


def _opencode_home_files() -> list[Path]:
    """Private copies opencode needs: auth.json and config files (Step 0)."""
    home = Path.home()
    out: list[Path] = []
    data_dir = home / ".local" / "share" / "opencode"
    auth = data_dir / "auth.json"
    if auth.is_file():
        out.append(auth)
    config_dir = home / ".config" / "opencode"
    if config_dir.is_dir():
        for p in sorted(config_dir.iterdir()):
            if p.is_file() and p.suffix in (".json", ".jsonc"):
                out.append(p)
    return out


class Sandbox:
    """Status probing and per-run directory preparation."""

    def __init__(self, *, config, root: Path):
        self.config = config
        self.root = Path(root)
        self._probe_result: tuple[float, str] | None = None

    # ---------- status ----------
    def status(self, *, force: bool = False) -> str:
        """One of: ok, unavailable (probe failed), disabled (env/config off)."""
        if os.environ.get("KIRACI_SANDBOX") == "off":
            return "disabled"
        if str(self.config.sandbox_value("mode")) == "off":
            return "disabled"
        now = time.monotonic()
        if not force and self._probe_result and now - self._probe_result[0] < _PROBE_TTL_S:
            return self._probe_result[1]
        result = self._probe()
        self._probe_result = (now, result)
        return result

    def _probe(self) -> str:
        bwrap = str(self.config.sandbox_value("bwrap") or "bwrap")
        if shutil.which(bwrap) is None and not Path(bwrap).is_file():
            return "unavailable"
        try:
            probe = subprocess.run(
                [bwrap, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
                 "--unshare-pid", "--die-with-parent", "true"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, timeout=15, check=False)
        except (OSError, subprocess.SubprocessError):
            return "unavailable"
        return "ok" if probe.returncode == 0 else "unavailable"

    def unsandboxed_agent_allowed(self, agent: str) -> bool:
        """With the explicit override, only no-bash/no-write agents may run."""
        return agent in UNSANDBOXED_ALLOWED_AGENTS

    # ---------- per-run preparation ----------
    def ipc_dir(self, run_id: str) -> Path:
        d = self.root / "data" / "ipc" / str(run_id)
        (d / "requests").mkdir(parents=True, exist_ok=True)
        (d / "responses").mkdir(parents=True, exist_ok=True)
        return d

    def sandbox_home(self, run_id: str) -> Path:
        """0700 home with a private copy of opencode's auth/config (0600)."""
        home = self.root / "data" / "sandbox" / f"home-{run_id}"
        home.mkdir(parents=True, mode=0o700, exist_ok=True)
        try:
            os.chmod(home, 0o700)
        except OSError:
            pass
        for src in _opencode_home_files():
            rel = src.relative_to(Path.home())
            dst = home / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copyfile(src, dst)
                os.chmod(dst, 0o600)
            except OSError:
                continue
        return home

    def cleanup(self, run_id: str) -> None:
        """Delete the per-run IPC dir and sandbox home. Never raises."""
        for rel in ("data/ipc", "data/sandbox"):
            base = self.root / rel
            shutil.rmtree(base / str(run_id), ignore_errors=True)
            shutil.rmtree(base / f"home-{run_id}", ignore_errors=True)
            try:
                if base.is_dir() and not any(base.iterdir()):
                    base.rmdir()
            except OSError:
                pass