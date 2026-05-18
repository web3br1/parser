from normalizers.currency import normalize_currency


def test_normalize_currency_with_symbol() -> None:
    money = normalize_currency("R$ 120")
    assert money is not None
    assert money.amount == 120.0
    assert money.currency == "BRL"


def test_normalize_currency_with_cents() -> None:
    money = normalize_currency("R$ 1.234,50")
    assert money is not None
    assert money.amount == 1234.5
