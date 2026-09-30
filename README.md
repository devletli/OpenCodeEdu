# Kiraci

A multi-agent system that pays its own bills. It starts with a EUR 100 budget,
tracks every cent in an append-only ledger, and has to earn enough to keep
covering its own rent (server) and food (LLM tokens). If the money runs out,
it dies.

The rules it lives by are in [KIRACI.md](KIRACI.md).

## What is in this repo (v0.1)

This first version contains only the foundation: the budget engine.

| Path | Purpose |
|---|---|
| `src/kiraci/rules.py` | Pure spending-policy function (no I/O, easy to test) |
| `src/kiraci/ledger.py` | Append-only ledger, approvals, income split |
| `src/kiraci/mcp_server.py` | MCP server exposing the safe, agent-facing tools |
| `src/kiraci/cli.py` | Human-only CLI: init, approve, reject, record income |
| `tests/` | Policy, ledger and fuzz tests |
| `.opencode/agent/` | Agent definitions for opencode |

## Design principles

- **Money is stored as integer cents.** No floats.
- **The ledger is append-only.** SQLite triggers block UPDATE and DELETE.
- **Agents can only *request* spending.** Approving, recording income and
  funding are human/system operations and are not exposed over MCP.
- **Limits matter more than identity.** Agents pass their own name, so it can be
  spoofed; the real protection is daily caps, bucket balances and human approval.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q

export KIRACI_DB=$PWD/data/kiraci.db
python -m kiraci.cli init          # creates the EUR 100 genesis budget
python -m kiraci.cli balances
python -m kiraci.cli pending       # requests waiting for human approval
python -m kiraci.cli approve 1
python -m kiraci.cli income --amount-eur 9.99 --ref order_123
```

## Budget buckets

| Bucket | Genesis | Rule |
|---|---|---|
| infra | EUR 30 | Server and domain |
| tokens | EUR 30 | LLM usage, daily cap EUR 0.60 |
| experiment | EUR 25 | Ads, fees, product tests. Locked in survival mode |
| emergency | EUR 15 | Human approval only |
| owner | EUR 0 | Profit share for the human owner. Human approval only |

Spending tiers: up to EUR 3 is automatic, EUR 3-10 needs approval (yellow),
above EUR 10 needs the human owner (red).

Income is split 50% experiment / 30% emergency / 20% owner.

## Using it with opencode

1. Fill in the `model:` placeholders in `.opencode/agent/*.md`.
2. Adjust the `KIRACI_DB` path in `opencode.json`.
3. Run agents inside a separate `git worktree`, ideally in a container that
   mounts `src/`, `tests/`, `KIRACI.md` and `.opencode/` read-only.

## Roadmap

- `queue-mcp`: task and approval queue
- Python orchestrator: systemd timers, `opencode serve`, daily rhythm
- Payment webhook service that calls `record_income` (never an agent)
- People cards and the social layer
