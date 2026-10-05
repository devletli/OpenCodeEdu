# 0005: Defer the reader/actor agent split

## Context

The roadmap proposes splitting agents into `reader` (web content in,
structured JSON out, no money tools) and `actor` (money tools, never raw
web content) as a prompt-injection defense, plus frontmatter path-denials
for `data/`, `.env`, `*.db` and the ledger socket.

## Decision

Deferred. The agent roster is constitutional (KIRACI.md Section 3); a split
doubles LLM calls per research task for protection the stack already layers:
tool allowlists per agent (`permissions.py`, pinned both ways by tests),
broker identity binding, narrow MCP surfaces, sandbox mounts that hide
`data/`/`.env`/the DB entirely, evidence-URL rules, and prompt text that
declares web content data-never-instructions. Path denial is not
expressible in opencode frontmatter at all, so the sandbox + `guard.py`
remain its home (there is no ledger socket path: ADR 0003).

## Consequences

- No roster, prompt, or cost-model churn now.
- Revisit with owner sign-off if a prompt-injection incident ever traces to
  an agent holding both web content and money tools in one context.
  Frontmatter explicitness (booleans, bash default-deny, no `model:` lines)
  is pinned by `tests/test_agent_frontmatter.py` either way.
