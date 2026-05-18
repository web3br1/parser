from parsers.base import BaseParser, ExtractionError
from parsers.csv_parser import CSVParser
from parsers.docx import DOCXParser
from parsers.pdf import PDFParser
from parsers.txt import TXTParser
from parsers.xlsx_parser import XLSXParser


class UnsupportedMimeError(Exception):
    def __init__(self, mime: str) -> None:
        super().__init__(f"Unsupported MIME type: {mime!r}")
        self.mime = mime


_PARSER_MAP: dict[str, BaseParser] = {
    "application/pdf": PDFParser(),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DOCXParser(),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": XLSXParser(),
    "text/csv": CSVParser(),
    "text/plain": TXTParser(),
}


def get_parser(mime: str) -> BaseParser:
    if mime not in _PARSER_MAP:
        raise UnsupportedMimeError(mime)
    return _PARSER_MAP[mime]


__all__ = ["BaseParser", "ExtractionError", "UnsupportedMimeError", "get_parser"]
