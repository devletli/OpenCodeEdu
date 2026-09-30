import pytest

from kiraci import ventures
from kiraci.db import connect
from kiraci.store import Store

URLS = ("https://example.com/demand-a", "https://example.com/rival-b",
        "https://example.com/price-c")


@pytest.fixture
def setup(tmp_path):
    research = tmp_path / "research"
    research.mkdir()
    (research / "a.md").write_text(
        "Demand is real.\n\n- " + "\n- ".join(URLS[:2]) + "\n", encoding="utf-8")
    (research / "b.md").write_text(
        f"More proof: {URLS[2]}\n", encoding="utf-8")
    store = Store(connect(":memory:"))
    return store, tmp_path


def make(store, root, name="Widget Pack", **kw):
    args = {"kind": "digital_product", "hypothesis": "People pay for widgets.",
            "score": 7.5, "evidence_paths": ["research/a.md", "research/b.md"],
            "caller": "brain"}
    args.update(kw)
    args["name"] = name
    return ventures.create_venture(store, root, **args)


def test_creation_rejections(setup):
    store, root = setup
    assert make(store, root, score=5.9)["status"] == "error"
    assert make(store, root, name="E1",
                evidence_paths=["research/a.md"])["status"] == "error"
    (root / "research" / "thin.md").write_text("no urls here\n", encoding="utf-8")
    assert make(store, root, name="E2",
                evidence_paths=["research/a.md", "research/thin.md"])["status"] == "error"
    (root / "research" / "banner.md").write_text(
        "> UNVERIFIED: fewer than 3 sources\ntext\n", encoding="utf-8")
    assert make(store, root, name="E3",
                evidence_paths=["research/a.md", "research/banner.md"])["status"] == "error"
    assert make(store, root, kind="casino")["status"] == "error"


def test_fourth_active_venture_rejected(setup):
    store, root = setup
    for i in range(3):
        r = make(store, root, name=f"V{i}")
        assert r["status"] == "created", r
    assert make(store, root, name="V3")["status"] == "error"


def test_duplicate_slug_rejected(setup):
    store, root = setup
    assert make(store, root)["status"] == "created"
    assert make(store, root)["status"] == "error"


def test_validation_task_queued_on_creation(setup):
    store, root = setup
    r = make(store, root)
    assert r["status"] == "created"
    task = ventures.find_validation_task(store, "Widget Pack")
    assert task is not None and task["agent"] == "scout"
    assert task["title"] == "[validate] Widget Pack"


def _to_building(store, root, name="Widget Pack"):
    r = make(store, root, name=name)
    vid = r["venture"]["id"]
    task = ventures.find_validation_task(store, name)
    clean = root / "research" / "validation.md"
    clean.write_text(f"Validation holds: {URLS[0]}\n", encoding="utf-8")
    store.set_status(task["id"], "done", result_path=str(clean))
    assert ventures.update_venture(store, root, vid, "validating")["status"] == "ok"
    assert ventures.update_venture(store, root, vid, "building")["status"] == "ok"
    return vid


def test_building_needs_validation_file(setup):
    store, root = setup
    r = make(store, root)
    vid = r["venture"]["id"]
    assert ventures.update_venture(store, root, vid, "validating")["status"] == "ok"
    assert ventures.update_venture(store, root, vid, "building")["status"] == "error"
    assert ventures.get_venture(store.conn, vid)["status"] == "validating"


def test_illegal_transitions_raise(setup):
    store, root = setup
    r = make(store, root)
    vid = r["venture"]["id"]
    with pytest.raises(ValueError):
        ventures.update_venture(store, root, vid, "building")
    with pytest.raises(ValueError):
        ventures.update_venture(store, root, vid, "live")


def test_dead_needs_long_note_and_writes_lesson(setup):
    store, root = setup
    vid = _to_building(store, root)
    assert ventures.update_venture(store, root, vid, "dead",
                                   death_note="too short")["status"] == "error"
    note = ("Nobody wanted paid widget packs: three much cheaper rivals, no forum "
            "demand, and our price could not cover the provider fees at all.")
    assert len(note) >= 80
    out = ventures.update_venture(store, root, vid, "dead", death_note=note)
    assert out["status"] == "ok"
    venture = ventures.get_venture(store.conn, vid)
    assert venture["status"] == "dead"
    lesson = root / "skills" / "lessons" / f"{vid}-widget-pack.md"
    assert lesson.exists() and note[:40] in lesson.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        ventures.update_venture(store, root, vid, "paused")


def test_live_needs_external_product_id(setup):
    store, root = setup
    vid = _to_building(store, root)
    assert ventures.update_venture(store, root, vid, "live")["status"] == "error"
    out = ventures.set_external_product(store, root, vid, "prod_123")
    assert out["status"] == "ok"
    assert ventures.get_venture(store.conn, vid)["status"] == "live"


def test_auto_advance(setup):
    store, root = setup
    r = make(store, root)
    vid = r["venture"]["id"]
    assert ventures.auto_advance(store, root) == []
    task = ventures.find_validation_task(store, "Widget Pack")
    clean = root / "research" / "validation.md"
    clean.write_text(f"Validation holds: {URLS[0]}\n", encoding="utf-8")
    store.set_status(task["id"], "done", result_path=str(clean))
    events = ventures.auto_advance(store, root)
    assert len(events) == 1
    assert ventures.get_venture(store.conn, vid)["status"] == "validating"
