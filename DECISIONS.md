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

## v0.3 (revenue engine)

- **Payment adapter: VERIFIED, not UNVERIFIED.** Current public docs reached 2026-09-30: list endpoint `GET https://api.lemonsqueezy.com/v1/orders` (docs.lemonsqueezy.com/api/orders/list-all-orders), `Authorization: Bearer` + JSON:API headers, filters `filter[store_id]/[user_email]/[order_number]` (no server-side date filter, so the adapter pages `sort=-created_at` and stops client-side), cent amount fields, `status`/`refunded`/`first_order_item.product_id`/`test_mode` (the-order-object page). Fee estimate 5% + 50c confirmed on lemonsqueezy.com/pricing (2026), still labelled an estimate (surcharges possible).
- **`mcp` pinned to `>=1.2,<2` in pyproject.** The loose pin resolved to mcp 2.2.0, where `mcp.server.fastmcp` no longer exists, so both MCP servers failed at import. Downgraded to mcp 1.30.0; migrating to the 2.x server API would be a bigger, riskier change.
- **Migration keeps one transaction without `executescript`.** `executescript` implicitly commits pending transactions, so `migrate()` uses only single-statement `conn.execute` calls inside explicit BEGIN/COMMIT.
- **`human_tasks` rebuilt via a temp name, no FK toggle.** `human_tasks_new` is created/copied, the old table dropped, then renamed: `tasks.blocked_on` keeps pointing at `human_tasks` because nothing ever references the temp name. Verified by resolving a blocked task post-migration in tests.
- **State machine gains `building->paused` and `paused->building`.** The hand-off (§5) pauses after 2 failed rounds from `building`, and without `paused->building` a fixed venture could never reach `live` again (only `building` ventures are scanned, `live` needs an external id).
- **Handoff finds ventures by scanning `products/<slug>/`** after every merged builder task, not by task metadata (the `tasks` table has no venture column and the spec adds none). `publish:<slug>` dedupe + `publish_rounds:<slug>` kv keep it idempotent.
- **FakeRunner's default output carries 3 source URLs** so pre-existing scout dispatch tests pass unchanged through the new §8 evidence check; the <3 path is covered by dedicated tests.
- **Poller provider name is configuration** (`revenue.payment_provider`, default `lemonsqueezy`); only Lemon Squeezy is implemented. Optional `revenue.payment_store_id` adds the `filter[store_id]` param (docs show no date filter, so store scoping is the only server-side narrowing).
- **`test_mode` orders are skipped silently** (recording test income as real income would corrupt the ledger).
- **Refund uses its own ref namespace** (`refund:order:<provider>:<id>`) because `record_refund` idempotency keys on `{ref}:experiment` like income does.
- **Day-90 notice goes through `send_info`** (Telegram if configured + one dated inbox line), not a human task; the system never stops itself.
- **Treasurer/brain prompts reference the latest metrics file** via a one-line pointer, and weekly retro task prompts carry the SKILL-block instruction; ingestion runs only for the exact-titled "Weekly retrospective" task.
- **Skipped-budget convention reused:** budget-skipped scout/builder runs defer the same way in v0.3; evidence re-runs reuse `set_status` with an extended field allowlist (`prompt`, `title` added to `Store.set_status`).
- **Agent modes resolved empirically (post-v0.3):** `opencode run --agent scout`
  on a `mode: subagent` file prints `agent "scout" not found. Falling back to
  default agent` — subagents are NOT selectable headlessly. Per the TASK 2
  Step-0 fallback, all 7 task agents are now `mode: all` (verified: `> scout`
  selected, no fallback). `brain` stays `mode: primary`, also verified
  selectable. The same ping test confirmed `openrouter/z-ai/glm-4.7-flash` runs.
- **Windows shim crash fixed:** `opencode` on PATH here is an npm/nvm shim
  (.cmd/.ps1/shell stub) that CreateProcess cannot execute, so the first real
  tick died with FileNotFoundError inside Popen. `resolve_opencode_binary()`
  now finds the real `node_modules/opencode-ai/bin/opencode.exe` next to the
  shim (verified locally), and any remaining spawn OSError fails the run
  (status `error`, normal attempts path) instead of killing the daemon. The
  crashed tick had already passed the 5c spend gate, so the ledger holds an
  audited `run brain` expense with no matching run row — accepted as-is.
- **Model picks from OpenRouter weekly-usage + price tables:** output price
  dominates agent cost (5.3-flash $0.2475 vs 5.3 $4.00, 16x). STRONG =
  `openrouter/z-ai/glm-5` (~3.4c per brain session, newest flagship reasoning;
  4.7 at ~2.5c was the runner-up). MID/CHEAP = `openrouter/z-ai/glm-5.3-flash`
  ($0.02/$0.2475, #3 by weekly usage at 12.3T tokens). Fallbacks if prices
  move: DeepSeek V4 Flash 0731 ($0.0099/$0.1307) for cheap tiers; free
  Space-Bunny/Nemotron rows rejected (unknown provenance/rate limits — wrong
  for the money pipeline).

## v0.4: Hardening (TASK 4) - decisions and findings

- **Step 0 environment findings (2026-10-01, Windows 11 host):**
  - `bwrap` is NOT available on Windows (`CommandNotFoundException`), and
    unprivileged user namespaces do not apply. Per the task, everything is
    implemented anyway: `sandbox.status()` reports `unavailable` here, the
    bwrap integration test is skipped with that reason, and with config
    `mode = "required"` no real agent run is dispatched on this host (a daily
    system notice explains the fix). `KIRACI_SANDBOX=off` +
    `KIRACI_ALLOW_UNSANDBOXED=1` allows the six no-bash/no-write agents.
  - Python 3.13.15, SQLite 3.50.4: `Connection.backup()` available.
  - `os.O_NOFOLLOW` is unavailable on Windows; the broker therefore uses
    `lstat` regular-file checks everywhere and adds `O_NOFOLLOW` only where
    the platform provides it.
  - opencode data paths (Step 0): auth at `%USERPROFILE%\.local\share\opencode\auth.json`,
    config at `%USERPROFILE%\.config\opencode\opencode.jsonc`, state at
    `%USERPROFILE%\.local\state\opencode\`. The sandbox home copies auth.json
    + config files (0600) into a private 0700 home.
  - `opencode stats` exists ("show token usage and cost statistics") but is a
    per-project summary table without a machine-readable cumulative total, so
    `LocalStatsProbe` was NOT implemented; the provider probe is the single
    probe (preferred by the spec anyway).
  - `.env` on this host defines KIRACI_MODEL_STRONG/MID/CHEAP, TELEGRAM_*,
    LEMONSQUEEZY_API_KEY, KIRACI_OWNER_NAME - but no OPENROUTER_API_KEY yet,
    so until the human adds it the system files the one `env-usage-probe`
    task and multiplies all paid estimates by the conservative 2.0x.
- **OpenRouter usage adapter VERIFIED against current docs**
  (https://openrouter.ai/docs/api-reference/limits, fetched 2026-10-01):
  `GET https://openrouter.ai/api/v1/key` returns `data.usage` (credits used,
  all time), `data.usage_daily` (current UTC day), in USD. The probe converts
  with `usd_to_eur` (0.92, labelled an estimate). `usage_daily` removes the
  need for a local daily baseline in the hard-stop check.
- **Deterministic no-LLM jobs run around the clock.** The v0.2 tick only ran
  jobs during awake hours (06:00-22:00 UTC), but the spec schedules backup at
  22:30 UTC and verify before it - both inside the night. `tick()` now runs
  `_always_jobs()` (reconcile, verify, backup) in BOTH branches, and PAUSE no
  longer skips them (a verify finding pauses the system; backups must keep
  running exactly then). PAUSE still blocks all LLM work as before.
- **PAUSE keeps LLM work blocked, jobs keep state**: `paused` summary line is
  unchanged, verify/backup/reconcile events are appended after it.
- **`booked` excludes `reconcile:` refs.** Without this exclusion a second
  reconcile run would undo the first booking (the correction entry itself
  would count as "booked"), breaking idempotency. Estimates are ref-NULL
  expenses; refunds use `refund:`; corrections use `reconcile:<date>:<n>`.
- **Hard-stop check is throttled to every 30 minutes** (kv `hardstop_checked_ts`)
  instead of every tick: the provider endpoint is a network call and ticks run
  every 30s. Between checks the kv-based `paid_paused_until` still binds.
- **`python -m` entry points unchanged for agents:** mcp_server/queue_mcp keep
  tool names and parameters; `agent`/`caller` stay optional and are IGNORED
  ("identity is assigned by the system"). The old module-level
  `Ledger(connect())` construction is gone - importing the MCP servers never
  opens a database (tested).
- **`Ledger._insert` writes `ts` from Python** (millisecond format matching
  the SQLite default) because the hash chain needs the exact ts as input.
  First implementation used `%f` as seconds - caught by the daily-cap test
  (spent_today went to 0) and fixed to `%S.%f`.
- **Agent file changes (per spec):** builder.md lost the four git allow-list
  entries and gained the "you cannot use git" line (the orchestrator commits);
  brain.md and the orchestrator planning prompt lost the `caller=` instruction;
  diplomat.md gained `queue_list_ventures: true` to match TOOLS_BY_AGENT
  (the consistency test is bidirectional). judge.md untouched.
- **Test updates required by the new flow (assertions kept, not removed):**
  runner child env no longer contains KIRACI_DB (assertion inverted); paid-run
  estimates carry the 2.0x multiplier without a probe key (3c -> 6c asserted);
  `_child_env(None)` signature in the payments test; spend-gate tests moved
  from the old mcp_server module-level ledger to BrokerSession (the gate now
  lives in the broker); migration tests assert version 4 and the backfilled
  chain.
- **Residual risks (also in deploy/README.md):** the model-provider credential
  must be readable inside the sandbox and egress is unrestricted, so a
  prompt-injected agent could try to exfiltrate the key; mitigation is
  outside the software (dedicated key, provider-side spending limit, rotation).
  On hosts without bwrap, mode `required` blocks all real agent runs (safe
  default); the explicit unsandboxed override only ever runs agents without
  bash/write tools.
- **systemd-analyze verify unavailable here** (Windows host): the unit files were written to match the existing kiraci.service style; syntax was reviewed manually. Note for the deploy host: run systemd-analyze verify once after copying.
- **Smoke checks done on this host:** v0.3 fixture DB migrated to v0.4 by the orchestrator's own connect() (hash backfilled over 4 genesis rows, verify healthy); orchestrator --once --dry-run prints its one-line summary and files env-usage-probe (no key yet); cli verify healthy, cli backup into a temp root, cli heartbeat-check exit 0 (fresh install), cli status shows sandbox/cost/heartbeat fields.
