from pathlib import Path

from parsers.base import BaseParser, ExtractedPage, ExtractionError, ExtractionResult, sanitize_text

TXT_MIME = "text/plain"
MAX_TXT_BYTES = 1024 * 1024


class TXTParser(BaseParser):
    def extract(self, path: Path) -> ExtractionResult:
        try:
            data = path.read_bytes()[:MAX_TXT_BYTES]
            try:
                raw = data.decode("utf-8")
            except UnicodeDecodeError:
                raw = data.decode("latin-1")
            text = sanitize_text(raw)
            char_count = len(text)
            page = ExtractedPage(
                page_number=1,
                text=text,
                char_count=char_count,
                is_empty=char_count == 0,
            )
            return ExtractionResult(
                mime_type=TXT_MIME,
                pages=[page],
                total_chars=char_count,
                error=ExtractionError.EMPTY_CONTENT if page.is_empty else None,
                metadata={"parser": "txt"},
            )
        except Exception:
            return ExtractionResult(mime_type=TXT_MIME, error=ExtractionError.PARSE_FAILED)
