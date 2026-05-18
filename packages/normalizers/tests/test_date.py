from datetime import datetime
from zoneinfo import ZoneInfo

from normalizers.date import normalize_date


def test_normalize_date_today() -> None:
    now = datetime(2026, 5, 5, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert str(normalize_date("hoje", now=now)) == "2026-05-05"


def test_normalize_date_br_format() -> None:
    assert str(normalize_date("05/05/2026")) == "2026-05-05"
