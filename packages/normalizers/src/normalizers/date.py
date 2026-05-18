from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "America/Sao_Paulo"


def normalize_date(
    value: str, *, timezone: str = DEFAULT_TIMEZONE, now: datetime | None = None
) -> date | None:
    text = value.strip().lower()
    current = now or datetime.now(ZoneInfo(timezone))

    if text == "hoje":
        return current.date()
    if text == "amanhã" or text == "amanha":
        return date.fromordinal(current.date().toordinal() + 1)

    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None
