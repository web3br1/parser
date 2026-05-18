import pytest
from schema_registry.validators import (
    ValidationResult,
    get_pydantic_model,
    validate_extraction,
)

# ---------------------------------------------------------------------------
# get_pydantic_model
# ---------------------------------------------------------------------------


def test_get_pydantic_model_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown fact_type"):
        get_pydantic_model("unknown_type")


def test_get_pydantic_model_all_known() -> None:
    for ft in (
        "service_price",
        "business_hours",
        "payment_method",
        "discount_rule",
        "cancellation_policy",
        "contact_info",
        "faq_item",
    ):
        model = get_pydantic_model(ft)
        assert model is not None


# ---------------------------------------------------------------------------
# service_price
# ---------------------------------------------------------------------------


def test_validate_service_price_valid() -> None:
    result = validate_extraction(
        "service_price",
        {
            "service_name": "Corte feminino",
            "price_amount": 120.0,
            "currency": "BRL",
            "price_type": "fixed",
        },
    )
    assert result.valid is True
    assert result.data["service_name"] == "Corte feminino"
    assert result.errors == []


def test_validate_service_price_missing_required() -> None:
    result = validate_extraction("service_price", {"price_amount": 50.0})
    assert result.valid is False
    assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# contact_info
# ---------------------------------------------------------------------------


def test_validate_contact_info_valid_phone() -> None:
    result = validate_extraction("contact_info", {"phone": "(11) 99999-9999"})
    assert result.valid is True
    assert result.data["phone"] == "(11) 99999-9999"


def test_validate_contact_info_all_none() -> None:
    # Pydantic allows all-None; worker-level guard catches this separately
    result = validate_extraction(
        "contact_info",
        {
            "phone": None,
            "email": None,
            "address": None,
            "website": None,
            "whatsapp": None,
            "contact_name": None,
        },
    )
    assert result.valid is True  # Pydantic passes; worker guard rejects


# ---------------------------------------------------------------------------
# faq_item
# ---------------------------------------------------------------------------


def test_validate_faq_item_valid() -> None:
    result = validate_extraction(
        "faq_item", {"question": "Qual o horário?", "answer": "Seg a Sex, 9h às 18h"}
    )
    assert result.valid is True


def test_validate_faq_item_missing_answer() -> None:
    result = validate_extraction("faq_item", {"question": "Qual o horário?"})
    assert result.valid is False
    assert len(result.errors) > 0


def test_validate_faq_item_missing_question() -> None:
    result = validate_extraction("faq_item", {"answer": "Seg a Sex"})
    assert result.valid is False


# ---------------------------------------------------------------------------
# Never raises
# ---------------------------------------------------------------------------


def test_validate_extraction_never_raises() -> None:
    # Extra fields — strict mode should return invalid, not raise
    result = validate_extraction("service_price", {"extra_field": "boom"})
    assert isinstance(result, ValidationResult)
    assert result.valid is False


def test_validate_extraction_unknown_type_never_raises() -> None:
    result = validate_extraction("unknown_type", {})
    assert isinstance(result, ValidationResult)
    assert result.valid is False
    assert "Unknown fact_type" in result.errors[0]


def test_validate_extraction_garbage_input() -> None:
    result = validate_extraction("faq_item", {"question": 123, "answer": None})
    assert isinstance(result, ValidationResult)
