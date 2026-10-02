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


def test_env_allowlist_excludes_secrets_and_db(wired, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "super-secret")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"],
                            cmd_builder=lambda a, m, p: _py(
                                "import os,json;print(json.dumps(dict(os.environ)))"))
    res = runner.run("scout", "hi", ".", 60)
    assert res.ok
    child_env = json.loads(res.text.strip().splitlines()[-1])
    assert "TELEGRAM_BOT_TOKEN" not in child_env
    # v0.4: agents never see the database path
    assert "KIRACI_DB" not in child_env
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


def test_paid_run_calls_request_spend_first(wired, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
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


def test_paid_run_spends_on_success(wired, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"],
                            cmd_builder=lambda a, m, p: _py("pass"))
    res = runner.run("builder", "build it", ".", 60)
    assert res.ok
    # no usage probe configured: the conservative 2.0x multiplier applies
    assert wired["ledger"].balances()["tokens"] == 3000 - 6


def test_paid_run_uses_kv_multiplier_with_probe(wired, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    wired["store"].kv_set("cost_multiplier", "2.0")
    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"],
                            cmd_builder=lambda a, m, p: _py("pass"))
    res = runner.run("builder", "build it", ".", 60)
    assert res.ok
    assert wired["ledger"].balances()["tokens"] == 3000 - 6  # ceil(3*2.0)


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


def test_tier_models_parses_comma_chain(wired, monkeypatch):
    monkeypatch.setenv("KIRACI_MODEL_CHEAP", "test/a, test/b ,test/c")
    assert wired["config"].tier_models("cheap") == ["test/a", "test/b", "test/c"]
    assert wired["config"].model_for("scout") == "test/a"
    monkeypatch.delenv("KIRACI_MODEL_CHEAP")
    assert wired["config"].tier_models("cheap") == []
    assert wired["config"].model_for("scout") is None
    assert wired["config"].tier_models("nope") == []


def test_quota_exhausted_classifier():
    from kiraci.runner import quota_exhausted

    for text in ("Error 429: Rate limit exceeded: free-models-per-day",
                 "503 Service Unavailable, provider overloaded",
                 "model not found: openrouter/old-model:free",
                 "No endpoints found for model"):
        assert quota_exhausted(text), text
    for text in ("ACCEPT\nlooks good",
                 "401 Unauthorized: invalid api key",
                 "something broke\n[TIMEOUT after 60s]"):
        assert not quota_exhausted(text), text


def _quota_cmd():
    return _py("import sys; print('Error 429: free-models-per-day"
               " rate limit exceeded'); sys.exit(1)")


def test_fallback_rotates_on_quota_and_sticks(wired, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("KIRACI_MODEL_CHEAP", "test/primary,test/spare")
    tried = []

    def builder(agent, model, prompt):
        tried.append(model)
        return _quota_cmd() if model == "test/primary" else _py("print('fine')")

    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"], cmd_builder=builder)
    res = runner.run("scout", "hi", ".", 60)
    assert res.ok and tried == ["test/primary", "test/spare"]
    assert wired["store"].kv_get("model_fallback_idx:cheap") == "1"
    tried.clear()
    res2 = runner.run("scout", "hi", ".", 60)
    assert res2.ok and tried == ["test/spare"]  # spare tried first now


def test_success_with_404_in_text_does_not_rotate(wired, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("KIRACI_MODEL_CHEAP", "test/a,test/b,test/c")
    tried = []

    def builder(agent, model, prompt):
        tried.append(model)
        if model == "test/a":
            return _quota_cmd()
        # successful run whose text mentions a fetch 404: must not rotate
        return _py("print('fetched ok; one 404 GET https://example.com noted')")

    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"], cmd_builder=builder)
    res = runner.run("scout", "hi", ".", 60)
    assert res.ok and tried == ["test/a", "test/b"]


def test_no_rotation_on_auth_failure(wired, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("KIRACI_MODEL_CHEAP", "test/primary,test/spare")
    tried = []

    def builder(agent, model, prompt):
        tried.append(model)
        return _py("import sys; print('401 Unauthorized: invalid api key');"
                   " sys.exit(1)")

    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"], cmd_builder=builder)
    res = runner.run("scout", "hi", ".", 60)
    assert not res.ok and tried == ["test/primary"]
    assert wired["store"].kv_get("model_fallback_idx:cheap") == "0"


def test_no_rotation_on_timeout(wired, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("KIRACI_MODEL_CHEAP", "test/primary,test/spare")
    tried = []

    def builder(agent, model, prompt):
        tried.append(model)
        return _py("import time;time.sleep(30)")

    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"], cmd_builder=builder)
    res = runner.run("scout", "hi", ".", 2)
    assert not res.ok and tried == ["test/primary"]
    assert "[TIMEOUT after" in res.text


def test_daily_reset_retries_primary(wired, monkeypatch):
    from datetime import UTC, datetime

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("KIRACI_MODEL_CHEAP", "test/primary,test/spare")
    wired["store"].kv_set("model_fallback_day", "2000-01-01")
    wired["store"].kv_set("model_fallback_idx:cheap", "1")
    tried = []

    def builder(agent, model, prompt):
        tried.append(model)
        return _py("print('fine')")

    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"], cmd_builder=builder)
    res = runner.run("scout", "hi", ".", 60)
    assert res.ok and tried == ["test/primary"]
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    assert wired["store"].kv_get("model_fallback_day") == today


class _SandboxStub:
    """Pretends the sandbox is unavailable: unsandboxed run with IPC wiring."""

    def __init__(self, root):
        self.root = root

    def status(self, *, force=False):
        return "unavailable"

    def ipc_dir(self, run_id):
        d = self.root / "data" / "ipc" / run_id
        (d / "requests").mkdir(parents=True, exist_ok=True)
        (d / "responses").mkdir(parents=True, exist_ok=True)
        return d

    def sandbox_home(self, run_id):
        d = self.root / "data" / "sandbox" / f"home-{run_id}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def cleanup(self, run_id):
        import shutil
        for rel in ("ipc", "sandbox"):
            base = self.root / "data" / rel
            shutil.rmtree(base / run_id, ignore_errors=True)
            shutil.rmtree(base / f"home-{run_id}", ignore_errors=True)
            try:
                if base.is_dir() and not any(base.iterdir()):
                    base.rmdir()
            except OSError:
                pass


def test_run_wires_ipc_dir_and_cleans_up(wired, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("KIRACI_DB", str(tmp_path / "b.db"))
    sbx = _SandboxStub(tmp_path)
    runner = OpencodeRunner(ledger=wired["ledger"], store=wired["store"],
                            config=wired["config"],
                            cmd_builder=lambda a, m, p: _py(
                                "import os,json;print(json.dumps(dict(os.environ)))"),
                            sandbox=sbx, root=tmp_path)
    res = runner.run("scout", "hi", tmp_path, 60)
    assert res.ok
    child_env = json.loads(res.text.strip().splitlines()[-1])
    assert "KIRACI_IPC_DIR" in child_env  # agents reach the broker, not the DB
    assert "KIRACI_DB" not in child_env
    assert not (tmp_path / "data" / "ipc").exists()  # cleaned up after the run
    row = wired["store"].conn.execute(
        "SELECT status FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "ok"
