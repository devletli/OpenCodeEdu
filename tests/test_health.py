"""Tests for the continuous health watchdog and its recovery scenarios."""

from datetime import UTC, datetime, timedelta

import pytest

from kiraci.config import Config
from kiraci.db import connect
from kiraci.health import BACKLOG_PENDING_N, HealthRunner, _parse_ts, claim_pidfile
from kiraci.ledger import Ledger
from kiraci.store import Store


def make_runner(tmp_path, now, **kw):
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    store = Store(conn)
    config = Config(models={}, costs={},
                    limits={"min_free_disk_mb": 1},
                    ops={"heartbeat_stale_minutes": 15,
                         "dashboard_port": 8787, "health_interval_s": 60})
    runner = HealthRunner(root=tmp_path, store=store, ledger=ledger,
                          config=config, clock=lambda: now, **kw)
    return runner, store, ledger


def fresh_tick(store, now):
    store.kv_set("last_tick", now.strftime("%Y-%m-%dT%H:%M:%SZ"))


NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def test_all_ok_no_actions(tmp_path):
    def no_spawn(*a, **k):
        raise AssertionError("must not spawn when healthy")

    runner, store, _ = make_runner(tmp_path, NOW, spawn=no_spawn)
    fresh_tick(store, NOW)
    findings, actions = runner.cycle()
    assert all(f.ok for f in findings)
    assert actions == []


def test_stale_tick_restarts_daemon_once(tmp_path):
    spawned = []
    runner, _store, _ = make_runner(
        tmp_path, NOW, spawn=lambda argv, cwd: spawned.append((argv, cwd))
        or type("P", (), {"pid": 4242})())
    findings = runner.check(NOW)
    tick = next(f for f in findings if f.name == "tick")
    assert not tick.ok and tick.severity == "crit"
    actions = runner.recover(findings, NOW)
    assert len(spawned) == 1
    argv, _cwd = spawned[0]
    assert argv[-3:] == ["-m", "kiraci.cli", "run"]
    assert any("restart" in a for a in actions)
    assert runner.recover(findings, NOW) == []  # no double start


def test_kill_file_blocks_everything(tmp_path):
    def no_spawn(*a, **k):
        raise AssertionError("KILL means hands off")

    runner, _store, _ = make_runner(tmp_path, NOW, spawn=no_spawn)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "KILL").touch()
    findings = runner.check(NOW)
    assert [f.name for f in findings] == ["killed"]
    assert all(f.ok for f in findings)
    assert runner.recover(findings, NOW) == []
    assert not (tmp_path / "data" / "PAUSE").exists()


def test_stale_running_requeued_old_only(tmp_path):
    runner, store, _ = make_runner(tmp_path, NOW)
    fresh_tick(store, NOW)
    old = store.create_task(agent="scout", title="Old", prompt="x",
                            priority=5, created_by="brain")["task_id"]
    new = store.create_task(agent="scout", title="New", prompt="x",
                            priority=5, created_by="brain")["task_id"]
    store.set_status(old, "running")
    store.set_status(new, "running")
    ancient = (NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    store.conn.execute("UPDATE tasks SET updated_at=? WHERE id=?",
                       (ancient, old))
    _findings, actions = runner.cycle()
    assert store.get_task(old)["status"] == "pending"
    assert store.get_task(old)["attempts"] == 1
    assert store.get_task(new)["status"] == "running"
    assert any("requeued 1" in a for a in actions)


def test_disk_crit_pauses_once(tmp_path, monkeypatch):
    notices = []
    runner, store, _ = make_runner(
        tmp_path, NOW,
        disk_usage=lambda p: type("D", (), {"free": 0})(),
        verify=lambda conn: [])
    monkeypatch.setattr("kiraci.health.send_info",
                        lambda msg, store, root=None: notices.append(msg))
    fresh_tick(store, NOW)
    findings, _actions = runner.cycle()
    disk = next(f for f in findings if f.name == "disk")
    assert not disk.ok and disk.severity == "crit"
    assert (tmp_path / "data" / "PAUSE").exists()
    assert len(notices) == 1
    before = store.kv_get("health_notice:pause-disk")
    runner.cycle()  # rate-limited: no second notice
    assert len(notices) == 1
    assert store.kv_get("health_notice:pause-disk") == before


def test_ledger_crit_pauses(tmp_path):
    runner, store, _ = make_runner(
        tmp_path, NOW, verify=lambda conn: ["broken chain"])
    fresh_tick(store, NOW)
    _findings, actions = runner.cycle()
    assert any("paused (ledger)" in a for a in actions)
    assert (tmp_path / "data" / "PAUSE").exists()


def test_backlog_only_notifies_never_acts(tmp_path, monkeypatch):
    monkeypatch.setattr("kiraci.health.BACKLOG_PENDING_N", 1)
    runner, store, _ = make_runner(tmp_path, NOW)
    fresh_tick(store, NOW)
    for i in range(3):
        store.create_task(agent="scout", title=f"T{i}", prompt="x",
                          priority=5, created_by="brain")
    findings, actions = runner.cycle()
    backlog = next(f for f in findings if f.name == "backlog")
    assert not backlog.ok
    assert actions == []


def test_sandbox_finding_never_blocks(tmp_path):
    runner, store, _ = make_runner(tmp_path, NOW)
    fresh_tick(store, NOW)
    findings, actions = runner.cycle()
    assert next(f for f in findings if f.name == "sandbox").ok
    assert actions == []


def test_pidfile_claim_and_stale(tmp_path):
    assert claim_pidfile(tmp_path) is True
    assert claim_pidfile(tmp_path) is True  # same process re-claims
    (tmp_path / "data" / "health.pid").write_text("999999999",
                                                  encoding="utf-8")
    assert claim_pidfile(tmp_path) is True  # dead pid: claimed


def test_run_forever_cycle_bound(tmp_path):
    sleeps = []
    runner, store, _ = make_runner(tmp_path, NOW)
    fresh_tick(store, NOW)
    assert runner.run_forever(sleep=sleeps.append, cycles=2) == 0
    assert len(sleeps) == 60 and all(s == 1.0 for s in sleeps)


def test_parse_ts_formats():
    assert _parse_ts("2026-10-05T10:00:00.000Z") == datetime(
        2026, 10, 5, 10, 0, tzinfo=UTC)
    assert _parse_ts("2026-10-05T10:00:00+00:00") == datetime(
        2026, 10, 5, 10, 0, tzinfo=UTC)
    assert _parse_ts("garbage") is None
    assert _parse_ts(None) is None
    assert BACKLOG_PENDING_N == 50


def test_cli_health_once_healthy(tmp_path, monkeypatch, capsys):
    import sys
    from datetime import datetime as real_datetime

    from kiraci import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text("[limits]\n", encoding="utf-8")
    db = tmp_path / "live.db"
    monkeypatch.setenv("KIRACI_DB", str(db))
    monkeypatch.setattr(sys, "argv", ["kiraci", "health", "--once"])
    conn = connect(str(db))
    try:
        Ledger(conn).init_genesis()
        Store(conn).kv_set(
            "last_tick",
            real_datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    finally:
        conn.close()
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert "health OK" in capsys.readouterr().out


def test_cli_health_once_crit_pauses_without_spawn(tmp_path, monkeypatch,
                                                    capsys):
    import sys
    from datetime import datetime as real_datetime

    from kiraci import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text("[limits]\n", encoding="utf-8")
    db = tmp_path / "live.db"
    monkeypatch.setenv("KIRACI_DB", str(db))
    monkeypatch.setattr(sys, "argv", ["kiraci", "health", "--once"])
    conn = connect(str(db))
    try:
        Ledger(conn).init_genesis()
        Store(conn).kv_set(
            "last_tick",
            real_datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
        # Data-level sabotage (schema repairs itself on connect, data doesn't):
        # a hash-less expense that drives infra negative.
        conn.execute(
            "INSERT INTO ledger(kind,bucket,delta_cents,agent,note)"
            " VALUES ('expense','infra',-99999,'x','sabotage')")
    finally:
        conn.close()
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "ledger" in out and "paused (ledger)" in out
    assert (tmp_path / "data" / "PAUSE").exists()
    conn = connect(str(db))
    try:
        # ledger crit pauses; it must never start a daemon by itself
        assert Store(conn).kv_get("health_daemon_started") is None
    finally:
        conn.close()
