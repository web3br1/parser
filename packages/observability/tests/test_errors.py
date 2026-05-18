from observability.errors import (
    DatabaseError,
    DomainError,
    FileValidationError,
    TechnicalError,
)


def test_domain_errors_are_not_retryable() -> None:
    err = FileValidationError(safe_detail={"reason": "magic_bytes_fail"})

    assert isinstance(err, DomainError)
    assert err.retryable is False
    assert err.code == "file_validation_failed"
    assert err.safe_detail["reason"] == "magic_bytes_fail"


def test_technical_errors_are_retryable() -> None:
    err = DatabaseError(provider="supabase", operation="insert")

    assert isinstance(err, TechnicalError)
    assert err.retryable is True
    assert err.provider == "supabase"
    assert err.operation == "insert"
