from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .store import Store

VENTURE_KINDS = ("digital_product", "bounty", "report", "micro_saas", "other")
VENTURE_STATUSES = ("researching", "validating", "building", "live", "paused", "dead")
ACTIVE_STATUSES = ("researching", "validating", "building", "live")

#: Legal transitions. Two extra edges beyond the happy-path chain in TASK 3 §2:
#: building->paused (the publish hand-off pauses after 2 failed check rounds)
#: and paused->building (resume after the human fixes the package; without it a
#: paused venture could never reach live because only building ventures are
#: scanned for packages and live requires an external product id).
TRANSITIONS: dict[str, set[str]] = {
    "researching": {"validating", "dead"},
    "validating": {"building", "dead"},
    "building": {"live", "paused", "dead"},
    "live": {"paused", "dead"},
    "paused": {"live", "building", "dead"},
    "dead": set(),
}

MIN_SCORE = 6.0
MIN_EVIDENCE_FILES = 2
MIN_DEATH_NOTE_CHARS = 80
UNVERIFIED_BANNER = "> UNVERIFIED"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60].strip("-")
    return slug or "venture"


def find_urls(text: str) -> set[str]:
    urls = set()
    for m in re.finditer(r"https?://\S+", text or ""):
        urls.add(m.group(0).rstrip(".,);:'\"!?]"))
    return urls


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


# ---------- reads (conn is enough) ----------
def get_venture(conn: sqlite3.Connection, venture_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM ventures WHERE id=?", (venture_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_venture_by_slug(conn: sqlite3.Connection, slug: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM ventures WHERE slug=?", (slug,)).fetchone()
    return _row_to_dict(row) if row else None


def list_ventures(conn: sqlite3.Connection, status: str | None = None) -> list[dict[str, Any]]:
    if status is None:
        rows = conn.execute("SELECT * FROM ventures ORDER BY id")
    else:
        rows = conn.execute("SELECT * FROM ventures WHERE status=? ORDER BY id",
                            (status,))
    return [_row_to_dict(r) for r in rows]


def active_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) c FROM ventures WHERE status IN"
        " ('researching','validating','building','live')").fetchone()
    return int(row["c"])


def venture_spent_cents(conn: sqlite3.Connection, venture_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(-SUM(delta_cents),0) s FROM ledger"
        " WHERE venture_id=? AND kind='expense'", (venture_id,)).fetchone()
    return int(row["s"])


def venture_income_cents(conn: sqlite3.Connection, venture_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(delta_cents),0) s FROM ledger"
        " WHERE venture_id=? AND kind IN ('income','refund')", (venture_id,)).fetchone()
    return int(row["s"])


def authorize_experiment_spend(conn: sqlite3.Connection, venture_id: int,
                               amount_cents: int, budget_cents: int) -> str | None:
    """Return a rejection reason, or None if the spend is allowed."""
    venture = get_venture(conn, venture_id)
    if venture is None:
        return f"unknown venture id: {venture_id}"
    if venture["status"] not in ("building", "live"):
        return (f"venture '{venture['slug']}' is {venture['status']}; "
                "experiment spending needs building or live")
    spent = venture_spent_cents(conn, venture_id)
    if spent + amount_cents > budget_cents:
        return (f"venture budget exceeded: already spent {spent}c, "
                f"request {amount_cents}c, budget {budget_cents}c")
    return None


# ---------- validation task linkage ----------
def validation_task_title(name: str) -> str:
    return f"[validate] {name}"


def find_validation_task(store: Store, name: str) -> dict[str, Any] | None:
    for t in store.list_tasks(limit=200):
        if t["title"] == validation_task_title(name):
            return t
    return None


def validation_output_clean(task: dict[str, Any]) -> bool:
    """A validation output counts if the task is done and its result file exists
    without the UNVERIFIED banner."""
    path = task.get("result_path")
    if not path:
        return False
    try:
        first = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    return bool(first) and not first[0].startswith(UNVERIFIED_BANNER)


def _check_evidence(root: Path, evidence_paths: list[str],
                    min_sources: int) -> tuple[list[str], str | None]:
    """Return (existing research files, error or None)."""
    if not evidence_paths or len(evidence_paths) < MIN_EVIDENCE_FILES:
        return [], (f"at least {MIN_EVIDENCE_FILES} research files are required, "
                    f"got {len(evidence_paths or [])}")
    research_dir = (Path(root) / "research").resolve()
    urls: set[str] = set()
    good: list[str] = []
    for rel in evidence_paths:
        p = (Path(root) / rel).resolve()
        if research_dir not in p.parents and p.parent != research_dir:
            return [], f"evidence must live under research/: {rel}"
        if not p.is_file():
            return [], f"evidence file does not exist: {rel}"
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            return [], f"evidence file unreadable: {rel}"
        first = text.splitlines()
        if first and first[0].startswith(UNVERIFIED_BANNER):
            return [], f"evidence carries an UNVERIFIED banner: {rel}"
        urls |= find_urls(text)
        good.append(rel)
    if len(urls) < min_sources:
        return [], (f"at least {min_sources} distinct source URLs required, "
                    f"found {len(urls)}")
    return good, None


DEVILS_ADVOCATE = (
    "Devil's-advocate validation for the venture below. Find reasons the demand "
    "may be weak or fake. List direct competitors with their prices. Estimate "
    "realistic monthly sales for the first 3 months. Cite every claim with a "
    "source URL; mark anything unverifiable as unverified.\n\nVenture: {name}\n"
    "Hypothesis: {hypothesis}"
)


def create_venture(store: Store, root: Path | str, *, name: str, kind: str, hypothesis: str,
                   score: float, evidence_paths: list[str], caller: str,
                   max_active: int = 3, min_sources: int = 3) -> dict[str, Any]:
    if kind not in VENTURE_KINDS:
        return {"status": "error", "reason": f"unknown venture kind: {kind}"}
    try:
        score = float(score)
    except (TypeError, ValueError):
        return {"status": "error", "reason": "score must be a number 0-10"}
    if not 0 <= score <= 10:
        return {"status": "error", "reason": "score must be between 0 and 10"}
    if score < MIN_SCORE:
        return {"status": "error",
                "reason": f"score {score} below the minimum {MIN_SCORE}"}
    if not name or not hypothesis:
        return {"status": "error", "reason": "name and hypothesis are required"}
    evidence, err = _check_evidence(Path(root), list(evidence_paths or []), min_sources)
    if err:
        return {"status": "error", "reason": err}
    if active_count(store.conn) >= max_active:
        return {"status": "error",
                "reason": f"too many active ventures (max {max_active})"}
    slug = slugify(name)
    try:
        cur = store.conn.execute(
            """INSERT INTO ventures(name,slug,kind,hypothesis,score,evidence)
               VALUES (?,?,?,?,?,?)""",
            (name, slug, kind, hypothesis, score, json.dumps(evidence)),
        )
        vid = cur.lastrowid
        assert vid is not None  # INSERT always yields a row id
        vid = int(vid)
    except sqlite3.IntegrityError:
        return {"status": "error", "reason": "a venture with this name/slug exists"}
    task = store.create_task(
        agent="scout", title=validation_task_title(name),
        prompt=DEVILS_ADVOCATE.format(name=name, hypothesis=hypothesis),
        priority=4, created_by=caller or "unknown")
    venture = get_venture(store.conn, vid)
    return {"status": "created", "venture": venture, "validation_task": task}


def _write_death_lesson(root: Path, venture: dict[str, Any]) -> str:
    lessons = Path(root) / "skills" / "lessons"
    lessons.mkdir(parents=True, exist_ok=True)
    path = lessons / f"{venture['id']}-{venture['slug']}.md"
    content = (
        "---\n"
        f"title: Lesson from dead venture {venture['name']}\n"
        "agents: [scout, builder, seller, treasurer, diplomat, chronicler]\n"
        f"tags: [lessons, {venture['kind']}]\n"
        f"venture_kind: {venture['kind']}\n"
        "---\n\n"
        f"# Lesson: {venture['name']} died\n\n"
        f"Kind: {venture['kind']} (score was {venture['score']}).\n\n"
        f"Why it died:\n\n{venture['death_note']}\n"
    )
    if not path.exists():
        path.write_text(content, encoding="utf-8")
    return str(path)


def update_venture(store: Store, root: Path | str, venture_id: int, status: str,
                   death_note: str = "") -> dict[str, Any]:
    """Move a venture. Illegal transitions raise ValueError; other problems
    return an error dict."""
    if status not in VENTURE_STATUSES:
        return {"status": "error", "reason": f"unknown status: {status}"}
    venture = get_venture(store.conn, venture_id)
    if venture is None:
        return {"status": "error", "reason": f"unknown venture id: {venture_id}"}
    if status == venture["status"]:
        return {"status": "ok", "venture": venture}
    if status not in TRANSITIONS[venture["status"]]:
        raise ValueError(
            f"illegal transition {venture['status']} -> {status}")
    if status == "dead" and (not death_note or len(death_note) < MIN_DEATH_NOTE_CHARS):
        return {"status": "error",
                "reason": f"death_note of at least {MIN_DEATH_NOTE_CHARS} "
                          "characters is required"}
    if status == "building":
        task = find_validation_task(store, venture["name"])
        if (task is None or task["status"] != "done"
                or not validation_output_clean(task)):
            return {"status": "error",
                    "reason": "building needs a finished validation research file "
                              "without the UNVERIFIED banner"}
    if status == "live" and not venture["external_product_id"]:
        return {"status": "error",
                "reason": "live needs an external_product_id (human CLI set-product)"}
    store.conn.execute(
        """UPDATE ventures SET status=?, death_note=?,
           updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""",
        (status, death_note if status == "dead" else venture["death_note"],
         venture_id),
    )
    venture = get_venture(store.conn, venture_id)
    assert venture is not None  # just updated above; the row exists
    lesson_path = ""
    if status == "dead":
        try:
            lesson_path = _write_death_lesson(Path(root), venture)
        except OSError as e:
            return {"status": "error",
                    "reason": f"dead but lesson file failed: {e}"}
    out = {"status": "ok", "venture": venture}
    if lesson_path:
        out["lesson_path"] = lesson_path
    return out


def set_external_product(store: Store, root: Path | str, venture_id: int,
                           external_product_id: str) -> dict[str, Any]:
    venture = get_venture(store.conn, venture_id)
    if venture is None:
        return {"status": "error", "reason": f"unknown venture id: {venture_id}"}
    if not external_product_id:
        return {"status": "error", "reason": "external product id is required"}
    store.conn.execute(
        """UPDATE ventures SET external_product_id=?,
           updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""",
        (external_product_id, venture_id))
    venture = get_venture(store.conn, venture_id)
    assert venture is not None  # just updated above; the row exists
    if venture["status"] in ("building", "paused"):
        try:
            return update_venture(store, root, venture_id, "live")
        except ValueError as e:
            return {"status": "error", "reason": str(e)}
    if venture["status"] != "live":
        return {"status": "error",
                "reason": f"venture is {venture['status']}; set-product moves "
                          "building/paused ventures to live"}
    return {"status": "ok", "venture": venture}


def auto_advance(store: Store, root: Path | str) -> list[str]:
    """Move researching ventures with a clean finished validation to validating."""
    events = []
    for venture in list_ventures(store.conn, "researching"):
        task = find_validation_task(store, venture["name"])
        if (task is not None and task["status"] == "done"
                and validation_output_clean(task)):
            try:
                update_venture(store, root, venture["id"], "validating")
            except ValueError:
                continue
            events.append(f"venture #{venture['id']} auto-validated")
    return events
