from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .db import connect
from .ledger import Ledger

# Only safe, agent-facing tools are exposed here.
# approve / reject / record_income / init_genesis are intentionally NOT available.
mcp = FastMCP("kiraci-ledger")
_ledger = Ledger(connect())


def _cents(eur: float) -> int:
    return round(eur * 100)


def _eur(cents: int) -> float:
    return cents / 100


@mcp.tool()
def get_balances() -> dict:
    """Return bucket balances in EUR (infra, tokens, experiment, emergency, owner)."""
    return {k: _eur(v) for k, v in _ledger.balances().items()}


@mcp.tool()
def request_spend(agent: str, bucket: str, amount_eur: float, purpose: str) -> dict:
    """Request a spend. The decision is made by policy: approved / pending / rejected.
    If pending, a human must approve it; you cannot approve it yourself."""
    return _ledger.request_spend(agent, bucket, _cents(amount_eur), purpose)


@mcp.tool()
def list_pending() -> list[dict]:
    """List spend requests that are waiting for human approval."""
    return _ledger.pending()


@mcp.tool()
def recent_entries(limit: int = 20) -> list[dict]:
    """Most recent ledger entries (amounts in cents, newest first)."""
    return _ledger.recent(limit)


if __name__ == "__main__":
    mcp.run()  # stdio transport
