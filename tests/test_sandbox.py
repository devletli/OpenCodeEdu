import json
import os
import shutil
import subprocess
import sys

import pytest

from kiraci.config import Config
from kiraci.sandbox import UNSANDBOXED_ALLOWED_AGENTS, Sandbox, build_command

BWRAP_AVAILABLE = shutil.which("bwrap") is not None and sys.platform != "win32"


def make_cmd():
    return ["opencode", "run", "--agent", "scout", "hello"]


def test_build_command_full_flag_set_and_mount_order(tmp_path):
    project = tmp_path / "proj"
    ipc = project / "data" / "ipc" / "run-1"
    home = project / "data" / "sandbox" / "home-run-1"
    cmd = build_command(project=project, ipc_dir=ipc, sandbox_home=home,
                        worktree=None, cwd=project, cmd=make_cmd())
    assert cmd[0] == "bwrap"
    assert cmd.count("--ro-bind") == 2  # / and /dev/null over .env
    assert cmd[1:4] == ["--ro-bind", "/", "/"]
    assert cmd[4:6] == ["--dev", "/dev"]
    assert cmd[6:8] == ["--proc", "/proc"]
    assert cmd[8:10] == ["--tmpfs", "/tmp"]
    assert cmd[10:12] == ["--tmpfs", "/home"]
    assert cmd[12:14] == ["--tmpfs", str(project / "data")]
    assert cmd[14:17] == ["--ro-bind", "/dev/null", str(project / ".env")]
    assert cmd[17:20] == ["--bind", str(home), "/home/sandbox"]
    assert cmd[20:23] == ["--bind", str(ipc), str(ipc)]
    assert "--unshare-pid" in cmd and "--unshare-ipc" in cmd
    assert "--unshare-uts" in cmd
    assert "--new-session" in cmd and "--die-with-parent" in cmd
    assert "--clearenv" in cmd
    # cleared environment: exactly PATH, HOME, LANG, KIRACI_IPC_DIR
    setenv = []
    for i, part in enumerate(cmd):
        if part == "--setenv":
            setenv.append(cmd[i + 1])
    assert setenv == ["PATH", "HOME", "LANG", "KIRACI_IPC_DIR"]
    assert "KIRACI_DB" not in setenv
    assert "--chdir" in cmd
    assert cmd[-len(make_cmd()):] == make_cmd()
    assert "--" in cmd


def test_no_unshare_net_network_stays_shared(tmp_path):
    cmd = build_command(project=tmp_path, ipc_dir=tmp_path / "ipc",
                        sandbox_home=tmp_path / "home", worktree=None,
                        cwd=tmp_path, cmd=make_cmd())
    assert "--unshare-net" not in cmd


def test_worktree_mounted_only_when_given(tmp_path):
    wt = tmp_path / "workspace" / "task-1"
    cmd = build_command(project=tmp_path, ipc_dir=tmp_path / "ipc",
                        sandbox_home=tmp_path / "home", worktree=wt,
                        cwd=wt, cmd=make_cmd())
    unshare = cmd.index("--unshare-pid")
    assert cmd[unshare - 3:unshare - 1] == ["--bind", str(wt)]


def test_env_mask_covers_secrets_file(tmp_path):
    cmd = build_command(project=tmp_path, ipc_dir=tmp_path / "ipc",
                        sandbox_home=tmp_path / "home", worktree=None,
                        cwd=tmp_path, cmd=make_cmd())
    triples = [cmd[i:i + 3] for i in range(len(cmd) - 2)]
    assert ["--ro-bind", "/dev/null", str(tmp_path / ".env")] in triples


def test_ipc_dir_is_the_only_visible_data_path(tmp_path):
    ipc = tmp_path / "data" / "ipc" / "run-1"
    cmd = build_command(project=tmp_path, ipc_dir=ipc, sandbox_home=tmp_path / "h",
                        worktree=None, cwd=tmp_path, cmd=make_cmd())
    binds = []
    for i, part in enumerate(cmd):
        if part == "--bind":
            binds.append(cmd[i + 1])
    assert str(ipc) in binds
    for b in binds:
        if b.startswith(str(tmp_path / "data")):
            assert b == str(ipc)


def test_status_disabled_by_env_or_config(monkeypatch, tmp_path):
    sbx = Sandbox(config=Config(), root=tmp_path)
    monkeypatch.setenv("KIRACI_SANDBOX", "off")
    assert sbx.status() == "disabled"
    monkeypatch.delenv("KIRACI_SANDBOX")
    cfg_off = Config(sandbox={"mode": "off"})
    assert Sandbox(config=cfg_off, root=tmp_path).status() == "disabled"


def test_status_unavailable_without_bwrap(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    sbx = Sandbox(config=Config(), root=tmp_path)
    assert sbx.status() == "unavailable"


def test_unsandboxed_agents_never_builder_or_judge():
    assert "builder" not in UNSANDBOXED_ALLOWED_AGENTS
    assert "judge" not in UNSANDBOXED_ALLOWED_AGENTS
    assert "scout" in UNSANDBOXED_ALLOWED_AGENTS
    assert "treasurer" in UNSANDBOXED_ALLOWED_AGENTS


def test_sandbox_home_and_ipc_and_cleanup(tmp_path, monkeypatch):
    fake_auth = tmp_path / "realhome" / "auth.json"
    fake_auth.parent.mkdir(parents=True)
    fake_auth.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("kiraci.sandbox._opencode_home_files",
                        lambda: [fake_auth])
    sbx = Sandbox(config=Config(), root=tmp_path)
    ipc = sbx.ipc_dir("42")
    assert (ipc / "requests").is_dir() and (ipc / "responses").is_dir()
    home = sbx.sandbox_home("42")
    copied = list(home.rglob("auth.json"))
    assert len(copied) == 1
    if os.name != "nt":
        assert (home.stat().st_mode & 0o777) == 0o700
        assert (copied[0].stat().st_mode & 0o777) == 0o600
    sbx.cleanup("42")
    assert not (tmp_path / "data" / "ipc" / "42").exists()
    assert not (tmp_path / "data" / "sandbox" / "home-42").exists()


# ---------- integration (skipped when bwrap is unusable) ----------

@pytest.mark.skipif(not BWRAP_AVAILABLE,
                    reason="bubblewrap unavailable on this host")
def test_sandboxed_run_sees_cleared_env_and_no_db_or_secrets(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".env").write_text("SECRET=topsecret-value", encoding="utf-8")
    (project / "data").mkdir()
    (project / "data" / "kiraci.db").write_text("pretend-db", encoding="utf-8")
    sbx = Sandbox(config=Config(), root=project)
    ipc = sbx.ipc_dir("it")
    home = sbx.sandbox_home("it")
    probe = [sys.executable, "-c",
             ("import os, json; print(json.dumps({"
             "'HOME': os.environ.get('HOME'),"
             "'KIRACI_IPC_DIR': os.environ.get('KIRACI_IPC_DIR'),"
             "'KIRACI_DB': os.environ.get('KIRACI_DB'),"
             "'SECRET': os.environ.get('SECRET'),"
             "'env_keys': sorted(os.environ),"
             "'env_file': open('.env').read(),"
             "'db_visible': os.path.exists('data/kiraci.db')})")]
    cmd = build_command(project=project, ipc_dir=ipc, sandbox_home=home,
                        worktree=None, cwd=project, cmd=probe)
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                         check=False)
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout.strip().splitlines()[-1])
    assert data["HOME"] == "/home/sandbox"
    assert data["KIRACI_IPC_DIR"] == str(ipc)
    assert data["KIRACI_DB"] is None
    assert data["SECRET"] is None
    assert "SECRET" not in data["env_keys"]
    assert data["env_file"] == ""  # .env is masked with /dev/null
    assert data["db_visible"] is False  # data/ is a tmpfs
    sbx.cleanup("it")