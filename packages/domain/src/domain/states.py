from enum import StrEnum


class SourceState(StrEnum):
    DRAFT = "draft"
    UPLOADED = "uploaded"
    QUALITY_CHECKED = "quality_checked"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    PUBLISHED = "published"
    FAILED = "failed"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class ChunkState(StrEnum):
    PENDING = "pending"
    CLASSIFIED = "classified"
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class FactState(StrEnum):
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"
    CONFLICTED = "conflicted"


class AnswerState(StrEnum):
    VALID_ANSWER = "valid_answer"
    NOT_FOUND = "not_found"
    CONFLICTING_SOURCES = "conflicting_sources"
    NEEDS_HUMAN_VALIDATION = "needs_human_validation"
    PARTIAL_ANSWER = "partial_answer"
