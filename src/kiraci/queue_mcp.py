from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import ventures
from .config import load_config
from .db import connect
from .notify import notify_human
from .store import Store

# Only queue tools safe for agents. resolve/dismiss/approve stay human-only (CLI).
mcp = FastMCP("kiraci-queue")
_store = Store(connect())


@mcp.tool()
def create_task(
    agent: str,
    title: str,
    prompt: str,
    caller: str,
    priority: int = 5,
    requires_review: bool = False,
) -> dict:
    """Queue a task for another agent. The brain is not a task agent."""
    return _store.create_task(
        agent=agent,
        title=title,
        prompt=prompt,
        priority=priority,
        requires_review=requires_review,
        created_by=caller,
    )


@mcp.tool()
def list_tasks(status: str | None = None, limit: int = 30) -> list[dict]:
    """List queued tasks, newest first."""
    if status is not None and status not in (
        "pending", "running", "blocked", "done", "failed", "rejected", "cancelled",
    ):
        return [{"status": "error", "reason": f"unknown status: {status}"}]
    return _store.list_tasks(status=status, limit=limit)


@mcp.tool()
def request_human_action(
    kind: str,
    title: str,
    instructions: str,
    dedupe_key: str,
    caller: str,
    url: str = "",
    blocks_task_id: int | None = None,
) -> dict:
    """Ask the human for a login/account action. Max title 120, instructions 1500 chars."""
    result = _store.add_human_task(
        kind=kind,
        title=title,
        instructions=instructions,
        url=url,
        dedupe_key=dedupe_key,
        created_by=caller or "unknown-agent",
        blocks_task_id=blocks_task_id,
    )
    if result.get("status") == "created":
        try:
            notify_human(result["task"], root=Path.cwd(), store=_store)
        except (OSError, sqlite3.Error) as e:
            print(f"kiraci: inbox notify failed: {e}", file=sys.stderr)
    return result


@mcp.tool()
def list_human_tasks(status: str = "open") -> list[dict]:
    """List human inbox tasks (open by default)."""
    if status not in ("open", "done", "dismissed"):
        return [{"status": "error", "reason": f"unknown status: {status}"}]
    return _store.list_human_tasks(status=status)


def _revenue_cfg():
    try:
        return load_config()
    except (OSError, ValueError):
        from .config import Config
        return Config()


@mcp.tool()
def create_venture(
    name: str,
    kind: str,
    hypothesis: str,
    score: float,
    evidence_paths: list[str],
    caller: str,
) -> dict:
    """Propose a venture. Needs score >= 6 and 2+ research files with 3+ sources."""
    cfg = _revenue_cfg()
    return ventures.create_venture(
        _store, Path.cwd(), name=name, kind=kind, hypothesis=hypothesis,
        score=score, evidence_paths=evidence_paths or [], caller=caller,
        max_active=int(cfg.revenue_value("max_active_ventures")),
        min_sources=int(cfg.revenue_value("min_sources_per_research")),
    )


@mcp.tool()
def update_venture(
    venture_id: int, status: str, caller: str, death_note: str = "",
) -> dict:
    """Move a venture through its gates. Illegal transitions are rejected."""
    try:
        return ventures.update_venture(
            _store, Path.cwd(), venture_id, status, death_note=death_note)
    except ValueError as e:
        return {"status": "error", "reason": str(e)}


@mcp.tool()
def list_ventures(status: str | None = None) -> list[dict]:
    """List ventures, optionally filtered by status."""
    return ventures.list_ventures(_store.conn, status)


if __name__ == "__main__":
    mcp.run()  # stdio transport
