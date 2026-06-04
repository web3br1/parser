import importlib
from pathlib import Path

from parsers.base import (
    MAX_EXTRACTED_CHARS,
    BaseParser,
    ExtractedPage,
    ExtractionError,
    ExtractionResult,
    sanitize_text,
    truncate_to_limit,
)
from parsers.page_profile import (
    page_profiles_to_metadata,
    profile_fitz_document,
    summarize_page_profiles,
)

MAX_PDF_PAGES = 200
PDF_MIME = "application/pdf"


class PDFParser(BaseParser):
    def extract(self, path: Path) -> ExtractionResult:
        try:
            fitz = importlib.import_module("fitz")

            with fitz.open(path) as document:
                if document.page_count > MAX_PDF_PAGES:
                    return ExtractionResult(mime_type=PDF_MIME, error=ExtractionError.PAGES_EXCEEDED)

                page_profiles = profile_fitz_document(document)
                pages: list[ExtractedPage] = []
                total_chars = 0
                warnings: list[str] = []

                for index, page in enumerate(document, start=1):
                    text = sanitize_text(page.get_text("text"))
                    text, truncated = truncate_to_limit(text, total_chars)
                    if truncated and "text_limit_reached" not in warnings:
                        warnings.append("text_limit_reached")
                    char_count = len(text)
                    total_chars += char_count
                    pages.append(
                        ExtractedPage(
                            page_number=index,
                            text=text,
                            char_count=char_count,
                            is_empty=char_count == 0,
                        )
                    )
                    if total_chars >= MAX_EXTRACTED_CHARS:
                        break

                return ExtractionResult(
                    mime_type=PDF_MIME,
                    pages=pages,
                    total_chars=total_chars,
                    warnings=warnings,
                    metadata={
                        "parser": "pdf",
                        "page_profiles": page_profiles_to_metadata(page_profiles),
                        "page_profile_summary": summarize_page_profiles(page_profiles),
                    },
                )
        except Exception:
            return ExtractionResult(mime_type=PDF_MIME, error=ExtractionError.PARSE_FAILED)
