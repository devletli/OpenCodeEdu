import gzip
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from kiraci.backup import run_backup
from kiraci.cli import cmd_restore
from kiraci.config import Config
from kiraci.db import connect
from kiraci.ledger import Ledger
from kiraci.orchestrator import Orchestrator
from kiraci.store import Store
from kiraci.testing import FakeRunner
from kiraci.verify import verify_ledger


def fresh_ledger(tmp_path, name="t.db"):
    conn = connect(str(tmp_path / name))
    Ledger(conn).init_genesis()
    return conn


def test_backup_creates_integrity_clean_gzip(tmp_path):
    conn = fresh_ledger(tmp_path)
    config = Config(backup={"keep_daily": 14, "keep_weekly": 8})
    res = run_backup(conn, tmp_path, config,
                     now=datetime(2026, 10, 1, 22, 30, tzinfo=UTC))
    assert res["status"] == "ok"
    gz = Path(res["path"])
    assert gz.exists() and gz.name == "kiraci-20261001.db.gz"
    with gzip.open(gz, "rb") as f:
        data = f.read()
    assert b"ledger" in data
    conn.close()


def make_gz(directory: Path, day: str) -> Path:
    p = directory / f"kiraci-{day}.db.gz"
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wb") as f:
        f.write(b"x")
    return p


def test_rotation_keeps_daily_and_weekly(tmp_path):
    directory = tmp_path / "data" / "backups"
    # 20 recent dailies incl. 3 Sundays
    for d in range(1, 21):
        day = f"2026-09-{d:02d}"
        dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
        make_gz(directory, dt.strftime("%Y%m%d"))
    config = Config(backup={"keep_daily": 14, "keep_weekly": 8})
    res = run_backup(fresh_ledger(tmp_path, "x.db"), tmp_path, config,
                     now=datetime(2026, 9, 21, 22, 30, tzinfo=UTC))
    assert res["status"] == "ok"
    kept = sorted(p.stem for p in directory.glob("kiraci-*.db.gz"))
    sundays = [k for k in kept
               if datetime.strptime(k.removeprefix("kiraci-").removesuffix(".db"),
                                    "%Y%m%d").replace(tzinfo=UTC).weekday() == 6]
    dailies = [k for k in kept if k not in sundays]
    assert len(dailies) <= 14
    assert len(sundays) >= 1  # weekly copies are kept separately


def test_verify_detects_dropped_trigger(tmp_path):
    conn = fresh_ledger(tmp_path)
    conn.execute("DROP TRIGGER ledger_no_update")
    findings = verify_ledger(conn)
    assert any("trigger" in f for f in findings)


def test_verify_detects_tampered_entry(tmp_path):
    conn = fresh_ledger(tmp_path)
    conn.execute("DROP TRIGGER ledger_no_update")
    conn.execute("DROP TRIGGER ledger_no_delete")
    conn.execute("UPDATE ledger SET delta_cents=123 WHERE id=1")
    findings = verify_ledger(conn)
    assert any("hash chain" in f for f in findings)


def test_verify_detects_executed_approval_without_entry(tmp_path):
    conn = fresh_ledger(tmp_path)
    conn.execute(
        "INSERT INTO approvals(agent,bucket,amount_cents,purpose,tier,status)"
        " VALUES ('brain','infra',100,'x','auto','executed')")
    findings = verify_ledger(conn)
    assert any("no entry" in f or "lacks" in f for f in findings)


def test_verify_detects_unexplained_expense(tmp_path):
    conn = fresh_ledger(tmp_path)
    conn.execute("DROP TRIGGER ledger_no_update")
    conn.execute("DROP TRIGGER ledger_no_delete")
    conn.execute(
        "INSERT INTO ledger(ts,kind,bucket,delta_cents,agent,note,hash)"
        " VALUES ('2026-10-01T00:00:00Z','expense','infra',-100,'agent','',"
        "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')")
    findings = verify_ledger(conn)
    assert any("unexplained expense" in f for f in findings)


def test_verify_detects_negative_bucket_without_reconciliation(tmp_path):
    conn = fresh_ledger(tmp_path)
    conn.execute("DROP TRIGGER ledger_no_update")
    conn.execute("DROP TRIGGER ledger_no_delete")
    conn.execute(
        "INSERT INTO ledger(ts,kind,bucket,delta_cents,agent,note,hash)"
        " VALUES ('2026-10-01T00:00:00Z','expense','infra',-99999,'agent','',"
        "'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')")
    findings = verify_ledger(conn)
    assert any("negative without reconciliation" in f for f in findings)


def test_verify_detects_duplicate_ref(tmp_path):
    # The UNIQUE constraint normally makes duplicates impossible; verify is
    # defense-in-depth for restored/hand-built databases without it.
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT,
            bucket TEXT, delta_cents INTEGER, agent TEXT, ref TEXT,
            note TEXT NOT NULL DEFAULT '', venture_id INTEGER, hash TEXT);
        CREATE TABLE approvals (id INTEGER PRIMARY KEY, entry_id INTEGER,
                                status TEXT, amount_cents INTEGER);
        CREATE TABLE payments (id INTEGER PRIMARY KEY, order_id TEXT,
                               recorded_cents INTEGER, status TEXT);
    """)
    for i, h in enumerate(("aaaa", "bbbb")):
        conn.execute(
            "INSERT INTO ledger(ts,kind,bucket,delta_cents,agent,ref,note,hash)"
            f" VALUES ('2026-10-01T00:00:0{i}Z','income','experiment',100,'a',"
            "'dup','', ?)", (h + "0" * 60,))
    findings = verify_ledger(conn)
    assert any("duplicate ref" in f for f in findings)


def test_verify_finding_pauses_and_notifies(tmp_path, monkeypatch):
    for var in ("KIRACI_MODEL_STRONG", "KIRACI_MODEL_MID", "KIRACI_MODEL_CHEAP"):
        monkeypatch.setenv(var, "test/model")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    conn = fresh_ledger(tmp_path)
    conn.execute("DROP TRIGGER ledger_no_update")
    orch = Orchestrator(root=tmp_path, store=Store(conn), ledger=Ledger(conn),
                        config=Config(models={}, costs={}, limits={}),
                        runner=FakeRunner())
    summary = orch._verify_job(datetime.now(UTC))
    assert "findings" in summary and "PAUSED" in summary
    assert (tmp_path / "data" / "PAUSE").exists()
    inbox = (tmp_path / "HUMAN_INBOX.md").read_text(encoding="utf-8")
    assert "FAILED" in inbox


def test_restore_requires_kill_and_stale_heartbeat(tmp_path, monkeypatch):
    monkeypatch.setenv("KIRACI_DB", str(tmp_path / "t.db"))
    conn = fresh_ledger(tmp_path)
    store = Store(conn)
    store.kv_set("last_tick", datetime.now(UTC).isoformat())  # fresh heartbeat
    res = cmd_restore(tmp_path, tmp_path / "backup.db.gz", yes=True)
    assert res["status"] == "refused"  # no KILL file
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "KILL").touch()
    res2 = cmd_restore(tmp_path, tmp_path / "backup.db.gz", yes=True)
    assert res2["status"] == "refused"  # heartbeat too fresh
    assert "2 minutes" in res2["reason"] or "heartbeat" in res2["reason"]


def test_restore_installs_backup_and_keeps_old_db(tmp_path, monkeypatch):
    monkeypatch.setenv("KIRACI_DB", str(tmp_path / "t.db"))
    conn = fresh_ledger(tmp_path)
    store = Store(conn)
    config = Config()
    res = run_backup(conn, tmp_path, config,
                     now=datetime(2026, 10, 1, 22, 30, tzinfo=UTC))
    assert res["status"] == "ok"
    # make the current db diverge from the backup
    Ledger(conn).request_spend("builder", "infra", 100, "after backup")
    store.kv_set("last_tick", "2020-01-01T00:00:00Z")  # stale heartbeat
    conn.close()  # release the file before the restore moves it
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "KILL").touch()
    out = cmd_restore(tmp_path, Path(res["path"]), yes=True)
    assert out["status"] == "restored"
    assert Path(out["kept_old_db"]).exists()
    # the restored db no longer contains the post-backup expense
    conn2 = connect(str(tmp_path / "t.db"))
    rows = conn2.execute("SELECT COUNT(*) c FROM ledger WHERE note='after backup'"
                         ).fetchone()
    assert rows["c"] == 0
    conn2.close()


def test_restore_refuses_unhealthy_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("KIRACI_DB", str(tmp_path / "t.db"))
    fresh_ledger(tmp_path)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "KILL").touch()
    bad = tmp_path / "bad.db.gz"
    with gzip.open(bad, "wb") as f:
        f.write(b"this is not a database")
    Store(connect(str(tmp_path / "t.db"))).kv_set(
        "last_tick", "2020-01-01T00:00:00Z")
    out = cmd_restore(tmp_path, bad, yes=True)
    assert out["status"] == "refused"
    assert "verification" in out["reason"]