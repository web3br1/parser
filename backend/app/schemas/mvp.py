from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Currency(StrEnum):
    BRL = "BRL"


class PriceType(StrEnum):
    fixed = "fixed"
    starting_from = "starting_from"
    range = "range"
    unknown = "unknown"


class ServicePrice(StrictModel):
    service_name: str
    price_amount: float | None = None
    currency: Currency
    price_type: PriceType
    min_price: float | None = None
    max_price: float | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    @model_validator(mode="after")
    def validate_price_shape(self) -> "ServicePrice":
        if self.price_type == PriceType.fixed and self.price_amount is None:
            raise ValueError("fixed price requires price_amount")
        if self.price_type == PriceType.range and (self.min_price is None or self.max_price is None):
            raise ValueError("range price requires min_price and max_price")
        return self


class DayOfWeek(StrEnum):
    mon = "mon"
    tue = "tue"
    wed = "wed"
    thu = "thu"
    fri = "fri"
    sat = "sat"
    sun = "sun"


class BusinessHours(StrictModel):
    day_of_week: DayOfWeek
    open_time: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    close_time: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    is_closed: bool
    special_case: str | None = None

    @model_validator(mode="after")
    def validate_hours_shape(self) -> "BusinessHours":
        if not self.is_closed and (self.open_time is None or self.close_time is None):
            raise ValueError("open days require open_time and close_time")
        return self


class PaymentMethodValue(StrEnum):
    pix = "pix"
    cash = "cash"
    credit = "credit"
    debit = "debit"
    bank_transfer = "bank_transfer"
    unknown = "unknown"


class PaymentMethod(StrictModel):
    method: PaymentMethodValue
    accepted: bool
    conditions: str | None = None


class DiscountCondition(StrictModel):
    payment_method: str | None = None
    day_of_week: str | None = None
    min_value: float | None = None


class DiscountAction(StrictModel):
    discount_percentage: float | None = None
    discount_fixed: float | None = None


class DiscountRule(StrictModel):
    condition: DiscountCondition
    action: DiscountAction

    @model_validator(mode="after")
    def validate_discount_shape(self) -> "DiscountRule":
        has_condition = any(
            value is not None for value in self.condition.model_dump().values()
        )
        has_action = any(value is not None for value in self.action.model_dump().values())
        if not has_condition:
            raise ValueError("discount_rule requires at least one condition")
        if not has_action:
            raise ValueError("discount_rule requires at least one action")
        return self


class CancellationPolicy(StrictModel):
    notice_required_hours: float
    penalty_percentage: float | None = None
    penalty_fixed: float | None = None


FACT_SCHEMAS = {
    "service_price": ServicePrice,
    "business_hours": BusinessHours,
    "payment_method": PaymentMethod,
}

RULE_SCHEMAS = {
    "discount_rule": DiscountRule,
    "cancellation_policy": CancellationPolicy,
}
