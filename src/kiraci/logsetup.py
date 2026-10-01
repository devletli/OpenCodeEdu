"""JSON-lines logging to data/logs/kiraci.log (5 MB x 5) plus stdout for journald.

A logging filter redacts anything the v0.2 secret detector flags, so keys or
card-like numbers never reach the log files. Ad hoc prints in the orchestrator
are replaced by this logger.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from pathlib import Path

from .store import redact_secrets

LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUPS = 5


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact_secrets(str(record.msg))
            if record.args:
                record.args = tuple(redact_secrets(str(a)) for a in record.args)
        except Exception:  # noqa: BLE001, S110 - logging must never break the app
            pass
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_configured: set[str] = set()


def setup_logging(root: Path, *, name: str = "kiraci") -> logging.Logger:
    """Idempotent: calling twice returns the same configured logger."""
    logger = logging.getLogger(name)
    if name in _configured:
        return logger
    logger.setLevel(logging.INFO)
    log_dir = Path(root) / "data" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_dir / "kiraci.log", maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS,
            encoding="utf-8")
        fh.setFormatter(JsonFormatter())
        fh.addFilter(RedactionFilter())
        logger.addHandler(fh)
    except OSError:
        pass  # e.g. read-only FS: stdout-only logging
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(JsonFormatter())
    sh.addFilter(RedactionFilter())
    logger.addHandler(sh)
    logger.propagate = False
    _configured.add(name)
    return logger


def get_logger(root: Path, *, name: str = "kiraci") -> logging.Logger:
    return setup_logging(root, name=name)