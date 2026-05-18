from pathlib import Path

import pytest
from parsers.base import ExtractionError
from parsers.docx import DOCXParser

docx = pytest.importorskip("docx")


def test_good_docx_extracts(tmp_path: Path) -> None:
    path = tmp_path / "good.docx"
    document = docx.Document()
    document.add_heading("Serviços", level=1)
    document.add_paragraph("Limpeza de pele custa R$120.")
    document.save(path)

    result = DOCXParser().extract(path)
    assert result.error is None
    assert result.total_chars > 0
    assert result.pages[0].page_number == 0
    assert "## Serviços" in result.pages[0].text


def test_corrupt_docx_parse_failed(tmp_path: Path) -> None:
    path = tmp_path / "bad.docx"
    path.write_text("not docx", encoding="utf-8")
    result = DOCXParser().extract(path)
    assert result.error == ExtractionError.PARSE_FAILED
