# DECISIONS.md (v0.2 implementation log)

One bullet per decision: what, why. Autonomy contract: no questions asked.

- **Step 0: opencode 1.18.31 is installed here.** `opencode run` really supports `--agent <name>`, `-m/--model provider/model` and a positional message, matching the spec's assumption. Kept the default human-readable `--format` (judge parsing needs the first non-empty line to be ACCEPT/REJECT).
- **Agent `mode:` values left unchanged.** The contract allowed only 3 opencode invocations, so whether `mode: subagent` agents are selectable via `--agent` could not be verified. The spec's own expected command assumes it works, so modes stay; all opencode specifics are isolated in `runner.py`. Human can verify on the Linux host with `opencode run --agent scout --model <m> "ping"`.
- **MCP env inheritance unverified** for the same reason. `opencode.json` has no `environment` block per spec; the runner always exports an absolute `KIRACI_DB`, and both MCP servers read it via `connect()`.
- **`core.hooksPath` uses `os.devnull`, not `/dev/null`.** Spec's literal path does not exist on Windows (`nul` does). Same for snapshot commits.
- **Child env allowlist extended on Windows** with `SYSTEMROOT`/`USERPROFILE`/`TEMP`/`TMP`. The bare POSIX allowlist breaks child process creation on Windows.
- **Timeout kill is platform-split:** POSIX starts a new session and kills the process group; Windows uses `CREATE_NEW_PROCESS_GROUP` + `proc.kill()`.
- **Daily human-task limit counts rows with `created_by != 'orchestrator'`.** The schema has no caller-type column; agent names are spoofable anyway (known v0.1 limitation), so the exemption is by name, set only on code paths the orchestrator itself calls.
- **Night blackout (22:00–06:00 UTC) is absolute.** Not even priority-0 tasks dispatch; the tick returns after the heartbeat.
- **Survival mode skips brain sessions and judge reviews** (both cost > 0, and only cost-0 runs may dispatch). Red approvals are still filed to the inbox (filing costs nothing); yellow reviews wait.
- **Tasks whose agent tier has no model configured stay pending** without attempts increment (environmental, not task failure). The one-shot `env-models` human task tells the human what to put in `.env`.
- **`skipped_reason` convention:** a reason starting with `budget:` means the ledger refused the spend → task deferred to 00:05 UTC next day, kept pending. Any other skip reason defers the same way (safe default).
- **Merge commits carry explicit `-c user.name=kiraci-bot` identity.** Hosts without a global git identity (e.g. the `kiraci` service user) would otherwise fail every merge.
- **MCP `request_human_action` notifies the inbox immediately.** The orchestrator only notifies for tasks it creates itself; CLI `human add` does not notify (the human is already looking at it).
- **Watchdog disk-full writes one raw dated line to `HUMAN_INBOX.md`.** A human task is not allowed for this (not a login), per spec.
- **`.gitkeep` only in tracked content dirs** (`journal research people personas skills products tools`), not in git-ignored `workspace/`, `data/`, `data/outputs/`.
- **Resolve/dismiss unblocks only tasks currently `blocked`.** A task the human cancelled stays cancelled.
- **Timeout test uses `sys.executable -c "sleep"`** instead of a `sleep` binary (none exists on Windows).
- **TASK 1 rule 8 overridden by TASK 2 §12/§14** for exactly two edits: removing the `model:` line from `judge.md`, and appending Section 15 to `KIRACI.md`. Nothing else in those files was touched.
- **`FakeRunner` lives in `src/kiraci/testing.py`, not `tests/`,** so `orchestrator --dry-run` can use it without importing test code.
- **Lint:** installed ruff 0.16.9 enforces more than the classic default set (UP/BLE/S/PLW/ISC/RUF). All findings fixed in source with behavior-preserving changes (UTC alias, explicit `check=False`, specific exception tuples + stderr notes instead of blind `except: pass`, parenthesized concatenation, f-strings). No test was weakened.
