from dataclasses import dataclass

from parsers.base import ExtractionResult


@dataclass(frozen=True)
class QualityReport:
    passed: bool
    total_chars: int
    total_pages: int
    total_sheets: int
    empty_pages: int
    rejection_reason: str | None
    warnings: list[str]


def run_quality_gate(result: ExtractionResult) -> QualityReport:
    total_pages = len(result.pages)
    total_sheets = len(result.sheets)
    empty_pages = sum(1 for page in result.pages if page.is_empty)
    warnings = list(result.warnings)

    if result.error is not None:
        return QualityReport(
            False,
            result.total_chars,
            total_pages,
            total_sheets,
            empty_pages,
            str(result.error.value),
            warnings,
        )

    if result.total_chars < 100:
        return QualityReport(
            False, result.total_chars, total_pages, total_sheets, empty_pages, "too_short", warnings
        )

    if total_pages > 0 and empty_pages == total_pages:
        return QualityReport(
            False,
            result.total_chars,
            total_pages,
            total_sheets,
            empty_pages,
            "all_pages_empty",
            warnings,
        )

    if result.total_chars > 500_000 and "content_very_large" not in warnings:
        warnings.append("content_very_large")

    if total_pages > 0 and empty_pages / total_pages > 0.3:
        warnings.append("high_empty_page_ratio")

    return QualityReport(True, result.total_chars, total_pages, total_sheets, empty_pages, None, warnings)
