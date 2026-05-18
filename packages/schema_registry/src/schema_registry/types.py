from typing import Literal, NotRequired, Required, TypedDict


class ServicePrice(TypedDict):
    service_name: Required[str]
    price_amount: NotRequired[float | None]
    currency: Required[Literal["BRL"]]
    price_type: Required[Literal["fixed", "starting_from", "range", "unknown"]]
    min_price: NotRequired[float | None]
    max_price: NotRequired[float | None]
    valid_from: NotRequired[str | None]
    valid_until: NotRequired[str | None]


class BusinessHours(TypedDict):
    day_of_week: Required[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]]
    open_time: NotRequired[str | None]
    close_time: NotRequired[str | None]
    is_closed: Required[bool]
    special_case: NotRequired[str | None]


class PaymentMethod(TypedDict):
    method: Required[Literal["pix", "cash", "credit", "debit", "bank_transfer", "unknown"]]
    accepted: Required[bool]
    conditions: NotRequired[str | None]


class DiscountCondition(TypedDict, total=False):
    payment_method: str
    day_of_week: str
    min_value: float


class DiscountAction(TypedDict, total=False):
    discount_percentage: float
    discount_fixed: float


class DiscountRule(TypedDict):
    condition: Required[DiscountCondition]
    action: Required[DiscountAction]


class CancellationPolicy(TypedDict):
    notice_required_hours: Required[float]
    penalty_percentage: NotRequired[float]
    penalty_fixed: NotRequired[float]


class ContactInfo(TypedDict):
    phone: NotRequired[str | None]
    email: NotRequired[str | None]
    address: NotRequired[str | None]
    website: NotRequired[str | None]
    whatsapp: NotRequired[str | None]
    contact_name: NotRequired[str | None]


class FAQItem(TypedDict):
    question: Required[str]
    answer: Required[str]
    category: NotRequired[str]
