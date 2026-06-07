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


def test_pdf_parser_adds_page_profile_metadata(tmp_path: Path) -> None:
    path = tmp_path / "profiled.pdf"
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((72, 72), "Procedure ABC")
    page.insert_text((72, 120), "Step    Owner    Status")
    document.save(path)

    result = PDFParser().extract(path)

    assert result.error is None
    assert result.metadata["parser"] == "pdf"
    page_profiles = result.metadata["page_profiles"]
    assert len(page_profiles) == 1
    profile = page_profiles[0]
    assert profile["page_number"] == 1
    assert profile["text_chars"] > 0
    assert profile["line_count"] == 2
    assert profile["block_count"] == 2
    assert profile["image_count"] == 0
    assert profile["table_candidates"] == 1
    assert profile["ocr_required"] is False
    assert profile["text_layer_type"] == "digital_text"
    assert profile["layout_complexity"] == "medium"
    assert profile["rotation"] == 0
    assert profile["empty_page"] is False
    assert profile["header_detected"] is True
    assert profile["footer_detected"] is False
    assert profile["risk_codes"] == ["table_candidates_present"]
    assert result.metadata["page_profile_summary"] == {
        "page_count": 1,
        "text_pages": 1,
        "image_pages": 0,
        "ocr_required_pages": [],
        "ocr_risk_pages": [],
        "empty_pages": [],
        "image_only_pages": [],
        "table_candidate_pages": [1],
        "table_risk_pages": [1],
        "header_detected_pages": [1],
        "footer_detected_pages": [],
        "layout_complexity_counts": {"low": 0, "medium": 1, "high": 0},
        "layout_complexity": {"low": 0, "medium": 1, "high": 0},
        "text_layer_type_counts": {"digital_text": 1, "mixed": 0, "scanned_image": 0, "empty": 0},
        "risk_code_counts": {
            "empty_page": 0,
            "ocr_required": 0,
            "rotated_page": 0,
            "high_layout_complexity": 0,
            "table_candidates_present": 1,
            "sparse_text_with_images": 0,
            "visual_content_without_caption": 0,
        },
        "risk_codes": {
            "empty_page": 0,
            "ocr_required": 0,
            "rotated_page": 0,
            "high_layout_complexity": 0,
            "table_candidates_present": 1,
            "sparse_text_with_images": 0,
            "visual_content_without_caption": 0,
        },
    }


def test_pdf_parser_adds_section_diagnostics_without_changing_text(tmp_path: Path) -> None:
    path = tmp_path / "sectioned.pdf"
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((72, 40), "ACME QMS Manual")
    page.insert_text((72, 120), "1 Objetivo")
    page.insert_text((72, 160), "Definir controles do procedimento.")
    page.insert_text((72, 760), "Pagina 1 de 2")
    page = document.new_page(width=600, height=800)
    page.insert_text((72, 40), "ACME QMS Manual")
    page.insert_text((72, 120), "1.1 Aplicacao")
    page.insert_text((72, 160), "Aplica-se a producao industrial.")
    page.insert_text((72, 760), "Pagina 2 de 2")
    document.save(path)

    result = PDFParser().extract(path)

    assert result.error is None
    assert "ACME QMS Manual" in result.pages[0].text
    assert "Pagina 1 de 2" in result.pages[0].text
    diagnostics = result.metadata["section_diagnostics"]
    assert diagnostics["summary"]["section_count"] == 2
    assert diagnostics["summary"]["boilerplate_counts"] == {"footer": 2, "header": 2}
    assert [
        (span["section_path"], span["section_title"], span["page_start"], span["page_end"])
        for span in diagnostics["section_spans"]
    ] == [
        ("1", "Objetivo", 1, 1),
        ("1/1.1", "Aplicacao", 2, 2),
    ]


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
