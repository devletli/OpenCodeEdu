"""Hermetic tests for tools/sandbox.py (Docker isolation, TASK2 Phase 2).

No test here needs a real Docker daemon: success/timeout paths stub
subprocess.run, and the unavailable-docker path uses a bogus binary name.
"""

import importlib.util
import subprocess
from pathlib import Path


def load_sandbox():
    path = Path(__file__).resolve().parent.parent / "tools" / "sandbox.py"
    spec = importlib.util.spec_from_file_location("kiraci_tools_sandbox", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sandbox = load_sandbox()


def test_empty_script_rejected():
    assert load_sandbox().run_in_sandbox("")["exit_code"] == 2
    assert load_sandbox().run_in_sandbox("   \n")["exit_code"] == 2


def test_bad_timeout_rejected():
    assert sandbox.run_in_sandbox("print(1)", timeout=0)["exit_code"] == 2


def test_missing_docker_binary_reports_unavailable():
    res = sandbox.run_in_sandbox("print(1)", docker="definitely-not-docker-xyz")
    assert res["exit_code"] == 2
    assert "docker" in res["stderr"].lower()
    assert sandbox.is_available("definitely-not-docker-xyz") is False


def test_success_shape_and_isolation_flags(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda _: "/usr/bin/docker")
    seen = {}

    class Done:
        returncode = 0
        stdout = "42\n"
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        assert kwargs.get("capture_output") is True
        assert kwargs.get("stdin") == subprocess.DEVNULL
        assert kwargs.get("check") is False
        return Done()

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    res = sandbox.run_in_sandbox("print(40 + 2)")
    assert res == {"exit_code": 0, "stdout": "42\n", "stderr": ""}
    cmd = seen["cmd"]
    assert isinstance(cmd, list)  # never shell=True
    assert cmd[0] == "docker"
    assert "--network" in cmd and "none" in cmd
    assert "--user" in cmd and "1000:1000" in cmd
    assert "--memory" in cmd and "--cpus" in cmd
    assert any(a.endswith(":/app/submission.py:ro") for a in cmd)
    assert not any(".env" in a for a in cmd)
    assert cmd[-2:] == ["python", "/app/submission.py"]


def test_timeout_maps_to_minus_one(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda _: "/usr/bin/docker")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, timeout=15)

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    res = sandbox.run_in_sandbox("print(1)")
    assert res["exit_code"] == -1
    assert "timed out" in res["stderr"].lower()


def test_oserror_maps_to_error(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda _: "/usr/bin/docker")

    def fake_run(cmd, **kwargs):
        raise OSError("noexec")

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    res = sandbox.run_in_sandbox("print(1)", docker="docker")
    assert res["exit_code"] == 2
    assert "noexec" in res["stderr"]
