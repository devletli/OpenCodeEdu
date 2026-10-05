from __future__ import annotations

import http.client
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .store import Store

DIGEST_EVERY_SECONDS = 6 * 3600

#: Network-level failures a best-effort Telegram send may hit.
_TELEGRAM_ERRORS = (OSError, ValueError, http.client.HTTPException)


def _telegram_config() -> tuple[str, str] | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if token and chat:
        return token, chat
    return None


def _send_telegram(text: str) -> None:
    """Best effort only: 10 s timeout, never raises."""
    cfg = _telegram_config()
    if cfg is None:
        return
    token, chat = cfg
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat, "text": text[:4000]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except _TELEGRAM_ERRORS as e:
        print(f"kiraci: telegram send failed: {e}", file=sys.stderr)


def notify_human(task: dict[str, Any], *, root: Path | str | None = None,
                 store: Store | None = None) -> Path:
    """Append a human task to HUMAN_INBOX.md and optionally Telegram it.

    Always writes the inbox file. Sends at most one Telegram message per task.
    Never raises because of Telegram; file errors propagate to the caller.
    """
    root = Path(root) if root else Path.cwd()
    inbox = root / "HUMAN_INBOX.md"
    if not inbox.exists():
        inbox.write_text(
            "# Human Inbox\n\nNon-blocking requests from the Kiraci system. "
            "Only logins and account actions land here.\n",
            encoding="utf-8",
        )
    url_line = f"\n- URL: {task.get('url')}" if task.get("url") else ""
    section = (
        f"\n## Human task #{task['id']} [{task['kind']}] {task['title']}\n"
        f"\n{task['instructions']}\n"
        f"{url_line}\n"
        f"- Resolve: `python -m kiraci.cli human done {task['id']} --note \"...\"`\n"
        f"- Dismiss: `python -m kiraci.cli human dismiss {task['id']}`\n"
    )
    with inbox.open("a", encoding="utf-8") as f:
        f.write(section)
    if store is not None and _telegram_config() is not None:
        key = f"tg_sent:{task['id']}"
        try:
            if not store.kv_get(key):
                _send_telegram(
                    f"Kiraci needs you [{task['kind']}]: {task['title']}\n"
                    f"{task['instructions']}"
                )
                store.kv_set(key, "1")
        except (*_TELEGRAM_ERRORS, sqlite3.Error) as e:
            print(f"kiraci: telegram notify failed: {e}", file=sys.stderr)
    return inbox


def send_info(text: str, store: Store, *, root: Path | str | None = None) -> None:
    """One-way informational message (day-90 review, weekly metrics digest).

    Telegram if configured, plus a dated line in HUMAN_INBOX.md. Never a human
    task, never raises.
    """
    _send_telegram(text)
    try:
        root = Path(root) if root else Path.cwd()
        inbox = root / "HUMAN_INBOX.md"
        if not inbox.exists():
            inbox.write_text("# Human Inbox\n", encoding="utf-8")
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        with inbox.open("a", encoding="utf-8") as f:
            f.write(f"\n[{day}] INFO: {text}\n")
    except OSError as e:
        print(f"kiraci: info notify failed: {e}", file=sys.stderr)


def maybe_send_digest(store: Store, *, root: Path | str | None = None) -> bool:
    """Send a digest of all open tasks every 6 h while any are open."""
    if _telegram_config() is None:
        return False
    open_tasks = store.open_human_tasks()
    if not open_tasks:
        return False
    try:
        last = store.kv_get("digest_ts")
        if last:
            last_dt = datetime.fromisoformat(last)
            if datetime.now(UTC) - last_dt < timedelta(seconds=DIGEST_EVERY_SECONDS):
                return False
        lines = [f"#{t['id']} [{t['kind']}] {t['title']}" for t in open_tasks]
        _send_telegram(f"Kiraci open requests ({len(lines)}):\n" + "\n".join(lines))
        store.kv_set("digest_ts", datetime.now(UTC).isoformat())
        return True
    except (*_TELEGRAM_ERRORS, sqlite3.Error) as e:
        print(f"kiraci: telegram digest failed: {e}", file=sys.stderr)
        return False
