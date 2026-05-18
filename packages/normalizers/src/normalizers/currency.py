from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Money:
    amount: float
    currency: str = "BRL"


def normalize_currency(value: str) -> Money | None:
    text = value.strip().lower()
    match = re.search(r"(?:r\$\s*)?(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{1,2}))?", text)
    if not match:
        return None

    whole = match.group(1).replace(".", "")
    cents = match.group(2) or "00"
    return Money(amount=float(f"{whole}.{cents[:2]}"))
