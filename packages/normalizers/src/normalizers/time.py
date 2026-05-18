from __future__ import annotations

import re

VAGUE_TIME_FALLBACKS = {
    "manha": "09:00",
    "manhã": "09:00",
    "tarde": "14:00",
    "fim do dia": "18:00",
    "final do dia": "18:00",
    "noite": "19:00",
}


def normalize_time(value: str) -> str | None:
    text = value.strip().lower()
    if text in VAGUE_TIME_FALLBACKS:
        return VAGUE_TIME_FALLBACKS[text]

    match = re.search(r"\b([01]?\d|2[0-3])(?::|h)?([0-5]\d)?\b", text)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    return f"{hour:02d}:{minute:02d}"
