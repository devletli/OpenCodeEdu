import pytest

from kiraci.db import connect
from kiraci.store import ORCHESTRATOR, Store


@pytest.fixture
def store():
    return Store(connect(":memory:"))


def _human(store, **kw):
    base = {"kind": "login", "title": "Need login",
            "instructions": "Do step 1, then step 2.",
            "dedupe_key": "k", "created_by": "scout"}
    base.update(kw)
    return store.add_human_task(**base)


def test_invalid_kind_rejected(store):
    r = _human(store, kind="ask_anything", dedupe_key="a")
    assert r["status"] == "error"
    assert "logins/account" in r["reason"]


def test_duplicate_dedupe_key_returns_same_task(store):
    r1 = _human(store, dedupe_key="same")
    r2 = _human(store, dedupe_key="same", title="Different title")
    assert r1["status"] == "created"
    assert r2["status"] == "exists"
    assert r2["task"]["id"] == r1["task"]["id"]


def test_fourth_agent_human_task_in_one_day_rejected(store):
    for i in range(3):
        r = _human(store, dedupe_key=f"d{i}")
        assert r["status"] == "created", r
    r = _human(store, dedupe_key="d3")
    assert r["status"] == "error"
    assert "batch" in r["reason"]
    # orchestrator's own tasks (e.g. red approvals) are exempt
    r = _human(store, dedupe_key="orc", created_by=ORCHESTRATOR,
               kind="red_tier_approval")
    assert r["status"] == "created", r


def test_secret_looking_text_rejected(store):
    assert _human(store, dedupe_key="s1",
                  instructions="use key sk-proj-abcdefgh12345678")["status"] == "error"
    assert _human(store, dedupe_key="s2",
                  instructions="auth Bearer abcdefgh12345678")["status"] == "error"
    assert _human(store, dedupe_key="s3",
                  instructions="card 4111111111111111")["status"] == "error"
    assert _human(store, dedupe_key="s4",
                  instructions="set password: hunter2-now")["status"] == "error"


def test_resolving_unblocks_dependent_tasks(store):
    t = store.create_task(agent="scout", title="Blocked research",
                          prompt="do it", created_by="brain")
    assert t["status"] == "created"
    h = store.add_human_task(kind="login", title="Need login",
                             instructions="Log in at https://example.com.",
                             dedupe_key="blk", created_by="scout",
                             blocks_task_id=t["task_id"])
    assert h["status"] == "created"
    assert store.get_task(t["task_id"])["status"] == "blocked"
    assert store.resolve_human_task(h["task"]["id"], note="done")["status"] == "done"
    task = store.get_task(t["task_id"])
    assert task["status"] == "pending" and task["blocked_on"] is None


def test_create_task_for_brain_rejected(store):
    r = store.create_task(agent="brain", title="Think", prompt="think",
                          created_by="brain")
    assert r["status"] == "error"


def test_max_10_pending(store):
    for i in range(10):
        r = store.create_task(agent="scout", title=f"T{i}", prompt="p",
                              created_by="brain")
        assert r["status"] == "created", r
    r = store.create_task(agent="scout", title="T10", prompt="p",
                          created_by="brain")
    assert r["status"] == "error" and "10" in r["reason"]


def test_title_and_prompt_limits(store):
    assert store.create_task(agent="scout", title="x" * 121, prompt="p",
                             created_by="b")["status"] == "error"
    assert store.create_task(agent="scout", title="t", prompt="p" * 4001,
                             created_by="b")["status"] == "error"


def test_blocks_unknown_task_rejected(store):
    r = store.add_human_task(kind="login", title="t", instructions="i" * 10,
                             dedupe_key="x", created_by="scout", blocks_task_id=999)
    assert r["status"] == "error"
