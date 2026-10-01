# Kiraci one-time setup (human)

1. Create user `kiraci` and clone this repo to `/opt/kiraci`.
2. Install bubblewrap and verify the sandbox probe:
   `sudo apt install bubblewrap`
   `bwrap --ro-bind / / --dev /dev --proc /proc --unshare-pid --die-with-parent true`
   (if this fails, enable unprivileged user namespaces:
   `sysctl kernel.unprivileged_userns_clone=1`, and check AppArmor restrictions).
3. Create the venv and install: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.
4. Log in to the model provider(s) as the `kiraci` user (`opencode auth login`).
5. Copy `.env.example` to `.env` and fill it in (model names in `provider/model` format; Telegram optional).
6. `chmod 600 /opt/kiraci/.env` - the secrets file is masked inside the sandbox.
7. Add `OPENROUTER_API_KEY` to `.env`: a DEDICATED key with a provider-side
   spending limit (the sandbox cannot restrict egress, so a prompt-injected
   agent could try to exfiltrate it; a capped key bounds the damage and can be
   rotated). Optionally add `KIRACI_BACKUP_DIR` (a mounted or synced folder;
   every backup is copied there too).
8. Initialize the ledger: `python -m kiraci.cli init`.
9. Install and start the units:
   `systemctl enable --now kiraci`
   `systemctl enable --now kiraci-heartbeat.timer`
   `systemctl enable --now kiraci-dashboard.service` (optional)
10. Watch with `journalctl -u kiraci -f` and `python -m kiraci.cli status`.
11. Open the dashboard through an SSH tunnel:
    `ssh -L 8787:127.0.0.1:8787 <server>` then browse to `http://127.0.0.1:8787`.
12. Stop everything with `python -m kiraci.cli kill`. Restoring a backup is a
    human-only operation: `python -m kiraci.cli restore <file> --yes`
    (refuses unless the daemon is killed and the heartbeat is stale).

## Known residual risks (accepted)

- The model-provider credential has to be readable inside the sandbox, and
  outbound network access is unrestricted: a prompt-injected agent could try
  to exfiltrate that key. Mitigation is outside the software: a dedicated
  provider key with a provider-side spending limit, rotated when needed.
- If the sandbox is unavailable, mode `required` stops all real agent runs and
  a daily system notice explains exactly what the host needs. The explicit
  override (`KIRACI_SANDBOX=off` + `KIRACI_ALLOW_UNSANDBOXED=1`) only ever
  runs agents with no bash and no write tools - never builder, never judge.