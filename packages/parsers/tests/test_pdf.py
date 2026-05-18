from pathlib import Path

import pytest
from parsers.base import ExtractionError
from parsers.pdf import PDFParser

fitz = pytest.importorskip("fitz")


def test_good_pdf_extracts(tmp_path: Path) -> None:
    path = tmp_path / "good.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Limpeza de pele custa R$120." * 10)
    document.save(path)

    result = PDFParser().extract(path)
    assert result.error is None
    assert result.total_chars > 0
    assert result.pages[0].page_number == 1


def test_image_only_pdf_keeps_empty_page(tmp_path: Path) -> None:
    path = tmp_path / "image_only.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)

    result = PDFParser().extract(path)
    assert result.error is None
    assert result.pages
    assert all(page.is_empty for page in result.pages)


def test_pdf_pages_exceeded(tmp_path: Path) -> None:
    path = tmp_path / "too_many.pdf"
    document = fitz.open()
    for _ in range(201):
        document.new_page()
    document.save(path)

    result = PDFParser().extract(path)
    assert result.error == ExtractionError.PAGES_EXCEEDED


def test_corrupt_pdf_parse_failed(tmp_path: Path) -> None:
    path = tmp_path / "bad.pdf"
    path.write_text("not pdf", encoding="utf-8")
    result = PDFParser().extract(path)
    assert result.error == ExtractionError.PARSE_FAILED
