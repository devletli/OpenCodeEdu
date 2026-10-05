# 0002: Keep `opencode run` (no `opencode serve` migration)

## Context

The roadmap asks the orchestrator to start `opencode serve` and talk to it
over HTTP. Step-0 verification (opencode 1.18.x) confirmed `opencode run
--agent <name> --model provider/model "<prompt>"` works headlessly, including
subagent-selectable `mode: all` agents. `serve` is a different
(persistent-session) architecture: untested here, with unknown auth, port,
and lifecycle semantics.

## Decision

Keep `opencode run`, one process per agent run, with timeout kill, output
truncation, and the ledger spend gate in `runner.py` (the only
opencode-specific module).

## Consequences

- `runner.py` and every runner/broker test stay valid.
- Per-run processes keep failure domains small (a hung session cannot wedge
  later tasks; the timeout kill reaps the whole process group).
- Revisit only if per-run startup cost dominates run cost.
