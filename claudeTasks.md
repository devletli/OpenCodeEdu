You are the lead engineer on this repo. Read README.md, KIRACI.md, AGENTS.md, DECISIONS.md and the whole src/ and tests/ tree first.

RULES
- Do not ask me questions. Decide, then record each decision in docs/adr/NNNN-title.md (context, decision, consequences).
- Environment: WSL2 Ubuntu, bash, Linux paths only. No .bat/.ps1. DB lives on the ext4 filesystem, never under /mnt/c.
- Work in phases, in order. After each phase: run `make check`, fix until green, then `git commit` with a conventional message. Never skip a failing test, never weaken a test to pass.
- Keep money as integer cents. Keep the ledger append-only. Approval and income-recording stay human-only (CLI), never exposed through any MCP tool.
- If a phase is blocked, write the blocker to BLOCKERS.md, skip to the next phase, and continue.

PHASE 0: Hygiene and tooling
- Move root scratch/debug files into scratch/ and gitignore them. Remove the literal '%SystemDrive%' directory.
- Add Makefile targets: install, lint, type, test, check (= lint + type + test), run, status, verify.
- Add ruff, mypy --strict, pytest, hypothesis, pre-commit config. Add .github/workflows/ci.yml running `make check` on every push/PR.
- Add .env.example (no real secrets) and make config load from env via a single settings module.

PHASE 1: Ledger hardening
- Open every connection with these pragmas: journal_mode=WAL, synchronous=FULL, foreign_keys=ON, busy_timeout=5000. Use BEGIN IMMEDIATE for all writes.
- Add a hash chain: each ledger row stores prev_hash and row_hash = sha256(prev_hash || canonical_json(row)). Add `kiraci verify` that recomputes the chain and exits non-zero on any break.
- Add idempotency_key (UNIQUE) to every spend/income/token-usage entry. A retry with the same key must return the original result, not write twice.
- Add a `frozen` flag table. `kiraci freeze` / `kiraci unfreeze` (human CLI only). Every MCP tool checks it first and refuses when frozen.
- Tests (hypothesis): balance never negative; sum of all buckets is conserved across any sequence of valid operations; replaying the same idempotency key N times changes nothing; tampering with any row makes `verify` fail.

PHASE 2: Single-writer ledger service
- Create src/kiraci/ledger_service.py: the ONLY process that opens the DB file for writing. It exposes a minimal API over a unix domain socket (path from settings, mode 0600). Policy from rules.py is enforced inside this service.
- Rewrite mcp_server.py so MCP tools are thin clients of that socket. MCP tools never import sqlite3 or open the DB.
- Add a test that greps src/kiraci/mcp_server.py and the agent dirs and fails if sqlite3 is imported there.
- Add `kiraci serve-ledger` command.

PHASE 3: Agent sandbox and permissions
- Update opencode.json and .opencode/agent/*.md: explicit allowlist for bash/edit/webfetch per agent; deny read/write on data/, .env, *.db, and the ledger socket path for everything except the MCP clients.
- Split roles: `reader` agent (reads external content, has NO money tools, outputs structured JSON summaries only) and `actor` agent (has money tools, never receives raw external content, only the reader's JSON). Document this in an ADR.
- Any spend above the configured threshold requires human approval via the queue (Phase 4).

PHASE 4: Queue, orchestrator, notifications
- src/kiraci/queue_mcp.py: task + approval queue (SQLite, same discipline). Agents can enqueue and read only.
- src/kiraci/orchestrator.py: asyncio loop with a persisted state machine (wake, plan, work, report, sleep), lease-based task claiming, retries with exponential backoff, crash-safe resume from DB state. It starts `opencode serve` and talks to it over HTTP.
- Before EVERY LLM call the orchestrator checks the daily token cap and the frozen flag. Cap exceeded means sleep until the next day, not an error loop.
- Survival mode: when total balance < configured threshold, lock the experiment bucket and switch all agents to the cheapest configured model.
- Notifications: src/kiraci/notify.py sends pending approvals to ntfy (topic and server from settings) with approve/deny links handled by a tiny local FastAPI endpoint that requires a signed, single-use token.
- CLI: `kiraci run`, `kiraci status` (balances, pending approvals, today's token spend, runway in days).
- Tests: kill the orchestrator mid-task (subprocess + SIGKILL), restart, assert balances and queue are consistent; assert cap enforcement cannot be bypassed.

PHASE 5: Provider-side budget limit
- Add a LiteLLM proxy config (litellm/config.yaml) with a hard daily budget and a per-model cheapest/premium split. All agents call the proxy, not providers directly. The ledger records the real `usage` returned by the proxy.
- Document how to rotate keys.

PHASE 6: Observability and dashboard
- structlog JSON logging, one event per agent call, spend, approval, freeze.
- Read-only dashboard (FastAPI + htmx, no Node): balances, runway, pending approvals, today's token spend, last 50 ledger rows with chain status.

PHASE 7: Containers and backup
- Dockerfiles + docker-compose.yml with three services: ledger (only one mounting the DB volume), orchestrator, sandbox (agents). Non-root, read-only rootfs, cap_drop ALL, egress limited to the LiteLLM proxy and ntfy.
- Backup: nightly `sqlite3 .backup` + restic to a configurable repo, plus a restore test in CI.
- Secrets via sops+age; only .env.example is committed.

FINISH
- Update README.md, KIRACI.md and the roadmap section to reflect reality. Write docs/RUNBOOK.md (start, stop, freeze, restore, rotate keys, what to do when balance hits survival mode).
- Print a final summary: what was done per phase, what is in BLOCKERS.md, and the exact commands I should run to start the system.