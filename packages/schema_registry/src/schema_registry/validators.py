from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


class _StrictModel(BaseModel):
    """Base Pydantic model: strict coercion, no extra fields."""

    model_config = ConfigDict(strict=True, extra="forbid")


# ---------------------------------------------------------------------------
# Pydantic validation models — one per MVP fact type
# These are separate from the TypedDicts in types.py which serve as schema
# documentation. These models are used for runtime LLM-output validation.
# ---------------------------------------------------------------------------


class ServicePriceModel(_StrictModel):
    service_name: str
    price_amount: float
    currency: Literal["BRL"] = "BRL"
    price_type: Literal["fixed", "starting_from", "range", "unknown"]
    min_price: float | None = None
    max_price: float | None = None
    valid_from: str | None = None
    valid_until: str | None = None


class BusinessHoursModel(_StrictModel):
    day_of_week: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    open_time: str | None = None
    close_time: str | None = None
    is_closed: bool = False
    special_case: str | None = None


class PaymentMethodModel(_StrictModel):
    method: Literal["pix", "cash", "credit", "debit", "bank_transfer", "unknown"]
    accepted: bool
    conditions: str | None = None


class DiscountConditionModel(_StrictModel):
    payment_method: str | None = None
    day_of_week: str | None = None
    min_value: float | None = None


class DiscountActionModel(_StrictModel):
    discount_percentage: float | None = None
    discount_fixed: float | None = None


class DiscountRuleModel(_StrictModel):
    condition: DiscountConditionModel
    action: DiscountActionModel


class CancellationPolicyModel(_StrictModel):
    notice_required_hours: float
    penalty_percentage: float | None = None
    penalty_fixed: float | None = None


class ContactInfoModel(_StrictModel):
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    website: str | None = None
    whatsapp: str | None = None
    contact_name: str | None = None


class FAQItemModel(_StrictModel):
    question: str
    answer: str
    category: str | None = None


class ControlledDocumentMetadataModel(_StrictModel):
    document_code: str
    document_type: Literal["POP", "IT", "Manual", "Policy", "Form", "Record", "Specification"]
    title: str
    revision: str
    status: Literal["vigent", "obsolete", "draft", "approved", "unknown"]
    owner_area: str
    issue_date: str | None = None
    approval_date: str | None = None
    review_due_date: str | None = None
    process: str | None = None
    plant: str | None = None
    approvers: list[str] = []
    confidentiality: Literal["public", "internal", "restricted"] | None = None
    allowed_audience: list[str] = []

    @field_validator("document_code", mode="before")
    @classmethod
    def _normalize_document_code(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return "-".join(part for part in value.strip().upper().replace("_", "-").split() if part)

    @field_validator("document_type", mode="before")
    @classmethod
    def _normalize_document_type(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        aliases = {
            "pop": "POP",
            "it": "IT",
            "manual": "Manual",
            "man": "Manual",
            "policy": "Policy",
            "politica": "Policy",
            "pol": "Policy",
            "form": "Form",
            "formulario": "Form",
            "for": "Form",
            "frm": "Form",
            "record": "Record",
            "registro": "Record",
            "reg": "Record",
            "specification": "Specification",
            "spec": "Specification",
            "esp": "Specification",
        }
        return aliases.get(normalized, value)

    @field_validator("revision", mode="before")
    @classmethod
    def _normalize_revision(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        match = re.search(r"\d{1,3}", value)
        if match:
            return match.group(0).zfill(2)
        return value.strip()

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        normalized = _fold_text(value)
        aliases = {
            "vigente": "vigent",
            "vigent": "vigent",
            "aprovado": "approved",
            "approved": "approved",
            "obsoleto": "obsolete",
            "obsolete": "obsolete",
            "rascunho": "draft",
            "draft": "draft",
            "unknown": "unknown",
            "desconhecido": "unknown",
        }
        return aliases.get(normalized, value)

    @field_validator("confidentiality", mode="before")
    @classmethod
    def _normalize_confidentiality(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        normalized = _fold_text(value)
        aliases = {
            "publico": "public",
            "public": "public",
            "interno": "internal",
            "internal": "internal",
            "restrito": "restricted",
            "restricted": "restricted",
        }
        return aliases.get(normalized, value)


class IndustrialRequirementModel(_StrictModel):
    requirement_type: Literal[
        "procedure",
        "deadline",
        "acceptance_criteria",
        "mandatory_record",
        "approval",
        "training",
        "other",
    ]
    subject: str
    requirement: str
    applies_to: str | None = None


class IndustrialResponsibilityModel(_StrictModel):
    role: str
    responsibility: str
    process: str | None = None
    escalation: str | None = None


class IndustrialRelationModel(_StrictModel):
    from_id: str
    from_type: Literal["Document", "Process", "Form", "Record", "Role"]
    to_id: str
    to_type: Literal["Document", "Process", "Form", "Record", "Role"]
    relationship_type: Literal[
        "defines_process",
        "uses_form",
        "requires_record",
        "assigns_responsibility",
        "requires_approval",
        "references_document",
        "supersedes",
        "is_revision_of",
        "triggers_action",
        "requires_training",
    ]
    source_document_code: str | None = None
    evidence_quote: str | None = None


# ---------------------------------------------------------------------------
# Registry and validator
# ---------------------------------------------------------------------------

_FACT_TYPE_MAP: dict[str, type[_StrictModel]] = {
    "service_price": ServicePriceModel,
    "business_hours": BusinessHoursModel,
    "payment_method": PaymentMethodModel,
    "discount_rule": DiscountRuleModel,
    "cancellation_policy": CancellationPolicyModel,
    "contact_info": ContactInfoModel,
    "faq_item": FAQItemModel,
    "controlled_document_metadata": ControlledDocumentMetadataModel,
    "industrial_requirement": IndustrialRequirementModel,
    "industrial_responsibility": IndustrialResponsibilityModel,
    "industrial_relation": IndustrialRelationModel,
}


def _fold_text(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("ç", "c")
        .replace("ã", "a")
        .replace("á", "a")
        .replace("à", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
    )


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    data: dict[str, Any]
    errors: list[str]


def get_pydantic_model(fact_type: str) -> type[_StrictModel]:
    if fact_type not in _FACT_TYPE_MAP:
        raise ValueError(f"Unknown fact_type: {fact_type!r}")
    return _FACT_TYPE_MAP[fact_type]


def validate_extraction(
    fact_type: str,
    raw_data: dict[str, Any],
) -> ValidationResult:
    """
    Validates raw_data against the Pydantic model for fact_type.
    Never raises — encapsulates ValidationError in ValidationResult.
    """
    try:
        model_cls = get_pydantic_model(fact_type)
        instance = model_cls(**raw_data)
        return ValidationResult(valid=True, data=instance.model_dump(), errors=[])
    except ValidationError as exc:
        return ValidationResult(
            valid=False,
            data={},
            errors=[f"{e['loc']}: {e['msg']}" for e in exc.errors()],
        )
    except Exception as exc:
        return ValidationResult(valid=False, data={}, errors=[str(exc)])
