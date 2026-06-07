from __future__ import annotations

import importlib
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

TABLE_SPACED_COLUMNS_RE = re.compile(r"\s{2,}")
CAPTION_RE = re.compile(r"\b(?:Figura\s+\d+|Imagem(?:\s+\d+)?|Fluxograma|Anexo(?:\s+(?:[IVXLCDM]+|\d+))?)\b\s*[-–:]\s*\S", re.IGNORECASE)

LAYOUT_COMPLEXITY_VALUES = ("low", "medium", "high")
TEXT_LAYER_TYPE_VALUES = ("digital_text", "mixed", "scanned_image", "empty")
RISK_CODE_VALUES = (
    "empty_page",
    "ocr_required",
    "rotated_page",
    "high_layout_complexity",
    "table_candidates_present",
    "sparse_text_with_images",
    "visual_content_without_caption",
)


@dataclass(frozen=True)
class PageProfile:
    page_number: int
    text_chars: int
    has_text: bool
    line_count: int
    block_count: int
    image_count: int
    has_images: bool
    table_candidates: int
    ocr_required: bool
    ocr_risk: bool
    table_risk: bool
    text_layer_type: str
    layout_complexity: str
    rotation: int
    empty_page: bool
    header_detected: bool
    footer_detected: bool
    risk_codes: list[str]


def profile_pdf_pages(path: Path, *, max_pages: int | None = None) -> list[PageProfile]:
    fitz: Any = importlib.import_module("fitz")

    with fitz.open(path) as document:
        return profile_fitz_document(document, max_pages=max_pages)


def profile_fitz_document(document: Any, *, max_pages: int | None = None) -> list[PageProfile]:
    profiles: list[PageProfile] = []
    for page_index, page in enumerate(document, start=1):
        if max_pages is not None and page_index > max_pages:
            break
        profiles.append(_profile_page(page, page_index))
    return profiles


def page_profiles_to_metadata(profiles: Iterable[PageProfile]) -> list[dict[str, Any]]:
    return [asdict(profile) for profile in profiles]


def summarize_page_profiles(profiles: Iterable[PageProfile]) -> dict[str, Any]:
    profile_list = list(profiles)
    layout_counts = _stable_counts((profile.layout_complexity for profile in profile_list), LAYOUT_COMPLEXITY_VALUES)
    text_layer_counts = _stable_counts((profile.text_layer_type for profile in profile_list), TEXT_LAYER_TYPE_VALUES)
    risk_counts = _stable_counts(
        (risk_code for profile in profile_list for risk_code in profile.risk_codes),
        RISK_CODE_VALUES,
    )

    return {
        "page_count": len(profile_list),
        "text_pages": sum(1 for profile in profile_list if profile.has_text),
        "image_pages": sum(1 for profile in profile_list if profile.has_images),
        "ocr_required_pages": [profile.page_number for profile in profile_list if profile.ocr_required],
        "ocr_risk_pages": [profile.page_number for profile in profile_list if profile.ocr_risk],
        "empty_pages": [profile.page_number for profile in profile_list if profile.empty_page],
        "image_only_pages": [
            profile.page_number for profile in profile_list if profile.text_layer_type == "scanned_image"
        ],
        "table_candidate_pages": [
            profile.page_number for profile in profile_list if profile.table_candidates > 0
        ],
        "table_risk_pages": [profile.page_number for profile in profile_list if profile.table_risk],
        "header_detected_pages": [profile.page_number for profile in profile_list if profile.header_detected],
        "footer_detected_pages": [profile.page_number for profile in profile_list if profile.footer_detected],
        "layout_complexity_counts": layout_counts,
        "layout_complexity": dict(layout_counts),
        "text_layer_type_counts": text_layer_counts,
        "risk_code_counts": risk_counts,
        "risk_codes": dict(risk_counts),
    }


def _profile_page(page: Any, page_number: int) -> PageProfile:
    text = page.get_text("text") or ""
    text_chars = len(text)
    lines = [line for line in text.splitlines() if line.strip()]
    text_blocks = _text_blocks(page)
    image_count = len(page.get_images(full=True))
    table_candidates = _count_table_candidates(lines)
    rotation = int(getattr(page, "rotation", 0) or 0)
    ocr_required = text_chars == 0 and image_count > 0
    text_layer_type = _text_layer_type(text_chars=text_chars, image_count=image_count)
    layout_complexity = _layout_complexity(
        block_count=len(text_blocks),
        image_count=image_count,
        table_candidates=table_candidates,
        line_count=len(lines),
    )
    empty_page = text_chars == 0 and image_count == 0

    return PageProfile(
        page_number=page_number,
        text_chars=text_chars,
        has_text=text_chars > 0,
        line_count=len(lines),
        block_count=len(text_blocks),
        image_count=image_count,
        has_images=image_count > 0,
        table_candidates=table_candidates,
        ocr_required=ocr_required,
        ocr_risk=ocr_required,
        table_risk=table_candidates > 0,
        text_layer_type=text_layer_type,
        layout_complexity=layout_complexity,
        rotation=rotation,
        empty_page=empty_page,
        header_detected=_has_text_block_in_vertical_band(page, text_blocks, band="header"),
        footer_detected=_has_text_block_in_vertical_band(page, text_blocks, band="footer"),
        risk_codes=_risk_codes(
            empty_page=empty_page,
            ocr_required=ocr_required,
            rotation=rotation,
            layout_complexity=layout_complexity,
            table_candidates=table_candidates,
            text_chars=text_chars,
            image_count=image_count,
            text=text,
        ),
    )


def _text_layer_type(*, text_chars: int, image_count: int) -> str:
    if text_chars > 0 and image_count == 0:
        return "digital_text"
    if text_chars > 0 and image_count > 0:
        return "mixed"
    if text_chars == 0 and image_count > 0:
        return "scanned_image"
    return "empty"


def _layout_complexity(*, block_count: int, image_count: int, table_candidates: int, line_count: int) -> str:
    if block_count >= 8 or image_count >= 3 or table_candidates >= 2:
        return "high"
    if block_count >= 3 or image_count > 0 or table_candidates > 0 or line_count >= 8:
        return "medium"
    return "low"


def _risk_codes(
    *,
    empty_page: bool,
    ocr_required: bool,
    rotation: int,
    layout_complexity: str,
    table_candidates: int,
    text_chars: int,
    image_count: int,
    text: str,
) -> list[str]:
    risk_codes: list[str] = []
    if empty_page:
        risk_codes.append("empty_page")
    if ocr_required:
        risk_codes.append("ocr_required")
    if rotation % 360 != 0:
        risk_codes.append("rotated_page")
    if layout_complexity == "high":
        risk_codes.append("high_layout_complexity")
    if table_candidates > 0:
        risk_codes.append("table_candidates_present")
    if text_chars < 200 and image_count > 0:
        if text_chars > 0:
            risk_codes.append("sparse_text_with_images")
        if CAPTION_RE.search(text) is None:
            risk_codes.append("visual_content_without_caption")
    return risk_codes


def _count_table_candidates(lines: Iterable[str]) -> int:
    return sum(1 for line in lines if _is_table_candidate(line))


def _is_table_candidate(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.count("|") >= 2:
        return True
    columns = [column for column in TABLE_SPACED_COLUMNS_RE.split(stripped) if column]
    return len(columns) >= 3


def _text_blocks(page: Any) -> list[Any]:
    blocks: list[Any] = []
    for block in page.get_text("blocks") or []:
        text = _block_text(block)
        block_type = block[6] if len(block) > 6 else 0
        if block_type == 0 and text.strip():
            blocks.append(block)
    return blocks


def _block_text(block: Any) -> str:
    if len(block) <= 4:
        return ""
    text = block[4]
    return text if isinstance(text, str) else ""


def _has_text_block_in_vertical_band(page: Any, blocks: Iterable[Any], *, band: str) -> bool:
    height = float(page.rect.height)
    if height <= 0:
        return False
    header_limit = height * 0.15
    footer_limit = height * 0.85

    for block in blocks:
        y0 = float(block[1])
        y1 = float(block[3])
        if band == "header" and y0 <= header_limit:
            return True
        if band == "footer" and y1 >= footer_limit:
            return True
    return False


def _stable_counts(values: Iterable[str], stable_keys: Iterable[str]) -> dict[str, int]:
    counts = Counter(values)
    result = {key: counts.pop(key, 0) for key in stable_keys}
    result.update(dict(sorted(counts.items())))
    return result
