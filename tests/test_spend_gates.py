"""Experiment spend gates, exercised through the broker (the MCP layer moved
into the broker in v0.4; the gate lives in BrokerSession._h_request_spend)."""

import pytest

from kiraci import ventures
from kiraci.broker import BrokerSession
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.store import Store

URLS = ("https://example.com/a", "https://example.com/b", "https://example.com/c")


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "a.md").write_text(
        "x\n\n- " + "\n- ".join(URLS[:2]) + "\n", encoding="utf-8")
    (tmp_path / "research" / "b.md").write_text(f"y {URLS[2]}\n", encoding="utf-8")
    monkeypatch.setenv("KIRACI_CONFIG", str(tmp_path / "t.toml"))
    (tmp_path / "t.toml").write_text("[revenue]\nventure_budget_cents = 500\n",
                                     encoding="utf-8")
    db = str(tmp_path / "g.db")
    conn = connect(db)
    ledger = Ledger(conn)
    ledger.init_genesis()
    store = Store(conn)
    r = ventures.create_venture(
        store, tmp_path, name="Gadget", kind="digital_product",
        hypothesis="Sells.", score=8.0,
        evidence_paths=["research/a.md", "research/b.md"], caller="brain")
    assert r["status"] == "created", r
    return {"store": store, "ledger": ledger, "root": tmp_path, "db": db,
            "vid": r["venture"]["id"]}


def _spend(ctx, bucket, amount_eur, purpose, venture_id=None, agent="builder"):
    """One broker call with system-assigned identity, no thread needed."""
    session = BrokerSession(
        "run-1", agent, ctx["root"] / "ipc" / agent, root=ctx["root"],
        connect_fn=lambda: connect(str(ctx["db"])))
    try:
        payload = session.execute("ledger", "request_spend", {
            "bucket": bucket, "amount_eur": amount_eur, "purpose": purpose,
            "venture_id": venture_id})
        assert payload["ok"] is True, payload
        return payload["result"]
    finally:
        import shutil
        shutil.rmtree(ctx["root"] / "ipc" / agent, ignore_errors=True)


def _to_building(ctx):
    store, root, vid = ctx["store"], ctx["root"], ctx["vid"]
    task = ventures.find_validation_task(store, "Gadget")
    clean = root / "research" / "validation.md"
    clean.write_text(f"ok {URLS[0]}\n", encoding="utf-8")
    store.set_status(task["id"], "done", result_path=str(clean))
    assert ventures.update_venture(store, root, vid, "validating")["status"] == "ok"
    assert ventures.update_venture(store, root, vid, "building")["status"] == "ok"


def test_experiment_spend_without_venture_rejected(ctx):
    out = _spend(ctx, "experiment", 1.0, "ads")
    assert out["status"] == "rejected" and "venture_id" in out["reason"]


def test_researching_venture_rejected(ctx):
    out = _spend(ctx, "experiment", 1.0, "ads", venture_id=ctx["vid"])
    assert out["status"] == "rejected" and "building or live" in out["reason"]


def test_budget_cap_across_spends(ctx):
    _to_building(ctx)
    first = _spend(ctx, "experiment", 3.0, "ads", venture_id=ctx["vid"])
    assert first["status"] == "approved", first
    second = _spend(ctx, "experiment", 3.0, "more ads", venture_id=ctx["vid"])
    assert second["status"] == "rejected" and "budget" in second["reason"]
    assert ctx["ledger"].balances()["experiment"] == 2500 - 300


def test_tokens_and_infra_unaffected(ctx):
    assert _spend(ctx, "tokens", 0.10, "llm")["status"] == "approved"
    assert _spend(ctx, "infra", 1.0, "domain")["status"] in ("approved", "pending")


def test_unknown_venture_rejected(ctx):
    out = _spend(ctx, "experiment", 1.0, "x", venture_id=999)
    assert out["status"] == "rejected" and "unknown venture" in out["reason"]