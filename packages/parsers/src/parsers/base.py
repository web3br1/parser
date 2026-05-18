from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class ExtractionError(StrEnum):
    PAGES_EXCEEDED = "pages_exceeded"
    ROWS_EXCEEDED = "rows_exceeded"
    UNSUPPORTED_FORMAT = "unsupported_format"
    EMPTY_CONTENT = "empty_content"
    PARSE_FAILED = "parse_failed"


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str
    char_count: int
    is_empty: bool


@dataclass(frozen=True)
class ExtractedSheet:
    sheet_name: str
    headers: list[str]
    rows: list[dict[str, str]]
    row_start: int
    row_end: int


@dataclass
class ExtractionResult:
    mime_type: str
    pages: list[ExtractedPage] = field(default_factory=list)
    sheets: list[ExtractedSheet] = field(default_factory=list)
    total_chars: int = 0
    error: ExtractionError | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseParser(ABC):
    @abstractmethod
    def extract(self, path: Path) -> ExtractionResult:
        raise NotImplementedError


MAX_EXTRACTED_CHARS: int = 500_000


def sanitize_text(text: str) -> str:
    return text.encode("utf-8", errors="ignore").decode("utf-8").strip()


def truncate_to_limit(text: str, current_total: int) -> tuple[str, bool]:
    remaining = MAX_EXTRACTED_CHARS - current_total
    if remaining <= 0:
        return "", True
    if len(text) > remaining:
        return text[:remaining], True
    return text, False
