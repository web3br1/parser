from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from parsers.base import sanitize_text
from parsers.chunker import RawChunk

TABLE_SPACED_COLUMNS_RE = re.compile(r"\s{2,}")
CHECKLIST_RE = re.compile(r"^\s*\[(?P<mark>[ xX])\]\s*(?P<label>.+?)(?:\s*[-–:]\s*(?P<status>.+))?\s*$")
FIGURE_RE = re.compile(
    r"\b(?P<label>Figura\s+\d+|Imagem(?:\s+\d+)?|Fluxograma|Anexo(?:\s+(?:[IVXLCDM]+|\d+))?)\b\s*[-–:]?\s*(?P<caption>.*)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class IndustrialTableFigureCandidate:
    candidate_id: str
    kind: str
    quote: str
    page_number: int | None
    section_path: str | None
    confidence: float
    normalized_content: dict[str, Any]
    risk_codes: tuple[str, ...] = ()


def extract_table_figure_candidates(
    chunks: list[RawChunk],
    *,
    page_profiles: list[dict[str, Any]] | None = None,
) -> list[IndustrialTableFigureCandidate]:
    candidates: list[IndustrialTableFigureCandidate] = []
    for chunk in chunks:
        candidates.extend(_chunk_candidates(chunk))
    candidates.extend(_visual_risk_candidates(page_profiles or [], candidates))
    return candidates


def summarize_table_figure_candidates(
    candidates: list[IndustrialTableFigureCandidate],
) -> dict[str, Any]:
    kind_counts = Counter(candidate.kind for candidate in candidates)
    risk_counts = Counter(risk for candidate in candidates for risk in candidate.risk_codes)
    return {
        "total_candidate_count": len(candidates),
        "candidate_kind_counts": dict(sorted(kind_counts.items())),
        "risk_code_counts": dict(sorted(risk_counts.items())),
    }


def table_figure_candidates_to_metadata(
    candidates: list[IndustrialTableFigureCandidate],
) -> list[dict[str, Any]]:
    return [
        {
            **asdict(candidate),
            "risk_codes": list(candidate.risk_codes),
        }
        for candidate in candidates
    ]


def _chunk_candidates(chunk: RawChunk) -> list[IndustrialTableFigureCandidate]:
    candidates: list[IndustrialTableFigureCandidate] = []
    lines = [sanitize_text(line) for line in chunk.text.splitlines() if sanitize_text(line)]
    candidates.extend(_table_candidates(chunk, lines))
    for line_index, line in enumerate(lines):
        checklist = CHECKLIST_RE.match(line)
        if checklist:
            status = sanitize_text(checklist.group("status") or "")
            candidates.append(
                _candidate(
                    chunk=chunk,
                    kind="checklist_row",
                    quote=line,
                    confidence=0.76,
                    normalized_content={
                        "label": sanitize_text(checklist.group("label")),
                        "status": _checklist_status(checklist.group("mark"), status),
                    },
                    suffix=f"checklist:{line_index}",
                )
            )
            continue
        figure = FIGURE_RE.search(line)
        if figure:
            candidates.append(
                _candidate(
                    chunk=chunk,
                    kind="figure_reference",
                    quote=line,
                    confidence=0.74,
                    normalized_content={
                        "label": sanitize_text(figure.group("label")),
                        "caption": sanitize_text(figure.group("caption")),
                    },
                    suffix=f"figure:{line_index}",
                )
            )
    return candidates


def _table_candidates(chunk: RawChunk, lines: list[str]) -> list[IndustrialTableFigureCandidate]:
    table_lines = [line for line in lines if _is_table_line(line)]
    if not table_lines:
        return []
    quote = "\n".join(table_lines[:5])
    return [
        _candidate(
            chunk=chunk,
            kind="text_table",
            quote=quote,
            confidence=0.72,
            normalized_content={"row_count": len(table_lines), "preview": quote},
            suffix="table:0",
        )
    ]


def _visual_risk_candidates(
    page_profiles: list[dict[str, Any]],
    existing: list[IndustrialTableFigureCandidate],
) -> list[IndustrialTableFigureCandidate]:
    caption_pages = {
        candidate.page_number
        for candidate in existing
        if candidate.kind == "figure_reference"
        and candidate.page_number is not None
        and _has_strong_caption(candidate)
    }
    risks: list[IndustrialTableFigureCandidate] = []
    for profile in page_profiles:
        page_number = _safe_int(profile.get("page_number"))
        if page_number is None or page_number in caption_pages:
            continue
        risk_codes = {str(code) for code in profile.get("risk_codes", [])}
        image_count = _safe_int(profile.get("image_count")) or 0
        text_chars = _safe_int(profile.get("text_chars")) or 0
        if "visual_content_without_caption" in risk_codes or (image_count > 0 and text_chars < 200):
            risk_codes.add("visual_content_without_caption")
            quote = f"page {page_number} contains visual content without extractable caption"
            risks.append(
                IndustrialTableFigureCandidate(
                    candidate_id=f"page:{page_number}:visual_risk",
                    kind="visual_risk",
                    quote=quote,
                    page_number=page_number,
                    section_path=None,
                    confidence=0.6,
                    normalized_content={"image_count": image_count, "text_chars": text_chars},
                    risk_codes=tuple(sorted(risk_codes)),
                )
            )
    return risks


def _candidate(
    *,
    chunk: RawChunk,
    kind: str,
    quote: str,
    confidence: float,
    normalized_content: dict[str, Any],
    suffix: str,
) -> IndustrialTableFigureCandidate:
    return IndustrialTableFigureCandidate(
        candidate_id=f"{chunk.chunk_hash}:{chunk.page_start or chunk.source_page}:{chunk.section_path or 'unsectioned'}:{suffix}",
        kind=kind,
        quote=quote,
        page_number=chunk.page_start or chunk.source_page,
        section_path=chunk.section_path,
        confidence=confidence,
        normalized_content=normalized_content,
    )


def _is_table_line(line: str) -> bool:
    if line.count("|") >= 2:
        return True
    columns = [column for column in TABLE_SPACED_COLUMNS_RE.split(line.strip()) if column]
    return len(columns) >= 3


def _has_strong_caption(candidate: IndustrialTableFigureCandidate) -> bool:
    caption = str(candidate.normalized_content.get("caption") or "").strip()
    caption_key = caption.casefold()
    weak_caption_markers = (
        "area reservada",
        "sem legenda",
        "imagem sem legenda",
        "placeholder",
        "apenas referencia",
    )
    if any(marker in caption_key for marker in weak_caption_markers):
        return False
    return (
        bool(caption)
        and any(character.isalnum() for character in caption)
        and not caption.casefold().startswith(("ver ", "vide "))
    )


def _checklist_status(mark: str, status: str) -> str:
    if status:
        return status.casefold()
    return "checked" if mark.strip().casefold() == "x" else "unchecked"


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
