from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import ventures
from .config import REVENUE_DEFAULTS, load_config
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
def request_spend(agent: str, bucket: str, amount_eur: float, purpose: str,
                  venture_id: int | None = None) -> dict:
    """Request a spend. The decision is made by policy: approved / pending / rejected.
    If pending, a human must approve it; you cannot approve it yourself.
    Spending from the experiment bucket requires a building/live venture id."""
    amount_cents = _cents(amount_eur)
    if bucket == "experiment":
        if venture_id is None:
            return {"status": "rejected",
                    "reason": "experiment spending requires a venture_id"}
        try:
            budget = int(load_config().revenue_value("venture_budget_cents"))
        except (OSError, ValueError):
            budget = int(REVENUE_DEFAULTS["venture_budget_cents"])
        gate = ventures.authorize_experiment_spend(
            _ledger.conn, venture_id, amount_cents, budget)
        if gate is not None:
            return {"status": "rejected", "reason": gate}
    return _ledger.request_spend(agent, bucket, amount_cents, purpose,
                                 venture_id=venture_id)


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
