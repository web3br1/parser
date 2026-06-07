import base64
from pathlib import Path

import pytest
from parsers.page_profile import (
    PageProfile,
    page_profiles_to_metadata,
    profile_fitz_document,
    profile_pdf_pages,
    summarize_page_profiles,
)

fitz = pytest.importorskip("fitz")

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def test_text_page_detects_header_footer_and_table_candidate(tmp_path: Path) -> None:
    path = tmp_path / "text_profile.pdf"
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((72, 40), "Procedure Header")
    page.insert_text((72, 160), "Step    Owner    Status")
    page.insert_text((72, 220), "Body line one")
    page.insert_text((72, 760), "Footer rev 01")
    document.save(path)
    document.close()

    profiles = profile_pdf_pages(path)

    assert len(profiles) == 1
    profile = profiles[0]
    assert profile.page_number == 1
    assert profile.text_chars > 0
    assert profile.has_text is True
    assert profile.line_count == 4
    assert profile.block_count >= 4
    assert profile.table_candidates == 1
    assert profile.has_images is False
    assert profile.ocr_required is False
    assert profile.ocr_risk is False
    assert profile.table_risk is True
    assert profile.text_layer_type == "digital_text"
    assert profile.header_detected is True
    assert profile.footer_detected is True
    assert profile.empty_page is False
    assert "table_candidates_present" in profile.risk_codes


def test_image_only_page_requires_ocr(tmp_path: Path) -> None:
    path = tmp_path / "image_only.pdf"
    document = fitz.open()
    page = document.new_page(width=200, height=200)
    page.insert_image(fitz.Rect(72, 72, 73, 73), stream=PNG_1X1)
    document.save(path)
    document.close()

    profile = profile_pdf_pages(path)[0]

    assert profile.image_count == 1
    assert profile.has_images is True
    assert profile.text_chars == 0
    assert profile.has_text is False
    assert profile.empty_page is False
    assert profile.ocr_required is True
    assert profile.ocr_risk is True
    assert profile.table_risk is False
    assert profile.text_layer_type == "scanned_image"
    assert "ocr_required" in profile.risk_codes
    assert "visual_content_without_caption" in profile.risk_codes


def test_sparse_text_with_images_marks_visual_content_risk(tmp_path: Path) -> None:
    path = tmp_path / "sparse_visual.pdf"
    document = fitz.open()
    page = document.new_page(width=300, height=300)
    page.insert_text((72, 72), "Ver figura.")
    page.insert_image(fitz.Rect(72, 120, 73, 121), stream=PNG_1X1)
    document.save(path)
    document.close()

    profile = profile_pdf_pages(path)[0]

    assert "sparse_text_with_images" in profile.risk_codes
    assert "visual_content_without_caption" in profile.risk_codes


def test_sparse_text_with_caption_does_not_mark_visual_content_risk(tmp_path: Path) -> None:
    path = tmp_path / "captioned_visual.pdf"
    document = fitz.open()
    page = document.new_page(width=300, height=300)
    page.insert_text((72, 72), "Figura 1 - Painel eletrico.")
    page.insert_image(fitz.Rect(72, 120, 73, 121), stream=PNG_1X1)
    document.save(path)
    document.close()

    profile = profile_pdf_pages(path)[0]

    assert "sparse_text_with_images" in profile.risk_codes
    assert "visual_content_without_caption" not in profile.risk_codes


def test_summarize_page_profiles_for_mixed_pdf(tmp_path: Path) -> None:
    path = tmp_path / "mixed.pdf"
    document = fitz.open()
    page = document.new_page(width=200, height=200)
    page.insert_text((72, 72), "Digital text")
    page = document.new_page(width=200, height=200)
    page.insert_image(fitz.Rect(72, 72, 73, 73), stream=PNG_1X1)
    document.save(path)
    document.close()

    profiles = profile_pdf_pages(path)
    summary = summarize_page_profiles(profiles)

    assert type(summary) is dict
    assert summary["page_count"] == 2
    assert summary["ocr_required_pages"] == [2]
    assert summary["empty_pages"] == []
    assert summary["image_only_pages"] == [2]
    assert summary["text_pages"] == 1
    assert summary["image_pages"] == 1
    assert summary["ocr_risk_pages"] == [2]
    assert summary["table_risk_pages"] == []
    assert summary["header_detected_pages"] == []
    assert summary["footer_detected_pages"] == []
    assert summary["layout_complexity"] == summary["layout_complexity_counts"]
    assert summary["layout_complexity"] is not summary["layout_complexity_counts"]
    assert summary["risk_codes"] == summary["risk_code_counts"]
    assert summary["risk_codes"] is not summary["risk_code_counts"]
    assert summary["risk_code_counts"]["ocr_required"] == 1
    assert "visual_content_without_caption" in summary["risk_code_counts"]


def test_profile_fitz_document_limits_pages_and_metadata_is_stable() -> None:
    document = fitz.open()
    page = document.new_page(width=200, height=200)
    page.insert_text((72, 72), "First page")
    page = document.new_page(width=200, height=200)
    page.insert_text((72, 72), "Second page")

    profiles = profile_fitz_document(document, max_pages=1)
    metadata = page_profiles_to_metadata(profiles)

    assert len(profiles) == 1
    assert isinstance(profiles[0], PageProfile)
    assert set(metadata[0]) == {
        "page_number",
        "text_chars",
        "line_count",
        "block_count",
        "image_count",
        "has_text",
        "has_images",
        "table_candidates",
        "ocr_required",
        "ocr_risk",
        "table_risk",
        "text_layer_type",
        "layout_complexity",
        "rotation",
        "empty_page",
        "header_detected",
        "footer_detected",
        "risk_codes",
    }
    assert metadata[0]["page_number"] == 1
    assert metadata[0]["text_layer_type"] == "digital_text"
    assert metadata[0]["risk_codes"] == profiles[0].risk_codes
