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
        "controlled_document_metadata",
        "industrial_requirement",
        "industrial_responsibility",
        "industrial_relation",
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


# ---------------------------------------------------------------------------
# industrial/QMS types
# ---------------------------------------------------------------------------


def test_validate_controlled_document_metadata_valid() -> None:
    result = validate_extraction(
        "controlled_document_metadata",
        {
            "document_code": "POP-QA-014",
            "document_type": "POP",
            "title": "Controle de Nao Conformidades",
            "revision": "04",
            "status": "vigent",
            "owner_area": "Qualidade",
        },
    )

    assert result.valid is True
    assert result.data["document_code"] == "POP-QA-014"


def test_validate_controlled_document_metadata_requires_revision() -> None:
    result = validate_extraction(
        "controlled_document_metadata",
        {
            "document_code": "POP-QA-014",
            "document_type": "POP",
            "title": "Controle de Nao Conformidades",
            "status": "vigent",
            "owner_area": "Qualidade",
        },
    )

    assert result.valid is False
    assert any("revision" in error for error in result.errors)


def test_validate_controlled_document_metadata_normalizes_natural_values() -> None:
    result = validate_extraction(
        "controlled_document_metadata",
        {
            "document_code": " pop qa 014 ",
            "document_type": "pop",
            "title": "Controle de Nao Conformidades",
            "revision": "Rev. 04",
            "status": "Vigente",
            "owner_area": "Qualidade",
        },
    )

    assert result.valid is True
    assert result.data["document_code"] == "POP-QA-014"
    assert result.data["document_type"] == "POP"
    assert result.data["revision"] == "04"
    assert result.data["status"] == "vigent"


def test_validate_industrial_requirement_valid() -> None:
    result = validate_extraction(
        "industrial_requirement",
        {
            "requirement_type": "deadline",
            "subject": "Investigacao de NC",
            "requirement": "A investigacao deve ser concluida em 10 dias.",
            "applies_to": "Nao conformidade",
        },
    )

    assert result.valid is True
    assert result.data["requirement_type"] == "deadline"


def test_validate_industrial_responsibility_valid() -> None:
    result = validate_extraction(
        "industrial_responsibility",
        {
            "role": "Gerente da Qualidade",
            "responsibility": "Aprovar CAPA critica.",
            "process": "CAPA",
        },
    )

    assert result.valid is True
    assert result.data["role"] == "Gerente da Qualidade"


def test_validate_industrial_relation_valid() -> None:
    result = validate_extraction(
        "industrial_relation",
        {
            "from_id": "POP-QA-014",
            "from_type": "Document",
            "to_id": "FOR-QA-002",
            "to_type": "Form",
            "relationship_type": "uses_form",
        },
    )

    assert result.valid is True
    assert result.data["relationship_type"] == "uses_form"


def test_validate_industrial_relation_preserves_optional_provenance() -> None:
    result = validate_extraction(
        "industrial_relation",
        {
            "from_id": "POP-QA-014",
            "from_type": "Document",
            "to_id": "FOR-QA-002",
            "to_type": "Form",
            "relationship_type": "uses_form",
            "source_document_code": "POP-QA-014",
            "evidence_quote": "Registrar a NC no formulario FOR-QA-002.",
        },
    )

    assert result.valid is True
    assert result.data["source_document_code"] == "POP-QA-014"
    assert result.data["evidence_quote"] == "Registrar a NC no formulario FOR-QA-002."
