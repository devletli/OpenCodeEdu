"""Agent-facing queue MCP server: a thin IPC client.

Runs INSIDE the agent sandbox; never touches the database. The broker binds
`created_by`/`caller` to the run's system-assigned identity, so spoofing the
caller is impossible (and any caller argument is ignored). Resolving or
dismissing human tasks stays human-only (CLI) and has no broker handler.
"""

from __future__ import annotations

import functools

from mcp.server.fastmcp import FastMCP

from .ipc import IpcError, call

mcp = FastMCP("kiraci-queue")


def _guard(fn):
    # functools.wraps keeps the real signature: FastMCP builds the tool
    # schema by introspection, and *args/**kwargs would leak into it as
    # required fields and break every call.
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except IpcError as e:
            return {"status": "error", "reason": str(e)}
    return wrapper


@mcp.tool()
@_guard
def create_task(agent: str, title: str, prompt: str, caller: str | None = None,
                priority: int = 5, requires_review: bool = False) -> dict:
    """Queue a task for another agent. The brain is not a task agent.
    Note: identity is assigned by the system; any caller argument is ignored.
    """
    return call("queue", "create_task", {
        "agent": agent, "title": title, "prompt": prompt,
        "priority": priority, "requires_review": requires_review,
    })


@mcp.tool()
def list_tasks(status: str | None = None, limit: int = 30) -> list[dict]:
    """List queued tasks, newest first.

    No _guard here by design: on IPC failure the IpcError propagates and
    FastMCP returns a proper retryable tool error. An error *dict* would
    violate the list output schema (seen live with list_ventures).
    """
    return call("queue", "list_tasks", {"status": status, "limit": limit})


@mcp.tool()
@_guard
def request_human_action(kind: str, title: str, instructions: str, dedupe_key: str,
                         caller: str | None = None, url: str = "",
                         blocks_task_id: int | None = None) -> dict:
    """Ask the human for a login/account action. Max title 120, instructions 1500 chars.
    Note: identity is assigned by the system; any caller argument is ignored.
    """
    return call("queue", "request_human_action", {
        "kind": kind, "title": title, "instructions": instructions,
        "dedupe_key": dedupe_key, "url": url, "blocks_task_id": blocks_task_id,
    })


@mcp.tool()
def list_human_tasks(status: str = "open") -> list[dict]:
    """List human inbox tasks (open by default).

    No _guard here by design (see list_tasks): IpcError must propagate
    so the list output schema is never violated by an error dict.
    """
    return call("queue", "list_human_tasks", {"status": status})


@mcp.tool()
@_guard
def create_venture(name: str, kind: str, hypothesis: str, score: float,
                   evidence_paths: list[str], caller: str | None = None) -> dict:
    """Propose a venture. Needs score >= 6 and 2+ research files with 3+ sources.
    Note: identity is assigned by the system; any caller argument is ignored.
    """
    return call("queue", "create_venture", {
        "name": name, "kind": kind, "hypothesis": hypothesis,
        "score": score, "evidence_paths": evidence_paths or [],
    })


@mcp.tool()
@_guard
def update_venture(venture_id: int, status: str, caller: str | None = None,
                   death_note: str = "") -> dict:
    """Move a venture through its gates. Illegal transitions are rejected.
    Note: identity is assigned by the system; any caller argument is ignored.
    """
    return call("queue", "update_venture", {
        "venture_id": venture_id, "status": status, "death_note": death_note,
    })


@mcp.tool()
def list_ventures(status: str | None = None) -> list[dict]:
    """List ventures, optionally filtered by status.

    No _guard here by design (see list_tasks): IpcError must propagate
    so the list output schema is never violated by an error dict.
    """
    return call("queue", "list_ventures", {"status": status})


if __name__ == "__main__":
    mcp.run()  # stdio transport