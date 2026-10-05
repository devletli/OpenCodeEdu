# 0001: Keep the synchronous tick loop (no asyncio rewrite)

## Context

The roadmap asks for "a single Python asyncio loop" driving the orchestrator.
The existing orchestrator is a synchronous tick loop (`run_forever` + 10-30 s
sleep), covered by 200+ synchronous tests. Ticks are single-threaded by
design: one task per tick, one SQLite writer, no lock contention.

## Decision

Keep the synchronous loop. Continuity without manual steps is provided by
`kiraci run` (crash backoff supervisor) plus DB-persisted state (kv jobs,
tasks, approvals) and startup resume of orphaned `running` rows.

## Consequences

- No `asyncio` migration risk to the money path; no test churn.
- Concurrency hazards SQLite would face under asyncio (shared connections
  across coroutines) are avoided by construction.
- If tick latency ever blocks scheduling (sub-10 s ticks), revisit with a
  thread-per-run design, not a full rewrite.
