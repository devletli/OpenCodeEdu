import os

os.environ["KIRACI_DB"] = ":memory:"  # before mcp_server builds its ledger

import pytest

from kiraci import mcp_server, ventures
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
    mcp_server._ledger = Ledger(connect(":memory:"))
    mcp_server._ledger.init_genesis()
    store = Store(mcp_server._ledger.conn)
    r = ventures.create_venture(
        store, tmp_path, name="Gadget", kind="digital_product",
        hypothesis="Sells.", score=8.0,
        evidence_paths=["research/a.md", "research/b.md"], caller="brain")
    assert r["status"] == "created", r
    return {"store": store, "ledger": mcp_server._ledger, "root": tmp_path,
            "vid": r["venture"]["id"]}


def _to_building(ctx):
    store, root, vid = ctx["store"], ctx["root"], ctx["vid"]
    task = ventures.find_validation_task(store, "Gadget")
    clean = root / "research" / "validation.md"
    clean.write_text(f"ok {URLS[0]}\n", encoding="utf-8")
    store.set_status(task["id"], "done", result_path=str(clean))
    assert ventures.update_venture(store, root, vid, "validating")["status"] == "ok"
    assert ventures.update_venture(store, root, vid, "building")["status"] == "ok"


def test_experiment_spend_without_venture_rejected(ctx):
    out = mcp_server.request_spend("builder", "experiment", 1.0, "ads")
    assert out["status"] == "rejected" and "venture_id" in out["reason"]


def test_researching_venture_rejected(ctx):
    out = mcp_server.request_spend("builder", "experiment", 1.0, "ads",
                                      venture_id=ctx["vid"])
    assert out["status"] == "rejected" and "building or live" in out["reason"]


def test_budget_cap_across_spends(ctx):
    _to_building(ctx)
    first = mcp_server.request_spend("builder", "experiment", 3.0, "ads",
                                        venture_id=ctx["vid"])
    assert first["status"] == "approved", first
    second = mcp_server.request_spend("builder", "experiment", 3.0, "more ads",
                                         venture_id=ctx["vid"])
    assert second["status"] == "rejected" and "budget" in second["reason"]
    assert ctx["ledger"].balances()["experiment"] == 2500 - 300


def test_tokens_and_infra_unaffected(ctx):
    assert mcp_server.request_spend("scout", "tokens", 0.10, "llm")["status"] \
        == "approved"
    assert mcp_server.request_spend("builder", "infra", 1.0, "domain")["status"] \
        in ("approved", "pending")


def test_unknown_venture_rejected(ctx):
    out = mcp_server.request_spend("builder", "experiment", 1.0, "x",
                                      venture_id=999)
    assert out["status"] == "rejected" and "unknown venture" in out["reason"]
