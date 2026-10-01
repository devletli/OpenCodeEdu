"""Single source of truth for which MCP tools each agent may call.

The broker enforces this allowlist. The `tools:` blocks in
`.opencode/agent/*.md` must stay consistent with this table; a test parses
those lines and fails on any mismatch in either direction.
"""

from __future__ import annotations

TOOLS_BY_AGENT: dict[str, frozenset[str]] = {
    "brain": frozenset({
        "ledger_get_balances", "ledger_recent_entries",
        "queue_create_task", "queue_list_tasks", "queue_list_human_tasks",
        "queue_request_human_action", "queue_create_venture",
        "queue_update_venture", "queue_list_ventures",
    }),
    "builder": frozenset({
        "ledger_request_spend", "queue_request_human_action",
        "queue_list_human_tasks", "queue_list_ventures",
    }),
    "scout": frozenset({"queue_list_tasks", "queue_list_ventures"}),
    "seller": frozenset({"queue_list_tasks", "queue_list_ventures"}),
    "diplomat": frozenset({"queue_list_tasks", "queue_list_ventures"}),
    "chronicler": frozenset({
        "ledger_get_balances", "ledger_recent_entries",
        "queue_list_tasks", "queue_list_ventures",
    }),
    "treasurer": frozenset({
        "ledger_get_balances", "ledger_recent_entries", "ledger_list_pending",
        "queue_list_tasks", "queue_list_ventures",
    }),
    "judge": frozenset({"ledger_recent_entries", "ledger_list_pending"}),
}


def tool_allowed(agent: str, server: str, tool: str) -> bool:
    """True iff agent may call <server>_<tool>. Identity is system-assigned."""
    return f"{server}_{tool}" in TOOLS_BY_AGENT.get(agent, frozenset())