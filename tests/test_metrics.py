from datetime import UTC, datetime, timedelta

from kiraci.config import Config
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.metrics import (
    genesis_ts,
    metrics_filename,
    write_metrics,
)
from kiraci.orchestrator import Orchestrator, genesis_age_days
from kiraci.store import Store
from kiraci.testing import FakeRunner

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def seeded():
    conn = connect(":memory:")
    ledger = Ledger(conn)
    ledger.init_genesis()
    store = Store(conn)
    ledger.record_income(2000, "seed1", agent="webhook", venture_id=None)
    ledger.request_spend("scout", "tokens", 50, "llm")
    conn.execute(
        """INSERT INTO ventures(name,slug,kind,hypothesis,score,evidence,status,
                                external_product_id)
           VALUES ('Gadget','gadget','digital_product','Sells.',8.0,'[]',
                   'live','prod_1')""")
    ledger.record_income(2000, "seed2", agent="payments", venture_id=1)
    ledger.request_spend("builder", "infra", 200, "domain", venture_id=1)
    conn.execute(
        """INSERT INTO payments(provider,order_id,product_id,venture_id,currency,
                                gross_cents,recorded_cents,status)
           VALUES ('testpay','o1','prod_1',1,'EUR',1199,900,'recorded')""")
    conn.execute(
        """INSERT INTO payments(provider,order_id,product_id,venture_id,currency,
                                gross_cents,recorded_cents,status)
           VALUES ('testpay','o2','prod_1',1,'USD',500,0,'fx_unhandled')""")
    store.log_run(agent="scout", model="m", status="ok")
    store.log_run(agent="scout", model="m", status="ok")
    store.log_run(agent="builder", model="m", est_cost_cents=3, status="ok")
    store.add_human_task(kind="login", title="Need login", instructions="Do it.",
                         dedupe_key="h1", created_by="scout")
    h = store.add_human_task(kind="login", title="Other", instructions="Do it.",
                             dedupe_key="h2", created_by="scout")
    store.resolve_human_task(h["task"]["id"])
    conn.execute(
        """INSERT INTO ventures(name,slug,kind,hypothesis,score,evidence,status,
                                death_note)
           VALUES ('Dead Pack','dead-pack','report','Maybe.',7.0,'[]','dead',
                   'Nobody wanted it, and the numbers below prove it conclusively.')""")
    return store, ledger


def test_numbers_match_seeded_db(tmp_path):
    store, ledger = seeded()
    path = write_metrics(store, ledger, tmp_path, NOW)
    assert path.name == metrics_filename(NOW)
    text = path.read_text(encoding="utf-8")
    # genesis 10000 + income (1600+1600 ex-owner... 2000+2000 split minus owner)
    # -50 tokens -200 infra = check exact total below
    assert f"{ledger.total_balance() / 100:.2f}" in text
    assert "ROI 10.00" in text  # venture 1: ledger income 2000 / spend 200
    assert "Dead Pack" in text
    assert "fx_unhandled: 1" in text
    assert "builder: 1 runs" in text
    assert "Open: 1, closed: 1" in text


def test_day60_wind_down_text():
    conn = connect(":memory:")
    old = (datetime.now(UTC) - timedelta(days=61)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO ledger(kind,bucket,delta_cents,agent,ref,note,ts)"
        " VALUES ('fund','infra',2000,'system','g:i','',?)", (old,))
    conn.execute(
        "INSERT INTO ledger(kind,bucket,delta_cents,agent,note)"
        " VALUES ('expense','infra',-1900,'t','burn')")
    assert genesis_ts(conn) == old
    assert genesis_age_days(conn, datetime.now(UTC)) == 61
    orch = Orchestrator(root=".", store=Store(conn), ledger=Ledger(conn),
                        config=Config(), runner=FakeRunner(), clock=lambda: NOW)
    text = orch._wind_down_instruction(datetime.now(UTC))
    assert "WIND-DOWN" in text


def test_day90_job_triggers_exactly_once(tmp_path, monkeypatch):
    for var in ("KIRACI_MODEL_STRONG", "KIRACI_MODEL_MID", "KIRACI_MODEL_CHEAP"):
        monkeypatch.setenv(var, "test/model")
    conn = connect(":memory:")
    old = (datetime.now(UTC) - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO ledger(kind,bucket,delta_cents,agent,ref,note,ts)"
        " VALUES ('fund','infra',10000,'system','g:i','',?)", (old,))
    store = Store(conn)
    runner = FakeRunner(outputs={"brain": ["Break-even reached: numbers."],
                                 "chronicler": ["Retro: it worked."]})
    orch = Orchestrator(root=tmp_path, store=store, ledger=Ledger(conn),
                        config=Config(
                            models={"brain": "strong", "chronicler": "cheap"},
                            costs={}, limits={"run_timeout_seconds": 60}),
                        runner=runner, clock=lambda: datetime.now(UTC))
    now = datetime.now(UTC)
    assert orch._day90(now, False) == "day90 review written"
    path = tmp_path / "journal" / "day-90-review.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "## Brain" in text and "## Chronicler" in text
    assert orch._day90(now, False) is None
