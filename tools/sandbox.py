"""Isolated code execution via ephemeral Docker container (TASK2.md Phase 2).

Runs untrusted agent/user code inside a non-root, no-network, read-only
container. Only the single submission file is mounted (read-only); host
paths such as .env, project root, or .opencode are never mounted.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

IMAGE = "python:3.11-slim"
TIMEOUT_S = 15


def is_available(docker: str = "docker") -> bool:
    """True when a docker binary is on PATH."""
    return shutil.which(docker) is not None


def run_in_sandbox(
    script_content: str,
    timeout: int = TIMEOUT_S,
    docker: str = "docker",
    image: str = IMAGE,
) -> dict:
    """Execute arbitrary code inside an isolated, non-root, read-only container."""
    if not script_content or not script_content.strip():
        return {"exit_code": 2, "stdout": "", "stderr": "empty script"}
    if timeout <= 0:
        return {"exit_code": 2, "stdout": "", "stderr": "timeout must be positive"}
    if shutil.which(docker) is None:
        return {"exit_code": 2, "stdout": "", "stderr": "docker not available"}

    with tempfile.TemporaryDirectory() as temp_dir:
        script_file = Path(temp_dir) / "submission.py"
        script_file.write_text(script_content, encoding="utf-8")

        docker_cmd = [
            docker, "run", "--rm",
            "--network", "none",
            "--memory", "256m",
            "--cpus", "0.5",
            "--user", "1000:1000",
            "-v", f"{script_file}:/app/submission.py:ro",
            image,
            "python", "/app/submission.py",
        ]

        try:
            res = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                check=False,
            )
            return {
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": "Execution timed out."}
        except OSError as e:
            return {"exit_code": 2, "stdout": "", "stderr": f"sandbox failed: {e}"}
