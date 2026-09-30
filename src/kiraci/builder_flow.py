from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from . import guard
from .store import tomorrow_0005

BUILDER_RULES = (
    "Rules for this task: write changes ONLY under these prefixes: "
    + ", ".join(guard.ALLOWED_PREFIXES)
    + ". Touching anything else (src/, tests/, .opencode/, deploy/, KIRACI.md, "
    "opencode.json, config.toml, data/) fails review automatically. "
    "Include tests next to any code you add under tools/ or products/."
)

#: Serializes merges into the main checkout.
_merge_lock = threading.Lock()


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False,
    )


def _remove_worktree(repo_root: Path, wt: Path, branch: str) -> None:
    _git(["worktree", "remove", "--force", str(wt)], repo_root)
    _git(["worktree", "prune"], repo_root)


def run_builder_task(
    *, task_id: int, store, runner, config, repo_root: Path, now: datetime,
) -> str:
    """Run the builder flow for a task.

    Returns one of "done", "rejected", "failed", "skipped" and writes the task
    status to the store. Merged code under tools/ is never executed by the
    orchestrator (there is simply no code path that does so).
    """
    repo_root = Path(repo_root)
    task = store.get_task(task_id)
    if task is None:
        return "failed"
    timeout = int(config.limits.get("run_timeout_seconds", 1200))
    max_attempts = int(config.limits.get("max_task_attempts", 3))
    branch = f"task/{task_id}"
    wt = repo_root / "workspace" / f"task-{task_id}"

    def defer(summary: str) -> str:
        _remove_worktree(repo_root, wt, branch)
        store.set_status(task_id, "pending", not_before=tomorrow_0005(now),
                         result_summary=summary)
        return "skipped"

    def fail(summary: str) -> str:
        _remove_worktree(repo_root, wt, branch)
        attempts = int(task.get("attempts", 0)) + 1
        if attempts >= max_attempts:
            store.set_status(task_id, "failed", attempts=attempts,
                             result_summary=summary)
        else:
            store.set_status(task_id, "pending", attempts=attempts,
                             result_summary=summary)
        return "failed"

    base = _git(["rev-parse", "HEAD"], repo_root)
    if base.returncode != 0:
        return fail("no git HEAD in main checkout")
    base = base.stdout.strip()
    _git(["worktree", "remove", "--force", str(wt)], repo_root)
    _git(["branch", "-D", branch], repo_root)
    add = _git(["worktree", "add", "-b", branch, str(wt), "HEAD"], repo_root)
    if add.returncode != 0:
        return fail(f"worktree add failed: {add.stdout.strip()[:500]}")

    res = runner.run("builder", task["prompt"] + "\n\n" + BUILDER_RULES, wt, timeout)
    if res.skipped_reason is not None:
        return defer(f"builder run skipped: {res.skipped_reason}")
    if not res.ok:
        return fail(f"builder run failed (exit {res.exit_code}): {res.text[:500]}")

    _git(["add", "-A"], wt)
    status = _git(["status", "--porcelain"], wt)
    if not status.stdout.strip():
        _remove_worktree(repo_root, wt, branch)
        store.set_status(task_id, "done", review="none",
                         result_summary="builder made no changes")
        return "done"
    commit = _git(
        ["-c", "user.name=kiraci-builder", "-c", "user.email=builder@kiraci.local",
         "-c", f"core.hooksPath={os.devnull}",
         "commit", "-m", f"task {task_id}: {task['title'][:72]}"],
        wt,
    )
    if commit.returncode != 0:
        return fail(f"builder commit failed: {commit.stdout.strip()[:500]}")

    diff = _git(["diff", "--raw", "--no-renames", base, branch], repo_root)
    viols = guard.violations(guard.parse_raw_diff(diff.stdout))
    if viols:
        _remove_worktree(repo_root, wt, branch)  # branch kept for inspection
        summary = "guard violations: " + "; ".join(viols)[:2000]
        store.set_status(task_id, "rejected", review="rejected",
                         branch=branch, result_summary=summary)
        return "rejected"

    stat = _git(["diff", "--stat", base, branch], repo_root).stdout.strip()[:4000]
    judge_prompt = (
        f"Review builder task #{task_id} ({task['title']}).\n"
        f"Diff stat vs {base[:12]}:\n{stat}\n\n"
        "Decide ACCEPT or REJECT per your policy. "
        "Your answer's first non-empty line must be exactly ACCEPT or REJECT."
    )
    jres = runner.run("judge", judge_prompt, wt, timeout)
    if jres.skipped_reason is not None:
        return defer(f"judge run skipped: {jres.skipped_reason}")
    first = next((ln.strip() for ln in jres.text.splitlines() if ln.strip()), "")
    if first != "ACCEPT":
        _remove_worktree(repo_root, wt, branch)  # branch kept for inspection
        summary = f"judge REJECT: {jres.text.strip()[:1000]}"
        store.set_status(task_id, "rejected", review="rejected",
                         branch=branch, result_summary=summary)
        return "rejected"

    with _merge_lock:
        merge = _git(["-c", "user.name=kiraci-bot", "-c", "user.email=bot@kiraci.local",
                      "merge", "--no-ff", branch, "-m", f"merge task {task_id}"],
                     repo_root)
        if merge.returncode != 0:
            _git(["merge", "--abort"], repo_root)
            return fail(f"merge conflict, aborted: {merge.stdout.strip()[:500]}")
    _remove_worktree(repo_root, wt, branch)
    store.set_status(task_id, "done", review="accepted", branch=branch,
                     result_summary=f"merged {branch}: {stat[:500]}")
    return "done"
