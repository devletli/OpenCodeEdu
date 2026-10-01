"""Heartbeat watcher: alerts when the daemon stops ticking.

`python -m kiraci.cli heartbeat-check` exits 0 when the last tick is younger
than [ops].heartbeat_stale_minutes or when data/KILL exists; otherwise it sends
a Telegram alert (at most one per hour, tracked in kv) and appends a system
notice to HUMAN_INBOX.md. Meant for a systemd timer (deploy/kiraci-heartbeat.*).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path


def last_tick_dt(store) -> datetime | None:
    raw = store.kv_get("last_tick")
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        try:
            dt = datetime.fromisoformat(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return None


def heartbeat_age_minutes(store, now: datetime) -> float | None:
    ts = last_tick_dt(store)
    if ts is None:
        return None
    return (now - ts).total_seconds() / 60


def heartbeat_check(store, root: Path, config, now: datetime | None = None) -> tuple[int, str]:
    """Returns (exit_code, message). Alerts at most once per hour."""
    now = now or datetime.now(UTC)
    root = Path(root)
    if (root / "data" / "KILL").exists():
        return 0, "killed: KILL file present"
    stale_after = float(config.ops_value("heartbeat_stale_minutes"))
    age = heartbeat_age_minutes(store, now)
    if age is None:
        return 0, "no heartbeat yet (fresh install)"
    if age <= stale_after:
        return 0, f"heartbeat fresh ({age:.1f} min old)"
    last_alert = store.kv_get("hb_alert_ts")
    alert = True
    if last_alert:
        try:
            alert = (now - datetime.fromisoformat(last_alert)) >= timedelta(hours=1)
        except ValueError:
            alert = True
    msg = f"heartbeat stale: last tick {age:.1f} min ago (limit {stale_after:g})"
    if alert:
        store.kv_set("hb_alert_ts", now.isoformat())
        from .notify import send_info
        send_info(f"Kiraci daemon heartbeat STALE. {msg}. Is the service down?",
                  store, root=root)
        inbox = root / "HUMAN_INBOX.md"
        try:
            with inbox.open("a", encoding="utf-8") as f:
                f.write(f"\n[{now.strftime('%Y-%m-%d')}] SYSTEM: {msg}\n")
        except OSError:
            pass
        return 1, msg
    return 1, msg + " (alert already sent within the last hour)"