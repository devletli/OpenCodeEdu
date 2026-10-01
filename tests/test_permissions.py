import re
from pathlib import Path

from kiraci.permissions import TOOLS_BY_AGENT

AGENT_DIR = Path(__file__).resolve().parent.parent / ".opencode" / "agent"

HUMAN_ONLY_TOOLS = {
    "ledger_approve", "ledger_reject", "ledger_record_income",
    "ledger_record_refund", "ledger_init_genesis", "ledger_restore",
    "queue_resolve_human_task", "queue_dismiss_human_task",
    "queue_set_product", "queue_restore",
}


def _tool_lines(agent: str) -> set[str]:
    text = (AGENT_DIR / f"{agent}.md").read_text(encoding="utf-8")
    front = text.split("---", 2)[1] if text.startswith("---") else ""
    tools: set[str] = set()
    in_tools = False
    for line in front.splitlines():
        if line.startswith("tools:"):
            in_tools = True
            continue
        if in_tools:
            m = re.match(r"\s+(ledger_\w+|queue_\w+):\s*true\s*$", line)
            if m:
                tools.add(m.group(1))
            elif line.strip() and not line.startswith((" ", "\t")):
                break
    return tools


def test_every_agent_file_is_covered():
    files = {p.stem for p in AGENT_DIR.glob("*.md")}
    assert files == set(TOOLS_BY_AGENT), (files, set(TOOLS_BY_AGENT))


def test_tools_by_agent_matches_agent_files_both_ways():
    for agent, allowed in TOOLS_BY_AGENT.items():
        assert _tool_lines(agent) == set(allowed), agent


def test_no_human_only_tool_is_exposed_to_any_agent():
    for agent, allowed in TOOLS_BY_AGENT.items():
        assert not (allowed & HUMAN_ONLY_TOOLS), agent


def test_builder_never_gets_more_than_spend_and_queue_read():
    assert TOOLS_BY_AGENT["builder"] == frozenset({
        "ledger_request_spend", "queue_request_human_action",
        "queue_list_human_tasks", "queue_list_ventures",
    })


def test_tool_allowed_rejects_unknown_agents():
    from kiraci.permissions import tool_allowed

    assert tool_allowed("nobody", "ledger", "get_balances") is False
    assert tool_allowed("treasurer", "ledger", "get_balances") is True
    assert tool_allowed("treasurer", "ledger", "approve") is False