from datetime import UTC, datetime, timedelta

from kiraci.config import Config
from kiraci.db import connect
from kiraci.heartbeat import heartbeat_check
from kiraci.logsetup import setup_logging
from kiraci.store import Store


def test_redaction_filter_masks_keys_and_cards(tmp_path):
    logger = setup_logging(tmp_path, name="kiraci-test")
    logger.info("key sk-abcdef1234567890 and card 4111111111111111 sent")
    for h in logger.handlers:
        h.flush()
    log_file = tmp_path / "data" / "logs" / "kiraci.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "sk-abcdef1234567890" not in content
    assert "4111111111111111" not in content
    assert "[REDACTED]" in content


def test_log_file_is_json_lines(tmp_path):
    logger = setup_logging(tmp_path, name="kiraci-json")
    logger.warning("hello %s", "world")
    for h in logger.handlers:
        h.flush()
    import json

    lines = (tmp_path / "data" / "logs" / "kiraci.log").read_text(
        encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[-1])
    assert payload["level"] == "WARNING"
    assert payload["msg"] == "hello world"


def test_fresh_heartbeat_and_kill_are_healthy(tmp_path):
    conn = connect(":memory:")
    store = Store(conn)
    config = Config(ops={"heartbeat_stale_minutes": 15})
    now = datetime.now(UTC)
    store.kv_set("last_tick", now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    code, _ = heartbeat_check(store, tmp_path, config, now=now)
    assert code == 0
    (tmp_path / "data" / "KILL").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "KILL").touch()
    store.kv_set("last_tick", "2020-01-01T00:00:00Z")
    code, _ = heartbeat_check(store, tmp_path, config, now=now)
    assert code == 0  # KILL present -> healthy exit


def test_stale_tick_alerts_once_per_hour(tmp_path):
    conn = connect(":memory:")
    store = Store(conn)
    config = Config(ops={"heartbeat_stale_minutes": 15})
    now = datetime.now(UTC)
    store.kv_set("last_tick",
                 (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    code1, msg1 = heartbeat_check(store, tmp_path, config, now=now)
    assert code1 == 1 and "stale" in msg1
    assert store.kv_get("hb_alert_ts") is not None
    inbox = (tmp_path / "HUMAN_INBOX.md").read_text(encoding="utf-8")
    assert "SYSTEM" in inbox
    first_alert = store.kv_get("hb_alert_ts")
    # immediately again: still exit 1, but no second alert
    code2, msg2 = heartbeat_check(store, tmp_path, config, now=now)
    assert code2 == 1
    assert store.kv_get("hb_alert_ts") == first_alert
    assert "already sent" in msg2
    inbox2 = (tmp_path / "HUMAN_INBOX.md").read_text(encoding="utf-8")
    assert inbox2.count("SYSTEM") == 1
    # an hour later: alerts again
    later = now + timedelta(hours=2)
    code3, _ = heartbeat_check(store, tmp_path, config, now=later)
    assert code3 == 1
    assert store.kv_get("hb_alert_ts") == later.isoformat()