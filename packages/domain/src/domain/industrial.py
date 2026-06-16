import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DOCUMENT_TYPE_VALUES = (
    "POP",
    "IT",
    "Manual",
    "Policy",
    "Form",
    "Record",
    "Specification",
)
DocumentType = Literal["POP", "IT", "Manual", "Policy", "Form", "Record", "Specification"]

DOCUMENT_STATUS_VALUES = ("vigent", "obsolete", "draft", "approved", "unknown")
DocumentStatus = Literal["vigent", "obsolete", "draft", "approved", "unknown"]

CONFIDENTIALITY_VALUES = ("public", "internal", "restricted")
Confidentiality = Literal["public", "internal", "restricted"]

RELATIONSHIP_TYPE_VALUES = (
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
)
RelationshipType = Literal[
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

_DOCUMENT_TYPE_ALIASES = {
    "POP": "POP",
    "IT": "IT",
    "MANUAL": "Manual",
    "POLICY": "Policy",
    "FORM": "Form",
    "FOR": "Form",
    "RECORD": "Record",
    "SPECIFICATION": "Specification",
    "SPEC": "Specification",
}

_STATUS_ALIASES = {
    "VIGENT": "vigent",
    "VIGENTE": "vigent",
    "ACTIVE": "vigent",
    "OBSOLETE": "obsolete",
    "OBSOLETO": "obsolete",
    "DEPRECATED": "obsolete",
    "DRAFT": "draft",
    "RASCUNHO": "draft",
    "APPROVED": "approved",
    "APROVADO": "approved",
    "UNKNOWN": "unknown",
    "DESCONHECIDO": "unknown",
}


def normalize_document_code(value: str) -> str:
    normalized = re.sub(r"[\s_]+", "-", value.strip().upper())
    normalized = re.sub(r"-+", "-", normalized)
    return normalized.strip("-")


def normalize_revision(value: str) -> str:
    normalized = value.strip().upper()
    normalized = re.sub(r"^(?:REV(?:ISAO|ISÃO)?\.?|R)\s*[-:.]?\s*", "", normalized)
    return normalized.strip()


def normalize_document_status(value: str) -> str:
    normalized = value.strip().upper()
    return _STATUS_ALIASES.get(normalized, value.strip().lower())


def _strip_text(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class ControlledDocumentMetadata(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    document_code: str
    document_type: DocumentType
    title: str
    revision: str
    status: DocumentStatus
    owner_area: str
    issue_date: str | None = None
    approval_date: str | None = None
    review_due_date: str | None = None
    process: str | None = None
    plant: str | None = None
    approvers: list[str] = Field(default_factory=list)
    confidentiality: Confidentiality | None = None
    allowed_audience: list[str] = Field(default_factory=list)

    @field_validator("document_code", mode="before")
    @classmethod
    def _normalize_document_code(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_document_code(value)
        return value

    @field_validator("document_type", mode="before")
    @classmethod
    def _normalize_document_type(cls, value: object) -> object:
        if isinstance(value, str):
            return _DOCUMENT_TYPE_ALIASES.get(value.strip().upper(), value.strip())
        return value

    @field_validator("revision", mode="before")
    @classmethod
    def _normalize_revision(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_revision(value)
        return value

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_document_status(value)
        return value

    @field_validator("confidentiality", mode="before")
    @classmethod
    def _normalize_confidentiality(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator(
        "title",
        "owner_area",
        "issue_date",
        "approval_date",
        "review_due_date",
        "process",
        "plant",
        mode="before",
    )
    @classmethod
    def _strip_string_fields(cls, value: object) -> object:
        return _strip_text(value)


class DocumentRelationship(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    from_id: str
    from_type: str
    to_id: str
    to_type: str
    relationship_type: RelationshipType
    source_document_code: str | None = None
    evidence_quote: str | None = None

    @field_validator("relationship_type", mode="before")
    @classmethod
    def _normalize_relationship_type(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("source_document_code", mode="before")
    @classmethod
    def _normalize_source_document_code(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_document_code(value)
        return value

    @field_validator("from_id", "from_type", "to_id", "to_type", "evidence_quote", mode="before")
    @classmethod
    def _strip_string_fields(cls, value: object) -> object:
        return _strip_text(value)
