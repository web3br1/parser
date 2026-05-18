import csv
from pathlib import Path

from parsers.base import (
    BaseParser,
    ExtractedSheet,
    ExtractionError,
    ExtractionResult,
    sanitize_text,
)

CSV_MIME = "text/csv"
MAX_ROWS = 10_000


class CSVParser(BaseParser):
    def extract(self, path: Path) -> ExtractionResult:
        try:
            text = _read_csv_text(path)
            lines = text.splitlines()
            if len(lines) <= 1:
                return ExtractionResult(mime_type=CSV_MIME, error=ExtractionError.EMPTY_CONTENT)
            if len(lines) - 1 > MAX_ROWS:
                return ExtractionResult(mime_type=CSV_MIME, error=ExtractionError.ROWS_EXCEEDED)

            sample = text[:2048]
            dialect = _detect_dialect(sample)
            reader = csv.reader(lines, dialect)
            rows = list(reader)
            if len(rows) <= 1:
                return ExtractionResult(mime_type=CSV_MIME, error=ExtractionError.EMPTY_CONTENT)
            if len(rows) - 1 > MAX_ROWS:
                return ExtractionResult(mime_type=CSV_MIME, error=ExtractionError.ROWS_EXCEEDED)

            headers = [sanitize_text(cell) for cell in rows[0]]
            records: list[dict[str, str]] = []
            for row in rows[1:]:
                padded = [sanitize_text(cell) for cell in row] + [""] * max(0, len(headers) - len(row))
                records.append(dict(zip(headers, padded, strict=False)))

            total_chars = sum(len(value) for record in records for value in record.values())
            sheet = ExtractedSheet(
                sheet_name="sheet1",
                headers=headers,
                rows=records,
                row_start=2,
                row_end=len(rows),
            )
            return ExtractionResult(
                mime_type=CSV_MIME,
                sheets=[sheet],
                total_chars=total_chars,
                metadata={"parser": "csv"},
            )
        except Exception:
            return ExtractionResult(mime_type=CSV_MIME, error=ExtractionError.PARSE_FAILED)


def _read_csv_text(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _detect_dialect(sample: str) -> type[csv.Dialect]:
    if not sample.strip():
        return csv.excel
    try:
        return csv.Sniffer().sniff(sample)
    except csv.Error:
        return csv.excel
