"""Tests for `kiraci run` supervision and today's-spend status fields."""

import os

import pytest

from kiraci.cli import cmd_status
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.orchestrator import build_status, supervise
from kiraci.store import Store


@pytest.fixture
def ledger_store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text("[limits]\ntick_seconds = 30\n",
                                           encoding="utf-8")
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    return ledger, Store(conn)


class _Sleeper:
    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


def test_supervise_clean_exit_no_restart():
    sleep = _Sleeper()
    calls = []
    assert supervise(lambda: calls.append(1) or 0, sleep=sleep) == 0
    assert calls == [1] and sleep.delays == []


def test_supervise_restarts_crash_then_stops_on_zero():
    sleep = _Sleeper()
    script = [Exception("boom"), 2, 0]

    def build_run():
        step = script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    assert supervise(build_run, sleep=sleep) == 0
    assert sleep.delays == [5.0, 10.0]


def test_supervise_backoff_doubles_and_caps():
    sleep = _Sleeper()
    code = supervise(lambda: 1, sleep=sleep, max_restarts=9)
    assert code == 1
    assert sleep.delays == [5.0, 10.0, 20.0, 40.0, 80.0, 160.0,
                             300.0, 300.0, 300.0]


def test_supervise_gives_up_after_max_restarts():
    sleep = _Sleeper()
    assert supervise(lambda: 3, sleep=sleep, max_restarts=2) == 3
    assert sleep.delays == [5.0, 10.0]


def test_status_today_spend_zero_at_genesis(ledger_store):
    ledger, store = ledger_store
    out = cmd_status(ledger, store)
    assert out["tokens_spent_today_cents"] == 0
    assert out["spend_today_by_bucket_cents"]["infra"] == 0
    assert "Tokens today: EUR 0.00" in out["status_text"]


def test_status_today_spend_tracks_token_runs(ledger_store):
    ledger, store = ledger_store
    assert ledger.request_spend("scout", "tokens", 40, "llm")["status"] == "approved"
    assert ledger.request_spend("builder", "infra", 100, "vps")["status"] == "approved"
    out = cmd_status(ledger, store)
    assert out["tokens_spent_today_cents"] == 40
    assert out["spend_today_by_bucket_cents"] == {
        "infra": 100, "tokens": 40, "experiment": 0, "emergency": 0, "owner": 0}
    assert "Tokens today: EUR 0.40 (cap EUR 0.60)" in out["status_text"]


def test_build_status_line_present(ledger_store):
    from datetime import UTC, datetime

    ledger, store = ledger_store
    text = build_status(store, ledger, datetime.now(UTC))
    assert "Tokens today:" in text and "Runway:" in text
    assert os.getcwd()  # documents the cwd dependency of cmd_status
