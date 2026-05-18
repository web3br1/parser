from pathlib import Path

from parsers.base import ExtractionError
from parsers.txt import TXTParser


def test_good_txt_extracts(tmp_path: Path) -> None:
    path = tmp_path / "good.txt"
    path.write_text("Parágrafo um.\n\nParágrafo dois com mais conteúdo.", encoding="utf-8")
    result = TXTParser().extract(path)
    assert result.error is None
    assert result.total_chars > 0
    assert result.pages[0].page_number == 1


def test_empty_txt_returns_empty_content(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_bytes(b"")
    result = TXTParser().extract(path)
    assert result.error == ExtractionError.EMPTY_CONTENT
    assert result.pages[0].is_empty is True
