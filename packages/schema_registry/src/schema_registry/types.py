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


class ControlledDocumentMetadata(TypedDict):
    document_code: Required[str]
    document_type: Required[
        Literal["POP", "IT", "Manual", "Policy", "Form", "Record", "Specification"]
    ]
    title: Required[str]
    revision: Required[str]
    status: Required[Literal["vigent", "obsolete", "draft", "approved", "unknown"]]
    owner_area: Required[str]
    issue_date: NotRequired[str | None]
    approval_date: NotRequired[str | None]
    review_due_date: NotRequired[str | None]
    process: NotRequired[str | None]
    plant: NotRequired[str | None]
    approvers: NotRequired[list[str]]
    confidentiality: NotRequired[Literal["public", "internal", "restricted"] | None]
    allowed_audience: NotRequired[list[str]]


class IndustrialRequirement(TypedDict):
    requirement_type: Required[
        Literal[
            "procedure",
            "deadline",
            "acceptance_criteria",
            "mandatory_record",
            "approval",
            "training",
            "other",
        ]
    ]
    subject: Required[str]
    requirement: Required[str]
    applies_to: NotRequired[str | None]


class IndustrialResponsibility(TypedDict):
    role: Required[str]
    responsibility: Required[str]
    process: NotRequired[str | None]
    escalation: NotRequired[str | None]


class IndustrialRelation(TypedDict):
    from_id: Required[str]
    from_type: Required[Literal["Document", "Process", "Form", "Record", "Role"]]
    to_id: Required[str]
    to_type: Required[Literal["Document", "Process", "Form", "Record", "Role"]]
    relationship_type: Required[
        Literal[
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
    ]
    source_document_code: NotRequired[str | None]
    evidence_quote: NotRequired[str | None]
