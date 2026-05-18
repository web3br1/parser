from __future__ import annotations

import re


def normalize_percent(value: str) -> float | None:
    text = value.strip().replace(",", ".")
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if not match:
        return None
    return float(match.group(1))
