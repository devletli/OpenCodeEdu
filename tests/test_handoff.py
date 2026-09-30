from datetime import UTC, datetime

from kiraci import ventures
from kiraci.config import Config
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.orchestrator import Orchestrator
from kiraci.store import Store
from kiraci.testing import FakeRunner

NOW = datetime(2026, 1, 5, 13, 0, tzinfo=UTC)
URLS = ("https://example.com/a", "https://example.com/b", "https://example.com/c")
DISCLOSURE = ("Created and maintained by an AI agent system "
              "operated by the store owner.")


def make_orch(tmp_path):
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    store = Store(conn)
    orch = Orchestrator(root=tmp_path, store=store, ledger=ledger,
                        config=Config(), runner=FakeRunner(), clock=lambda: NOW)
    return orch, store


def make_building(store, root, name="Gadget"):
    (root / "research").mkdir(exist_ok=True)
    (root / "research" / "a.md").write_text(
        "x\n\n- " + "\n- ".join(URLS[:2]) + "\n", encoding="utf-8")
    (root / "research" / "b.md").write_text(f"y {URLS[2]}\n", encoding="utf-8")
    r = ventures.create_venture(
        store, root, name=name, kind="digital_product", hypothesis="Sells.",
        score=8.0, evidence_paths=["research/a.md", "research/b.md"],
        caller="brain")
    assert r["status"] == "created", r
    vid = r["venture"]["id"]
    task = ventures.find_validation_task(store, name)
    clean = root / "research" / "validation.md"
    clean.write_text(f"ok {URLS[0]}\n", encoding="utf-8")
    store.set_status(task["id"], "done", result_path=str(clean))
    assert ventures.update_venture(store, root, vid, "validating")["status"] == "ok"
    assert ventures.update_venture(store, root, vid, "building")["status"] == "ok"
    return vid


def write_package(root, slug, *, broken=False):
    d = root / "products" / slug
    (d / "deliverable").mkdir(parents=True, exist_ok=True)
    (d / "listing.md").write_text(
        "---\ntitle: Gadget\nprice_eur: 9.99\ntags: [g]\n---\n"
        "A gadget.\n" + DISCLOSURE + "\n",
        encoding="utf-8")
    if not broken:
        (d / "README.md").write_text("# Gadget\n", encoding="utf-8")
    (d / "CHECKLIST.md").write_text("- [x] Done\n", encoding="utf-8")
    (d / "LICENSE.txt").write_text("Rights.\n", encoding="utf-8")
    (d / "deliverable" / "g.zip").write_bytes(b"0" * 10)
    return d


def test_merged_package_files_publish_task_once(tmp_path, monkeypatch):
    monkeypatch.delenv("KIRACI_OWNER_NAME", raising=False)
    orch, store = make_orch(tmp_path)
    make_building(store, tmp_path)
    write_package(tmp_path, "gadget")
    assert orch._publish_handoff(NOW) != []
    found = [t for t in store.list_human_tasks("open")
             if t["dedupe_key"] == "publish:gadget"]
    assert len(found) == 1
    assert found[0]["kind"] == "logged_in_action"
    assert (tmp_path / "products" / "gadget" / "dist" / "gadget.zip").exists()


def test_set_product_goes_live(tmp_path, monkeypatch):
    monkeypatch.delenv("KIRACI_OWNER_NAME", raising=False)
    orch, store = make_orch(tmp_path)
    vid = make_building(store, tmp_path)
    write_package(tmp_path, "gadget")
    orch._publish_handoff(NOW)
    out = ventures.set_external_product(store, tmp_path, vid, "prod_9")
    assert out["status"] == "ok"
    assert ventures.get_venture(store.conn, vid)["status"] == "live"


def test_two_failed_rounds_pause_venture(tmp_path, monkeypatch):
    monkeypatch.delenv("KIRACI_OWNER_NAME", raising=False)
    orch, store = make_orch(tmp_path)
    vid = make_building(store, tmp_path)
    write_package(tmp_path, "gadget", broken=True)
    orch._publish_handoff(NOW)  # round 1 -> fix task queued
    fixes = [t for t in store.list_tasks("pending")
             if t["title"] == "[venture:gadget] fix product package"]
    assert len(fixes) == 1
    store.set_status(fixes[0]["id"], "done")
    orch._publish_handoff(NOW)  # round 2 -> fix task queued again
    fixes = [t for t in store.list_tasks("pending")
             if t["title"] == "[venture:gadget] fix product package"]
    assert len(fixes) == 1
    store.set_status(fixes[0]["id"], "done")
    events = orch._publish_handoff(NOW)  # round 3 -> paused
    assert any("paused" in e for e in events)
    assert ventures.get_venture(store.conn, vid)["status"] == "paused"
    journal = tmp_path / "journal" / "2026-01-05.md"
    assert "paused" in journal.read_text(encoding="utf-8")
