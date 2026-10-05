"""Thin IPC client used by the agent-facing MCP servers.

The MCP servers must never import or open the database: inside the sandbox the
only thing visible is a per-run IPC directory (see sandbox.py). A call writes
one request file and polls for the response file. The broker (running outside
the sandbox, in the orchestrator process) binds the call to the run's real
identity, so the calling agent cannot spoof it.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

REQUEST_TIMEOUT_S = 60.0
POLL_INTERVAL_S = 0.1


class IpcError(RuntimeError):
    """Raised when a broker call cannot be completed."""


def ipc_dir() -> Path | None:
    """The run's IPC directory, or None when not running under the broker."""
    raw = os.environ.get("KIRACI_IPC_DIR", "")
    return Path(raw) if raw else None


def call(server: str, tool: str, args: dict[str, Any], *,
         ipc_path: Path | None = None,
         timeout_s: float = REQUEST_TIMEOUT_S) -> Any:
    """Execute one broker call and return its JSON-decoded result.

    Raises IpcError with a clear message when the broker is unreachable,
    rejects the call or answers too late. Callers validate the shape
    (dict vs list) before returning: MCP output schemas must never receive
    the wrong JSON type. Atomic write (temp file + os.replace), response
    polled every POLL_INTERVAL_S.
    """
    root = ipc_path or ipc_dir()
    if root is None:
        raise IpcError("KIRACI_IPC_DIR is not set: broker IPC is unavailable")
    req_id = uuid.uuid4().hex
    requests = root / "requests"
    responses = root / "responses"
    if not requests.is_dir() or not responses.is_dir():
        raise IpcError("broker directories are missing for this run")
    req_path = requests / f"{req_id}.json"
    body = json.dumps({"server": server, "tool": tool, "args": args})
    tmp = requests / f".{req_id}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(body)
    os.replace(tmp, req_path)
    resp_path = responses / f"{req_id}.json"
    waited = 0.0
    while waited < timeout_s:
        if resp_path.exists():
            break
        waited += POLL_INTERVAL_S
        time.sleep(POLL_INTERVAL_S)
    else:
        req_path.unlink(missing_ok=True)
        raise IpcError(f"broker did not answer {server}.{tool} within {timeout_s:g}s")
    try:
        with open(resp_path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, ValueError) as e:
        raise IpcError(f"broker response unreadable for {server}.{tool}") from e
    finally:
        resp_path.unlink(missing_ok=True)
    if not isinstance(payload, dict) or "ok" not in payload:
        raise IpcError(f"malformed broker response for {server}.{tool}")
    if not payload["ok"]:
        raise IpcError(str(payload.get("error", "broker call failed")))
    return payload.get("result")