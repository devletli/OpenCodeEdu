# 0003: Broker sessions instead of a unix-socket ledger service

## Context

The roadmap asks for a single-writer ledger service over a unix socket,
MCP servers rewritten as its thin clients, and a `kiraci serve-ledger`
command. The security property behind it — agents never open the database,
unspoofable identity, one disciplined write path — already holds via the
v0.4 IPC broker: MCP servers are thin IPC clients (no `sqlite3`, no
`connect()`, verified by `tests/test_no_db_in_mcp.py`), the broker binds
every call to the run's identity, enforces the per-agent allowlist plus the
freeze flag, and writes go through `BEGIN IMMEDIATE` on a single-threaded
tick (one writer at a time in practice).

## Decision

No socket service, no MCP rewrite, no `serve-ledger` command. The broker
is the single-writer discipline; `test_broker.py` pins the allowlist and
the human-only set, `test_no_db_in_mcp.py` pins the import boundary.

## Consequences

- No new daemon to supervise, no socket permissions/paths to manage, no
  20+ invalidated tests.
- If agents ever need concurrent (multi-threaded) dispatch, revisit: put a
  real single-writer queue in front of SQLite at that point.
