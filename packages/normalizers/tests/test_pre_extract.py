from normalizers.pre_extract import pre_normalize


def test_service_price_currency_string() -> None:
    result = pre_normalize("service_price", {"service_name": "Corte", "price_amount": "R$ 150,00", "currency": "BRL", "price_type": "fixed"})
    assert result["price_amount"] == 150.0


def test_service_price_already_float() -> None:
    result = pre_normalize("service_price", {"price_amount": 80.0})
    assert result["price_amount"] == 80.0


def test_business_hours_time_string() -> None:
    result = pre_normalize("business_hours", {"day_of_week": "mon", "open_time": "9h", "close_time": "18h", "is_closed": False})
    assert result["open_time"] == "09:00"
    assert result["close_time"] == "18:00"


def test_business_hours_already_formatted() -> None:
    result = pre_normalize("business_hours", {"open_time": "09:00", "close_time": "18:00"})
    assert result["open_time"] == "09:00"


def test_discount_rule_percent_string() -> None:
    result = pre_normalize(
        "discount_rule",
        {"condition": {}, "action": {"discount_percentage": "10%"}},
    )
    assert result["action"]["discount_percentage"] == 10.0


def test_discount_rule_fixed_currency() -> None:
    result = pre_normalize(
        "discount_rule",
        {"condition": {}, "action": {"discount_fixed": "R$ 20,00"}},
    )
    assert result["action"]["discount_fixed"] == 20.0


def test_cancellation_penalty_percent() -> None:
    result = pre_normalize(
        "cancellation_policy",
        {"notice_required_hours": 24, "penalty_percentage": "50%"},
    )
    assert result["penalty_percentage"] == 50.0


def test_non_normalizable_field_preserved() -> None:
    result = pre_normalize("service_price", {"price_amount": "sem preço definido"})
    # normalize_currency returns None → original string preserved
    assert result["price_amount"] == "sem preço definido"


def test_unknown_fact_type_passthrough() -> None:
    data = {"foo": "bar"}
    result = pre_normalize("unknown_type", data)
    assert result == data


def test_no_side_effects_on_original() -> None:
    original = {"action": {"discount_percentage": "10%"}}
    pre_normalize("discount_rule", original)
    # original dict must not be mutated
    assert original["action"]["discount_percentage"] == "10%"
