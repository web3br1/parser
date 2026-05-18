from __future__ import annotations

import json
import os
import re
import traceback
from datetime import UTC, datetime
from typing import Any

from .context import get_request_id

_DENYLIST = {
    "authorization",
    "cookie",
    "api_key",
    "service_role",
    "access_token",
    "refresh_token",
    "password",
    "raw_response",
    "chunk.content",
    "document_content",
    "file_bytes",
}
_SECRET_TEXT_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"Bearer\s+(?:eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]{20,})"),
]


def redact_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {key: _redact_value(key, value) for key, value in data.items()}


def get_logger(service: str) -> JsonLogger:
    return JsonLogger(service=service)


class JsonLogger:
    def __init__(self, service: str) -> None:
        self.service = service

    def info(self, event: str, **fields: Any) -> None:
        self._emit("INFO", event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit("WARNING", event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit("ERROR", event, **fields)

    def exception(self, event: str, exc: BaseException, **fields: Any) -> None:
        stack = None
        if os.getenv("APP_ENV", "development") != "production":
            stack = "".join(traceback.format_exception(exc))
        self._emit(
            "ERROR",
            event,
            error_type=type(exc).__name__,
            stack=stack,
            **fields,
        )

    def _emit(self, level: str, event: str, **fields: Any) -> None:
        try:
            payload = {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": level,
                "service": self.service,
                "event": event,
                "request_id": fields.pop("request_id", None) or get_request_id(),
                "workflow_id": fields.pop("workflow_id", None),
                "job_id": fields.pop("job_id", None),
                "workspace_id": fields.pop("workspace_id", None),
                "error_type": fields.pop("error_type", None),
                "error_code": fields.pop("error_code", None),
                "stack": fields.pop("stack", None),
                **fields,
            }
            # Usar print com flush=True é mais robusto em ambientes de teste
            print(json.dumps(redact_payload(payload), default=str), flush=True)
        except Exception:
            # Fallback seguro para não travar a aplicação por causa do log
            pass


def _redact_value(key: str, value: Any) -> Any:
    normalized = key.lower()
    if normalized in _DENYLIST or any(secret in normalized for secret in _DENYLIST):
        return "[REDACTED]"
    if isinstance(value, dict):
        return redact_payload(value)
    if isinstance(value, list):
        return [_redact_list_item(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_list_item(item: Any) -> Any:
    if isinstance(item, dict):
        return redact_payload(item)
    if isinstance(item, str):
        return _redact_text(item)
    return item


def _redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_TEXT_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted
