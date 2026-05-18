from __future__ import annotations

import re
import unicodedata
from typing import Any

_SENSITIVE_TOKENS = frozenset(
    {
        "cost",
        "custo",
        "margin",
        "margem",
        "secret",
        "token",
        "credential",
    }
)
_SENSITIVE_PHRASES = frozenset(
    {
        "supplier_price",
        "internal_notes",
        "api_key",
    }
)


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: redact_sensitive(item)
            for key, item in value.items()
            if not is_sensitive_key(key)
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


def redact_sensitive_quote(value: Any, *, user_role: str) -> str | None:
    if not isinstance(value, str):
        return None
    if can_expose_sensitive_fields(user_role):
        return value
    normalized = normalize_identifier(value)
    if contains_sensitive_identifier(normalized):
        return None
    return value


def context_row(row: dict[str, Any], *, user_role: str) -> dict[str, Any]:
    return dict(row) if can_expose_sensitive_fields(user_role) else redact_sensitive(row)


def can_expose_sensitive_fields(user_role: str) -> bool:
    """Query responses are public-operational; no workspace role receives internal fields."""
    return False


def is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    normalized = normalize_identifier(key)
    return contains_sensitive_identifier(normalized)


def contains_sensitive_identifier(normalized: str) -> bool:
    tokens = {token for token in normalized.split("_") if token}
    if tokens & _SENSITIVE_TOKENS:
        return True
    compact = normalized.replace("_", "")
    return any(
        phrase in normalized or phrase.replace("_", "") == compact
        for phrase in _SENSITIVE_PHRASES
    )


def normalize_identifier(value: str) -> str:
    with_separators = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    decomposed = unicodedata.normalize("NFKD", with_separators.lower())
    ascii_text = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
