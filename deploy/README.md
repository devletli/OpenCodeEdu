# Kiraci one-time setup (human)

1. Create user `kiraci` and clone this repo to `/opt/kiraci`.
2. Create the venv and install: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.
3. Log in to the model provider(s) as the `kiraci` user (`opencode auth login`).
4. Copy `.env.example` to `.env` and fill it in (model names in `provider/model` format; Telegram optional).
5. Initialize the ledger: `python -m kiraci.cli init`.
6. Install and start the unit: `systemctl enable --now kiraci`.
7. Watch with `journalctl -u kiraci -f` and `python -m kiraci.cli status`.
8. Stop everything with `python -m kiraci.cli kill`.
