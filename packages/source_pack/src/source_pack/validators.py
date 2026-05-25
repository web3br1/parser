from __future__ import annotations

import json
import re
from typing import Any

FORBIDDEN_MARKERS = (
    "raw_prompt",
    "provider_response",
    "SYSTEM PROMPT",
    "system prompt",
    "Traceback",
    "X-Amz-Signature",
    "password=",
)

TOKEN_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\b(?:sk|pk|rk|sb|org|proj)-[A-Za-z0-9_-]{16,}\b", re.IGNORECASE),
    re.compile(r"\b[A-Za-z]:(?:\\|\\\\)+(?:Users|Documents and Settings)(?:\\|\\\\)+[^\s,;)]*", re.IGNORECASE),
    re.compile(r"(?:^|\s)/(?:Users|home|root)/[^\s,;)]*", re.IGNORECASE),
)


def sanitize_text(text: str) -> str:
    sanitized = text
    for pattern in TOKEN_PATTERNS:
        sanitized = pattern.sub("[redacted]", sanitized)
    for marker in FORBIDDEN_MARKERS:
        sanitized = sanitized.replace(marker, "[redacted]")
    return sanitized


def validate_no_forbidden_payload(payload: Any) -> list[str]:
    serialized = json.dumps(payload, sort_keys=True, default=str)
    errors: list[str] = []
    for marker in FORBIDDEN_MARKERS:
        if marker in serialized:
            errors.append(f"forbidden_marker:{marker}")
    for pattern in TOKEN_PATTERNS:
        if pattern.search(serialized):
            errors.append(f"forbidden_pattern:{pattern.pattern}")
    return errors
