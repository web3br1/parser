from normalizers.time import normalize_time


def test_normalize_time_numeric_hour() -> None:
    assert normalize_time("9h") == "09:00"


def test_normalize_time_vague_fallback() -> None:
    assert normalize_time("fim do dia") == "18:00"
