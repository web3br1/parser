from parsers.base import ExtractedPage, ExtractionError, ExtractionResult
from parsers.quality_gate import run_quality_gate


def test_good_extraction_passes() -> None:
    result = ExtractionResult(
        mime_type="text/plain",
        pages=[ExtractedPage(1, "x" * 120, 120, False)],
        total_chars=120,
    )
    assert run_quality_gate(result).passed is True


def test_too_short_fails() -> None:
    report = run_quality_gate(ExtractionResult(mime_type="text/plain", total_chars=99))
    assert report.passed is False
    assert report.rejection_reason == "too_short"


def test_error_fails() -> None:
    result = ExtractionResult(
        mime_type="application/pdf",
        error=ExtractionError.PAGES_EXCEEDED,
    )
    report = run_quality_gate(result)
    assert report.passed is False
    assert report.rejection_reason == "pages_exceeded"


def test_all_pages_empty_fails() -> None:
    result = ExtractionResult(
        mime_type="application/pdf",
        pages=[ExtractedPage(1, "", 0, True), ExtractedPage(2, "", 0, True)],
        total_chars=120,
    )
    assert run_quality_gate(result).rejection_reason == "all_pages_empty"


def test_large_content_warns() -> None:
    result = ExtractionResult(mime_type="text/plain", total_chars=500_001)
    report = run_quality_gate(result)
    assert report.passed is True
    assert "content_very_large" in report.warnings


def test_empty_page_ratio_warns() -> None:
    result = ExtractionResult(
        mime_type="application/pdf",
        pages=[
            ExtractedPage(1, "", 0, True),
            ExtractedPage(2, "x" * 120, 120, False),
        ],
        total_chars=120,
    )
    report = run_quality_gate(result)
    assert report.passed is True
    assert "high_empty_page_ratio" in report.warnings
