"""Structured JSON logging with credential redaction."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

_SECRET_PATTERNS = [
    # (pattern, keep_prefix): the second flag is True when group 1 is a safe
    # prefix (e.g. the JSON key) that should survive redaction.
    (re.compile(r"sk-or-[A-Za-z0-9_\-]{8,}"), False),
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), False),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}"), True),
    (re.compile(r"(\"api_key\"\s*:\s*\")[^\"]+"), True),
    (re.compile(r"(\"authorization\"\s*:\s*\")[^\"]+"), True),
]
_REDACTED = "***REDACTED***"


def redact(text: str) -> str:
    """Best-effort credential redaction for logs, exports and error payloads."""
    if not text:
        return text
    out = text
    for pattern, keep_prefix in _SECRET_PATTERNS:
        if keep_prefix:
            out = pattern.sub(lambda m: m.group(1) + _REDACTED, out)
        else:
            out = pattern.sub(_REDACTED, out)
    return out


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        for key in ("request_id", "project_id", "job_id", "duration_ms", "status_code", "path"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, default=str)


def setup_logging() -> logging.Logger:
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        if settings.environment == "production":
            handler.setFormatter(JsonFormatter())
        else:
            handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
            )
        root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return logging.getLogger("npi")


logger = setup_logging()
