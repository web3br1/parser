from __future__ import annotations

from typing import Any


class BaseAppError(Exception):
    code: str = "app_error"
    message: str = "Application error"
    retryable: bool = False

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        safe_detail: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.safe_detail = safe_detail or {}
        super().__init__(self.message)


class DomainError(BaseAppError):
    code = "domain_error"
    message = "Domain error"
    retryable = False


class TechnicalError(BaseAppError):
    code = "technical_error"
    message = "Technical error"
    retryable = True
    provider: str | None = None
    operation: str | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        safe_detail: dict[str, Any] | None = None,
        provider: str | None = None,
        operation: str | None = None,
    ) -> None:
        self.provider = provider
        self.operation = operation
        super().__init__(message, code=code, safe_detail=safe_detail)


class FileValidationError(DomainError):
    code = "file_validation_failed"
    message = "File validation failed"


class QualityGateError(DomainError):
    code = "quality_gate_failed"
    message = "Quality gate failed"


class WorkspaceMismatchError(DomainError):
    code = "workspace_mismatch"
    message = "Workspace mismatch"


class ClassificationParseError(DomainError):
    code = "classification_parse_failed"
    message = "Classification parse failed"


class DatabaseError(TechnicalError):
    code = "database_error"
    message = "Database error"


class StorageError(TechnicalError):
    code = "storage_error"
    message = "Storage error"


class QueueError(TechnicalError):
    code = "queue_error"
    message = "Queue error"


class ModelProviderError(TechnicalError):
    code = "model_provider_error"
    message = "Model provider error"


class OperationTimeoutError(TechnicalError):
    code = "operation_timeout"
    message = "Operation timeout"


class ProviderTimeoutError(TechnicalError):
    code = "provider_timeout"
    message = "Provider timeout"
