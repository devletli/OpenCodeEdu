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
- **Sandbox runtime location fixed (post-v0.4 check):** native Windows cannot run bubblewrap at all (kernel namespaces), but WSL2 Ubuntu on this host has bwrap 0.11.1 with the probe passing. A sudo-less venv (~/kiraci-venv, --without-pip + get-pip.py because ensurepip is absent) runs kiraci inside WSL; there cli status reports sandbox_status: ok, the full test suite passes 196/196 with the bwrap integration tests live (0 skipped), and cli verify/dry-run are clean. On the Windows side the suite stays 195 passed + 1 skipped (integration). One real bug surfaced and was fixed: Sandbox.sandbox_home crashed via 
elative_to when opencode files live outside the real home (now mirrors the absolute structure); the bwrap integration test was otherwise dead code (never ran anywhere) and had two latent bugs (venv interpreter hidden by the tmpfs /home -> realpath needed; a missing closing paren). Note: user-namespace bind mounts are implicitly nodev, so the .env mask fails CLOSED with EACCES - accepted per spec ('fails or is empty').

## Continuous operation (2026-10-02)

- **Shift windows removed; all agents dispatch 06:00-22:00 UTC.** On the free-model tier a run costs ~0, so the "rhythm saves money" premise of KIRACI.md §4 no longer holds — idle gaps only delayed work (e.g. builder tasks waiting hours for 12:30). Queue order is priority-then-oldest; the 22:00-06:00 night blackout stays absolute (priority 0 included). KIRACI.md §4 table and AGENTS.md daemon rules updated; TASKs.md untouched (frozen bootstrap spec).
- **Judge verdict parsing tolerates the opencode transcript.** Formatted `opencode run` output prefixes a session header (`> judge · model`) and tool echoes, so "first non-empty line" could never be ACCEPT. `_judge_verdict` now takes the last bare ACCEPT/REJECT line (fail closed); builder_flow shares it and keeps the output tail in the summary so real rejections stay auditable.
- **Tier env vars hold fallback chains for free-quota exhaustion.** `KIRACI_MODEL_*` accept comma-separated `provider/model` lists (primary first); `Config.tier_models()` parses, `model_for()` stays primary-first for compat. `OpencodeRunner.run` tries the next model when a run fails with quota/rate-limit/overload/removed-model output (auth failures and timeouts return as-is, and a successful run never rotates even if its text mentions e.g. a fetch 404). Winner persists in kv, reset to primary daily (free quotas reset). Spare models verified live 2026-10-02 (free+tools from the OpenRouter model list, strict ACCEPT probe): strong → thinkingmachines/inkling, poolside/laguna-s-2.1; mid → cohere/north-mini-code; cheap → inclusionai/ling-3.0-flash-sante, liquid/lfm-2.5-2.6b, apodex/apodex-1.1-mini. qwen3.8/gemma-4-31b probed but ignored the instruction, excluded.

## TASK2.md remediation (2026-10-05)

- **`.gitignore` extended additively.** Existing entries kept; added `/journal/*`, `/research/*`, `/products/*`, `/scripts/outputs/*` (+ `.gitkeep` exceptions), `*.db`, `*.sqlite3`, `*.log`, `venv/`. Already-tracked snapshot files stay tracked (gitignore does not untrack); new runtime files are ignored going forward.
- **Snapshot persistence is dual-write, not a cutover.** New `src/kiraci/daemon.py` (`init_db`/`save_snapshot`/`list_snapshots`, DB `data/state.db` or `KIRACI_STATE_DB`) records every `git_snapshot` tick in SQLite best-effort (never crashes the tick). The git commit path is kept unchanged so v0.2 `git_snapshot` semantics and history keep working; SQLite is the durable local log per TASK2.md.
- **Docker sandbox added as `tools/sandbox.py`, bwrap kept.** `run_in_sandbox()` builds a list-only `docker run --rm --network none --memory 256m --cpus 0.5 --user 1000:1000` with a single `:ro` submission-file mount — no `.env`, project, or `.opencode` mounts. `src/kiraci/sandbox.py` (bwrap) untouched; verified live on this host (`print(42)` → exit 0).
- **Pre-commit is lint-only.** `.pre-commit-config.yaml` runs `ruff-check --fix` (catches E741 locally); `ruff-format-check` omitted because existing files are not format-clean and would block commits. No `.github/workflows/` exists in repo; `pyproject.toml` already sets `pythonpath=["src"]`, so no PYTHONPATH workaround to remove.

## Dashboard human-inbox actions (owner-authorized, 2026-10-05)

- **Owner scope: human inbox only.** The human asked for GUI resolve/dismiss and accepted the trade-off ("sadece human için gerekli tasklara ekle sorun yok"). KIRACI.md gains Section 18; Sections 15/17 otherwise untouched.
- **Design:** GET `/human` list + GET `/human/<id>` confirm page (form with per-process CSRF token, note field, done/dismiss buttons via `formaction`, no JS); POST only on `/human/<id>/done|dismiss`. All other POST/PUT/DELETE/HEAD paths still 405. Writes use a dedicated writable connection (`Store.resolve_human_task`); reads stay `mode=ro`. Notes pass `find_secret` like the CLI. Success uses 303 redirect (PRG); errors are 400/403/404 pages with the same security headers.
- **Tests updated, not weakened:** `test_non_get_methods_return_405` still asserts 405 for PUT/DELETE/HEAD and for POST to `/` and unknown paths; 5 new tests cover the confirm page, CSRF rejection, done/dismiss flows, double-resolve and secret-note rejection.
- **Residual risk:** loopback-only + per-process token bounds CSRF to code running on the same host/browser; approve/spend/restore remain unreachable by construction (no handlers).
- **Dashboard/CLI DB mismatch fixed.** `python -m kiraci.dashboard` previously started nothing (no `__main__` block); added `main()` (cwd root + `load_config`). Worse, `serve()` hardcoded `<root>/data/kiraci.db` while the CLI honors `KIRACI_DB`, so GUI and CLI could silently read different databases (seen live: GUI listed an open task the CLI could not see). `serve()` now prefers `KIRACI_DB` via `resolve_db_path()` and prints the exact file it serves; behavior without the env var is unchanged.
- **Two live DBs found (2026-10-05).** Windows CLI uses `D:\ProjAI\OpencodeEdu\data\kiraci.db` (all human tasks done); the WSL dashboard (pid 221, since 03:25, root `/home/dev/kiraci-run`) serves its own DB where human task #4 (Lemon Squeezy setup for the handbook) is still open. The venv imports code from the Windows checkout via `/mnt/d`, so the running dashboard had the OLD POST handler in memory (405) until restarted (new pid 8697; verified GET /human 200, token-less POST 403, confirm page carries CSRF). Open question for the owner: which DB is the source of truth long-term.
- **Live system = WSL daemon (pid 199, since 03:25).** cwd is the Windows checkout (outputs land in `research/` etc. there), `KIRACI_DB` points at the WSL DB, free-tier model chains configured, ticks fresh, recent runs all ok, no KILL/PAUSE, queue fully worked through (28 done / 6 rejected). Nothing was stuck: no `running`/`blocked`/`failed` rows anywhere. The 5 pending in the Windows scratch DB were moved by hand: 3 real research prompts re-queued into the live WSL queue as #35-37 (`created_by="human"`), 2 `X araştırması` placeholders cancelled as prompt-less; the 3 moved copies cancelled in scratch as "moved to live WSL queue". Daemon picked #37 up on the next tick (running), #35-36 follow one per tick.
- **Venture #5 live (owner, 2026-10-05).** Handbook went `validating → building → live` with `external_product_id=1413610` (numeric LS product ID, not the buy-link UUID). Gate check passed first: `[validate]` task #17 done with a clean result file. `set-product` CLI only moves `building`/`paused` → `live`, so the `validating → building` step ran through the same `update_venture` code path the brain uses (no CLI exists for it — owner did it by hand). Payment poller now maps orders to venture #5; manual poll auth ok, 0 orders yet.
- **Single-DB decision (owner, 2026-10-05).** Windows `data/kiraci.db` retired to `data/archive/kiraci-windows-20261005.db` (7 ledger rows, 5 cancelled tasks; verified readable, git-ignored). Live DB is `/home/dev/kiraci-run/data/kiraci.db` only. Rule: every `kiraci.cli` invocation runs inside WSL with `KIRACI_DB` (now exported in `/home/dev/.bashrc`); Windows-side Python is for code/tests only (`pytest` uses `:memory:`, never the live DB). Rationale: SQLite over the `\\wsl$` 9P share under a writing daemon risks locking corruption; single writer (WSL) avoids it. Do not recreate `data/kiraci.db` on Windows.

## Continuous-Windows roadmap (owner directive, 2026-10-05; no questions asked)

- **No asyncio rewrite.** The tick loop stays synchronous: 200+ tests are sync, a single-threaded tick avoids SQLite concurrency hazards, and agent runs are blocking subprocess calls anyway. The directive's intent (self-contained loop, no `.sh`/systemd dependency, crash recovery, DB-persisted resume) is met by `run_forever` + a new backoff supervisor in `kiraci run`.
- **No `opencode serve`.** Step-0 verified `opencode run --agent --model` on 1.18.31; `serve` is a different (persistent-session) architecture that would invalidate `runner.py` and every runner/broker test. Kept `run`.
- **Crash policy:** `kiraci run` restarts the orchestrator with exponential backoff (5s, doubling to 300s cap) on nonzero exit or uncaught exception only. Exit 0 (KILL-file stop) stays stopped — the kill switch must never be overridden by a supervisor.
- **Resume:** `startup()` requeues stale `running` tasks to `pending` (attempts+1, summary notes the restart), so a killed/restarted daemon (e.g. WSL reboot) resumes cleanly instead of stranding tasks. Jobs, kv, approvals were already DB-persisted.
- **Survival cheapest-model:** `OpencodeRunner.survival_mode` flag (default False); the orchestrator sets it every tick from the survival check, and model selection then uses the cheap-tier chain for every agent. The ledger spend gate and the cost-0 dispatch filter are untouched (defense in depth; existing survival tests keep passing).
- **queue_mcp already compliant:** agents can only enqueue + read (`create_task`, `list_tasks`, `request_human_action`, `list_human_tasks`, venture create/update/list-read); resolve/dismiss/approve/income/set-product have no MCP handler. Added an explicit test asserting the privileged names are absent from both MCP surfaces.
- **Tests run in WSL** (`/home/dev/kiraci-venv`, ext4 `/tmp`, `:memory:` DBs); no Windows paths or `.bat`/`.ps1` anywhere in this work.
- **Never use numeric %-formats in log calls.** The secret-redaction filter stringifies every log arg in place, so `%.0f` blows up at emit time (caught by the new supervise tests). F-strings only.
- **Live daemon restarted onto the new code (owner ok, 2026-10-05).** Old pid 199 (03:25, pre-TASK2) stopped gracefully via KILL file after its tick; new supervisor pid runs `kiraci run`. Restart proved the resume path twice: task #43 (killed mid-seller-run) came back `pending` with attempts+1 both times. Provider/notify keys now live in `/home/dev/kiraci-run/.env` (0600, copied from the Windows `.env` without printing values) and the daemon is started sourcing it; key presence verified in the new process env. Two inbox tasks went stale in the process (`env-models`, `env-payments`) — owner dismisses via GUI.
