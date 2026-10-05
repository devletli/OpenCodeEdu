"""IPC broker: agents never touch the database.

One BrokerSession runs in a thread in the orchestrator process for the
lifetime of one agent run. It polls the run's `requests/` directory, executes
each call against the real Ledger/Store/ventures code over its OWN database
connection and writes the response. The calling identity is ALWAYS the agent
of the session (fixes the spoofing threat): for request_spend the ledger agent
is the session agent; for queue tools created_by/caller is the session agent.

Request/response hardening: only regular files (lstat, O_NOFOLLOW where
available), max 64 KB, valid JSON object with nesting depth <= 5, non-.json
files ignored, file content never echoed in errors, at most 200 requests per
run. Responses are informational; authoritative state lives only in the
database. Processed requests are deleted.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import threading
from pathlib import Path
from typing import Any

from . import permissions, ventures
from .config import Config, load_config
from .ledger import Ledger
from .store import Store

MAX_REQUEST_BYTES = 64 * 1024
MAX_REQUESTS_PER_RUN = 200
MAX_JSON_DEPTH = 5
POLL_INTERVAL_S = 0.1

#: Human-only operations. These have NO broker handler at all; the test suite
#: asserts that none of these names can ever be invoked through the broker.
HUMAN_ONLY_OPERATIONS = frozenset({
    "ledger_approve", "ledger_reject", "ledger_record_income",
    "ledger_record_refund", "ledger_init_genesis", "ledger_restore",
    "queue_resolve_human_task", "queue_dismiss_human_task",
    "queue_set_product", "queue_restore",
})


def _depth_ok(obj: Any, depth: int = 0) -> bool:
    if depth > MAX_JSON_DEPTH:
        return False
    if isinstance(obj, dict):
        return all(
            isinstance(k, str) and _depth_ok(v, depth + 1) for k, v in obj.items()
        )
    if isinstance(obj, list):
        return all(_depth_ok(v, depth + 1) for v in obj)
    return True


def _read_request(path: Path) -> dict[str, Any]:
    """Read and validate one request file. Raises ValueError on any problem.

    Error messages never contain file content.
    """
    try:
        st = path.lstat()
    except OSError as e:
        raise ValueError("request unreadable") from e
    if not stat.S_ISREG(st.st_mode):
        raise ValueError("request is not a regular file")
    if st.st_size > MAX_REQUEST_BYTES:
        raise ValueError("request too large")
    flags = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, os.O_RDONLY | flags)
    except OSError as e:
        raise ValueError("request unreadable") from e
    try:
        st2 = os.fstat(fd)
        if not stat.S_ISREG(st2.st_mode):
            raise ValueError("request is not a regular file")
        data = os.read(fd, MAX_REQUEST_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_REQUEST_BYTES:
        raise ValueError("request too large")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise ValueError("request is not valid JSON") from e
    if not isinstance(payload, dict) or not _depth_ok(payload):
        raise ValueError("request must be a shallow JSON object")
    server = payload.get("server")
    tool = payload.get("tool")
    args = payload.get("args")
    if not isinstance(server, str) or not isinstance(tool, str):
        raise ValueError("request must name a server and a tool")  # noqa: TRY004
    if args is not None and not isinstance(args, dict):
        raise ValueError("args must be an object")
    return {"server": server, "tool": tool, "args": args or {}}


class BrokerSession:
    """Executes whitelisted tool calls for one agent run, with real identity."""

    def __init__(self, run_id: str, agent: str, ipc_dir: Path, *,
                 root: Path | str | None = None,
                 ledger: Ledger | None = None, store: Store | None = None,
                 connect_fn: Any = None, config: Config | None = None) -> None:
        self.run_id = str(run_id)
        self.agent = agent
        self.ipc_dir = Path(ipc_dir)
        self.root = Path(root) if root else Path.cwd()
        self._ledger = ledger
        self._store = store
        self._connect_fn = connect_fn
        self._config = config
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._handled = 0

    # ---------- lifecycle ----------
    def start(self) -> None:
        requests = self.ipc_dir / "requests"
        responses = self.ipc_dir / "responses"
        requests.mkdir(parents=True, exist_ok=True)
        responses.mkdir(parents=True, exist_ok=True)
        marker = self.ipc_dir / "run.json"
        marker.write_text(
            json.dumps({"run_id": self.run_id, "agent": self.agent}),
            encoding="utf-8")
        self._thread = threading.Thread(
            target=self._loop, name=f"kiraci-broker-{self.run_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def cleanup(self) -> None:
        """Stop the session and delete the whole IPC directory."""
        self.stop()
        shutil.rmtree(self.ipc_dir, ignore_errors=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._poll_once()
            self._stop.wait(POLL_INTERVAL_S)
        self._poll_once()  # drain whatever arrived before the stop

    def _poll_once(self) -> None:
        requests = self.ipc_dir / "requests"
        try:
            names = sorted(p.name for p in requests.iterdir())
        except OSError:
            return
        for name in names:
            path = requests / name
            if not name.endswith(".json"):
                continue  # never look inside non-json files
            if self._handled >= MAX_REQUESTS_PER_RUN:
                self._respond(name, {"ok": False,
                                     "error": "request limit reached for this run"})
                self._delete(path)
                continue
            self._handled += 1
            try:
                req = _read_request(path)
            except ValueError as e:
                self._respond(name, {"ok": False, "error": str(e)})
                self._delete(path)
                continue
            result = self.execute(req["server"], req["tool"], req["args"])
            self._respond(name, result)
            self._delete(path)

    @staticmethod
    def _delete(path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass

    def _respond(self, name: str, payload: dict[str, Any]) -> None:
        resp = self.ipc_dir / "responses" / name
        tmp = self.ipc_dir / "responses" / f".{name}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(payload))
            os.replace(tmp, resp)
        except OSError:
            pass  # responses are informational; the DB holds the truth

    # ---------- dispatch ----------
    def execute(self, server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        name = f"{server}_{tool}"
        if not permissions.tool_allowed(self.agent, server, tool):
            return {"ok": False,
                    "error": f"tool {name} is not allowed for this agent"}
        handler = HANDLERS.get(name)
        if handler is None:
            return {"ok": False, "error": f"unknown tool: {name}"}
        try:
            with self._lock:
                return {"ok": True, "result": handler(self, args)}
        except Exception:  # noqa: BLE001 - the broker must answer, not crash
            return {"ok": False, "error": f"internal error in {name}"}

    # ---------- handler resources (lazy, own connection) ----------
    @property
    def ledger(self) -> Ledger:
        if self._ledger is None:
            self._connect()
        assert self._ledger is not None
        return self._ledger

    @property
    def store(self) -> Store:
        if self._store is None:
            self._connect()
        assert self._store is not None
        return self._store

    @property
    def config(self) -> Config:
        if self._config is None:
            try:
                self._config = load_config()
            except (OSError, ValueError):
                self._config = Config()
        assert self._config is not None
        return self._config

    def _connect(self) -> None:
        if self._connect_fn is not None:
            conn = self._connect_fn()
        else:
            from .db import connect
            conn = connect()
        if self._ledger is None:
            self._ledger = Ledger(conn)
        if self._store is None:
            self._store = Store(conn)

    # ---------- handlers (identity bound to the session) ----------
    def _h_get_balances(self, args: dict[str, Any]) -> dict[str, Any]:
        return {k: v / 100 for k, v in self.ledger.balances().items()}

    def _h_request_spend(self, args: dict[str, Any]) -> dict[str, Any]:
        bucket = str(args.get("bucket", ""))
        try:
            amount = round(float(args.get("amount_eur", 0)) * 100)
        except (TypeError, ValueError):
            return {"status": "rejected", "reason": "amount_eur must be a number"}
        purpose = str(args.get("purpose", ""))
        venture_id = args.get("venture_id")
        if bucket == "experiment":
            if venture_id is None:
                return {"status": "rejected",
                        "reason": "experiment spending requires a venture_id"}
            gate = ventures.authorize_experiment_spend(
                self.ledger.conn, int(venture_id), amount,
                int(self.config.revenue_value("venture_budget_cents")))
            if gate is not None:
                return {"status": "rejected", "reason": gate}
        return self.ledger.request_spend(
            self.agent, bucket, amount, purpose, venture_id=venture_id)

    def _h_list_pending(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        return self.ledger.pending()

    def _h_recent_entries(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            limit = int(args.get("limit", 20))
        except (TypeError, ValueError):
            limit = 20
        return self.ledger.recent(limit)

    def _h_create_task(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.store.create_task(
            agent=str(args.get("agent", "")),
            title=str(args.get("title", "")),
            prompt=str(args.get("prompt", "")),
            priority=args.get("priority", 5),
            requires_review=bool(args.get("requires_review", False)),
            created_by=self.agent,  # identity comes from the run, not the caller
        )

    def _h_list_tasks(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        status = args.get("status")
        if status is not None and status not in (
            "pending", "running", "blocked", "done", "failed", "rejected", "cancelled",
        ):
            return [{"status": "error", "reason": f"unknown status: {status}"}]
        try:
            limit = int(args.get("limit", 30))
        except (TypeError, ValueError):
            limit = 30
        return self.store.list_tasks(status=status, limit=limit)

    def _h_request_human_action(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self.store.add_human_task(
            kind=str(args.get("kind", "")),
            title=str(args.get("title", "")),
            instructions=str(args.get("instructions", "")),
            url=str(args.get("url", "")),
            dedupe_key=str(args.get("dedupe_key", "")),
            created_by=self.agent,  # identity comes from the run
            blocks_task_id=args.get("blocks_task_id"),
        )
        if result.get("status") == "created":
            try:
                from .notify import notify_human
                notify_human(result["task"], root=self.root, store=self.store)
            except OSError as e:
                import sys
                print(f"kiraci: inbox notify failed: {e}", file=sys.stderr)
        return result

    def _h_list_human_tasks(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        status = args.get("status", "open")
        if status not in ("open", "done", "dismissed"):
            return [{"status": "error", "reason": f"unknown status: {status}"}]
        return self.store.list_human_tasks(status=status)

    def _h_create_venture(self, args: dict[str, Any]) -> dict[str, Any]:
        return ventures.create_venture(
            self.store, self.root,
            name=str(args.get("name", "")),
            kind=str(args.get("kind", "")),
            hypothesis=str(args.get("hypothesis", "")),
            score=args.get("score", 0),
            evidence_paths=list(args.get("evidence_paths", [])),
            caller=self.agent,  # identity comes from the run
            max_active=int(self.config.revenue_value("max_active_ventures")),
            min_sources=int(self.config.revenue_value("min_sources_per_research")),
        )

    def _h_update_venture(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            return ventures.update_venture(
                self.store, self.root, int(args.get("venture_id", 0)),
                str(args.get("status", "")),
                death_note=str(args.get("death_note", "")))
        except (ValueError, TypeError) as e:
            return {"status": "error", "reason": str(e)}

    def _h_list_ventures(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        return ventures.list_ventures(self.store.conn, args.get("status"))


#: The complete handler surface. Anything not in here is unreachable through
#: the broker - in particular every human-only operation listed in
#: HUMAN_ONLY_OPERATIONS.
HANDLERS = {
    "ledger_get_balances": BrokerSession._h_get_balances,
    "ledger_request_spend": BrokerSession._h_request_spend,
    "ledger_list_pending": BrokerSession._h_list_pending,
    "ledger_recent_entries": BrokerSession._h_recent_entries,
    "queue_create_task": BrokerSession._h_create_task,
    "queue_list_tasks": BrokerSession._h_list_tasks,
    "queue_request_human_action": BrokerSession._h_request_human_action,
    "queue_list_human_tasks": BrokerSession._h_list_human_tasks,
    "queue_create_venture": BrokerSession._h_create_venture,
    "queue_update_venture": BrokerSession._h_update_venture,
    "queue_list_ventures": BrokerSession._h_list_ventures,
}