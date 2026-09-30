import json
import os
import sys

import pytest

from kiraci.config import Config
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.runner import OpencodeRunner
from kiraci.store import Store


@pytest.fixture
def wired(tmp_path, monkeypatch):
    monkeypatch.setenv("KIRACI_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("KIRACI_MODEL_CHEAP", "test/cheap")
    monkeypatch.setenv("KIRACI_MODEL_MID", "test/mid")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    store = Store(conn)
    config = Config(
        models={"scout": "cheap", "builder": "mid"},
        costs={"builder": 3},
        limits={},
    )
    return {"ledger": ledger, "store": store, "config": config}


def _py(code):
    return [sys.executable, "-c", code]


def test_command_is_list_with_agent_and_model(wired):
    seen = {}

    def builder(agent, model, prompt):
        seen["cmd"] = ["echo-cmd", agent, model, prompt]
        return [sys.executable, "-c", "pass"]

    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"], cmd_builder=builder)
    res = runner.run("scout", "hello", ".", 60)
    assert res.ok
    assert seen["cmd"][1] == "scout" and seen["cmd"][2] == "test/cheap"


def test_env_allowlist_excludes_secrets(wired, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "super-secret")
    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"],
                            cmd_builder=lambda a, m, p: _py(
                                "import os,json;print(json.dumps(dict(os.environ)))"))
    res = runner.run("scout", "hi", ".", 60)
    assert res.ok
    child_env = json.loads(res.text.strip().splitlines()[-1])
    assert "TELEGRAM_BOT_TOKEN" not in child_env
    assert os.path.isabs(child_env["KIRACI_DB"])
    assert os.path.isabs(runner.kiracidb)


def test_timeout_kills_process(wired):
    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"],
                            cmd_builder=lambda a, m, p: _py(
                                "import time;time.sleep(30)"))
    res = runner.run("scout", "hi", ".", 2)
    assert not res.ok and res.duration_s >= 2
    row = wired["store"].conn.execute(
        "SELECT status FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "timeout"


def test_paid_run_calls_request_spend_first(wired):
    calls = []

    def never(agent, model, prompt):
        calls.append(agent)
        raise AssertionError("must not run when the ledger refuses")

    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"], cmd_builder=never)
    # exhaust the 60c daily tokens cap first
    assert wired["ledger"].request_spend("s", "tokens", 60, "x")["status"] == "approved"
    res = runner.run("builder", "build it", ".", 60)
    assert not res.ok and res.skipped_reason.startswith("budget:")
    assert calls == []


def test_paid_run_spends_on_success(wired):
    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"],
                            cmd_builder=lambda a, m, p: _py("pass"))
    res = runner.run("builder", "build it", ".", 60)
    assert res.ok
    assert wired["ledger"].balances()["tokens"] == 3000 - 3


def test_missing_model_skips_without_spending(wired, monkeypatch):
    monkeypatch.delenv("KIRACI_MODEL_MID")
    calls = []

    def never(agent, model, prompt):
        calls.append(agent)
        return _py("pass")

    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"], cmd_builder=never)
    res = runner.run("builder", "build it", ".", 60)
    assert not res.ok and "no model" in res.skipped_reason
    assert calls == []
    assert wired["ledger"].balances()["tokens"] == 3000


def test_missing_binary_fails_run_instead_of_raising(wired):
    # Regression: on Windows `opencode` can be an unrunnable shim; Popen then
    # raises FileNotFoundError, which must fail the run, not kill the daemon.
    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"],
                            cmd_builder=lambda a, m, p: ["no-such-binary-xyz"])
    res = runner.run("scout", "hi", ".", 30)
    assert not res.ok and "failed to start" in res.text
    row = wired["store"].conn.execute(
        "SELECT status FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "error"


def test_resolve_opencode_binary():
    from kiraci.runner import resolve_opencode_binary

    assert resolve_opencode_binary()  # non-empty string, never raises
