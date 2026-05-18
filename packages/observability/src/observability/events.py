from __future__ import annotations

import re
from typing import Any

_EVENT_PART_PATTERN = re.compile(r"[^a-z0-9_-]+")


def agent_event(
    agent: Any,
    stage: Any,
    action: Any,
    outcome: Any,
    **fields: Any,
) -> tuple[str, dict[str, Any]]:
    event_fields = {
        **fields,
        "agent": _safe_field_value(agent),
        "stage": _safe_field_value(stage),
        "action": _safe_field_value(action),
        "outcome": _safe_field_value(outcome),
    }
    event_name = ".".join(
        (
            _normalize_event_part(agent),
            _normalize_event_part(stage),
            _normalize_event_part(action),
            _normalize_event_part(outcome),
        )
    )
    return event_name, event_fields


def _normalize_event_part(value: Any) -> str:
    text = _safe_string(value).strip().lower()
    if text == "<unprintable>":
        return "unknown"
    normalized = _EVENT_PART_PATTERN.sub("_", text)
    return normalized or "unknown"


def _safe_field_value(value: Any) -> Any:
    if isinstance(value, str):
        return value
    return _safe_string(value)


def _safe_string(value: Any) -> str:
    try:
        return str(value)
    except Exception:
        return "<unprintable>"
