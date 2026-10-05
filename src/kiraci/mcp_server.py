"""Agent-facing ledger MCP server: a thin IPC client.

This server runs INSIDE the agent sandbox. It must never import or open the
database; every call is forwarded through the broker, which binds it to the
identity of the run (never to agent-supplied text) and enforces the per-agent
tool allowlist. Human-only operations (approve, reject, record_income,
init_genesis) have no broker handler and are unreachable by construction.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, ParamSpec

from mcp.server.fastmcp import FastMCP

from .ipc import IpcError, call

mcp = FastMCP("kiraci-ledger")

P = ParamSpec("P")


def _guard(fn: Callable[P, dict[str, Any]]) -> Callable[P, dict[str, Any]]:
    # functools.wraps keeps the real signature: FastMCP builds the tool
    # schema by introspection, and *args/**kwargs would leak into it as
    # required fields and break every call. Dict-shaped tools only: list
    # tools must let IpcError propagate (see list_pending).
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except IpcError as e:
            return {"status": "error", "reason": str(e)}
    return wrapper


def _expect_dict(tool: str, out: Any) -> dict[str, Any]:
    if not isinstance(out, dict):
        raise IpcError(f"broker returned non-dict for {tool}")
    return out


def _expect_list(tool: str, out: Any) -> list[dict[str, Any]]:
    if not isinstance(out, list):
        raise IpcError(f"broker returned non-list for {tool}")
    return out


@mcp.tool()
@_guard
def get_balances() -> dict[str, Any]:
    """Return bucket balances in EUR (infra, tokens, experiment, emergency, owner)."""
    return _expect_dict("get_balances", call("ledger", "get_balances", {}))


@mcp.tool()
@_guard
def request_spend(agent: str | None = None, bucket: str = "", amount_eur: float = 0.0,
                  purpose: str = "", venture_id: int | None = None) -> dict[str, Any]:
    """Request a spend. The decision is made by policy: approved / pending / rejected.
    If pending, a human must approve it; you cannot approve it yourself.
    Spending from the experiment bucket requires a building/live venture id.
    Note: identity is assigned by the system; any agent argument is ignored.
    """
    return _expect_dict("request_spend", call("ledger", "request_spend", {
        "bucket": bucket, "amount_eur": amount_eur, "purpose": purpose,
        "venture_id": venture_id,
    }))


@mcp.tool()
def list_pending() -> list[dict[str, Any]]:
    """List spend requests that are waiting for human approval.

    No _guard here by design: on IPC failure the IpcError propagates and
    FastMCP returns a proper retryable tool error. An error *dict* would
    violate the list output schema (seen live with list_ventures).
    """
    return _expect_list("list_pending", call("ledger", "list_pending", {}))


@mcp.tool()
def recent_entries(limit: int = 20) -> list[dict[str, Any]]:
    """Most recent ledger entries (amounts in cents, newest first).

    No _guard here by design (see list_pending): IpcError must propagate
    so the list output schema is never violated by an error dict.
    """
    return _expect_list("recent_entries",
                        call("ledger", "recent_entries", {"limit": limit}))


if __name__ == "__main__":
    mcp.run()  # stdio transport