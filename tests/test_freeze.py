"""Freeze flag: human-only toggle, broker-wide refusal (Phase 1)."""

import json
import sys

import pytest

from kiraci.broker import BrokerSession
from kiraci.cli import cmd_status
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.store import Store


def fresh():
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    return ledger, Store(conn)


def test_freeze_roundtrip_defaults_unfrozen():
    _, store = fresh()
    assert store.is_frozen() is False
    assert store.set_frozen(True) is True
    assert store.is_frozen() is True
    assert store.set_frozen(False) is False


def test_broker_refuses_everything_when_frozen(tmp_path):
    ledger, store = fresh()
    store.set_frozen(True)
    session = BrokerSession("r1", "scout", tmp_path / "ipc" / "s",
                            ledger=ledger, store=store)
    try:
        for server, tool, args in (
                ("ledger", "get_balances", {}),
                ("ledger", "request_spend", {"bucket": "infra"}),
                ("queue", "list_tasks", {}),
                ("queue", "create_task", {"agent": "x"})):
            assert session.execute(server, tool, args) == {
                "ok": False,
                "error": "frozen: the human froze the system; "
                         "all agent tools refuse until `kiraci unfreeze`"}
        assert ledger.balances()["infra"] == 3000  # nothing booked
    finally:
        session.cleanup()


def test_broker_works_unfrozen(tmp_path):
    ledger, store = fresh()
    session = BrokerSession("r1", "treasurer", tmp_path / "ipc" / "s",
                            ledger=ledger, store=store)
    try:
        assert session.execute("ledger", "get_balances", {})["ok"] is True
    finally:
        session.cleanup()


def test_status_reports_frozen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text("[limits]\n", encoding="utf-8")
    ledger, store = fresh()
    assert cmd_status(ledger, store)["frozen"] is False
    assert "Frozen: no" in cmd_status(ledger, store)["status_text"]
    store.set_frozen(True)
    assert cmd_status(ledger, store)["frozen"] is True
    assert "Frozen: YES" in cmd_status(ledger, store)["status_text"]


def test_cli_freeze_unfreeze_and_verify_exit(tmp_path, monkeypatch, capsys):
    from kiraci import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text("[limits]\n", encoding="utf-8")
    db = tmp_path / "live.db"
    monkeypatch.setenv("KIRACI_DB", str(db))
    conn = connect(str(db))
    try:
        Ledger(conn).init_genesis()
    finally:
        conn.close()

    monkeypatch.setattr(sys, "argv", ["kiraci", "freeze"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["frozen"] is True
    monkeypatch.setattr(sys, "argv", ["kiraci", "unfreeze"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["frozen"] is False

    monkeypatch.setattr(sys, "argv", ["kiraci", "verify"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "healthy"


def test_cli_verify_exits_nonzero_on_break(tmp_path, monkeypatch, capsys):
    from kiraci import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text("[limits]\n", encoding="utf-8")
    db = tmp_path / "live.db"
    monkeypatch.setenv("KIRACI_DB", str(db))
    conn = connect(str(db))
    try:
        Ledger(conn).init_genesis()
        conn.execute(
            "INSERT INTO ledger(kind,bucket,delta_cents,agent,note)"
            " VALUES ('expense','infra',-1,'mallory','x')")
    finally:
        conn.close()
    monkeypatch.setattr(sys, "argv", ["kiraci", "verify"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "findings"
