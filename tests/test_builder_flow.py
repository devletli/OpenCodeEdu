import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kiraci.builder_flow import run_builder_task
from kiraci.config import Config
from kiraci.db import connect
from kiraci.store import Store
from kiraci.testing import FakeRunner


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=str(repo), stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, check=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init")
    _git(r, "config", "user.email", "test@kiraci.local")
    _git(r, "config", "user.name", "test")
    (r / "README.md").write_text("hi\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-m", "init")
    return r


@pytest.fixture
def wired():
    conn = connect(":memory:")
    store = Store(conn)
    config = Config(
        models={"builder": "mid", "judge": "mid"},
        costs={"builder": 3, "judge": 3},
        limits={"run_timeout_seconds": 60, "max_task_attempts": 3},
    )
    return store, config


def _task(store, title="Gadget"):
    r = store.create_task(agent="builder", title=title, prompt="write it",
                          created_by="o")
    assert r["status"] == "created", r
    return r["task_id"]


def _worktrees(repo):
    out = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=str(repo),
                         stdout=subprocess.PIPE, text=True, check=False)
    return [ln for ln in out.stdout.splitlines() if ln.startswith("worktree ")]


def test_merge_allowed_change(repo, wired):
    store, config = wired

    def writer(agent, prompt, cwd):
        if agent == "builder":
            d = Path(cwd) / "tools"
            d.mkdir(parents=True, exist_ok=True)
            (d / "gadget.py").write_text("x = 1\n", encoding="utf-8")
            (d / "test_gadget.py").write_text("def test_x():\n    assert 1 == 1\n",
                                              encoding="utf-8")

    runner = FakeRunner(outputs={"judge": ["ACCEPT\nlooks good"]}, on_run=writer)
    tid = _task(store)
    outcome = run_builder_task(task_id=tid, store=store, runner=runner,
                               config=config, repo_root=repo,
                               now=datetime(2026, 1, 5, 13, 0, tzinfo=UTC))
    assert outcome == "done"
    assert (repo / "tools" / "gadget.py").exists()
    task = store.get_task(tid)
    assert task["status"] == "done" and task["review"] == "accepted"
    assert len(_worktrees(repo)) == 1  # worktree cleaned up


def test_touching_src_rejected_never_merged(repo, wired):
    store, config = wired

    def writer(agent, prompt, cwd):
        if agent == "builder":
            d = Path(cwd) / "src"
            d.mkdir(parents=True, exist_ok=True)
            (d / "evil.py").write_text("print('hi')\n", encoding="utf-8")

    runner = FakeRunner(outputs={"judge": ["ACCEPT\nfine"]}, on_run=writer)
    tid = _task(store)
    outcome = run_builder_task(task_id=tid, store=store, runner=runner,
                               config=config, repo_root=repo,
                               now=datetime(2026, 1, 5, 13, 0, tzinfo=UTC))
    assert outcome == "rejected"
    assert not (repo / "src" / "evil.py").exists()
    task = store.get_task(tid)
    assert task["status"] == "rejected" and task["review"] == "rejected"
    assert "src/evil.py" in task["result_summary"]
    branches = subprocess.run(["git", "branch", "--list", f"task/{tid}"],
                              cwd=str(repo), stdout=subprocess.PIPE,
                              text=True, check=False).stdout
    assert f"task/{tid}" in branches  # kept for inspection
    assert len(_worktrees(repo)) == 1


def test_judge_reject_leaves_main_untouched(repo, wired):
    store, config = wired

    def writer(agent, prompt, cwd):
        if agent == "builder":
            d = Path(cwd) / "tools"
            d.mkdir(parents=True, exist_ok=True)
            (d / "gadget.py").write_text("x = 1\n", encoding="utf-8")

    runner = FakeRunner(outputs={"judge": ["REJECT\nno tests included"]},
                        on_run=writer)
    tid = _task(store)
    outcome = run_builder_task(task_id=tid, store=store, runner=runner,
                               config=config, repo_root=repo,
                               now=datetime(2026, 1, 5, 13, 0, tzinfo=UTC))
    assert outcome == "rejected"
    assert not (repo / "tools" / "gadget.py").exists()
    assert store.get_task(tid)["status"] == "rejected"
    assert len(_worktrees(repo)) == 1
