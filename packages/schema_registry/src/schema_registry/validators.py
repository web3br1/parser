from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError


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
}


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
