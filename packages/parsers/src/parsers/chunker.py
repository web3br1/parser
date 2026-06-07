from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from parsers.base import ExtractedPage, ExtractedSheet, ExtractionResult, sanitize_text

MAX_TOKENS = 800
OVERLAP_TOKENS = 100
MIN_CHUNK_CHARS = 50
SHEET_BLOCK_SIZE = 15


@dataclass(frozen=True)
class RawChunk:
    chunk_index: int
    text: str
    char_count: int
    token_estimate: int
    chunk_hash: str
    source_page: int | None
    sheet_name: str | None
    row_start: int | None
    row_end: int | None
    section_heading: str | None
    metadata: dict[str, object]
    page_start: int | None = None
    page_end: int | None = None
    section_path: str | None = None
    section_title: str | None = None
    chunk_kind: str | None = None
    structure_risk_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ChunkDraft:
    text: str
    source_page: int | None
    sheet_name: str | None
    row_start: int | None
    row_end: int | None
    section_heading: str | None
    order: tuple[int, int, int]
    page_start: int | None = None
    page_end: int | None = None
    section_path: str | None = None
    section_title: str | None = None
    chunk_kind: str | None = None
    structure_risk_codes: tuple[str, ...] = ()


def chunk_extraction(
    result: ExtractionResult,
    *,
    source_version: int = 1,
    industrial_context: dict[str, Any] | None = None,
) -> list[RawChunk]:
    if result.error is not None:
        return []

    parser_name = _parser_name(result)
    timestamp = datetime.now(UTC).isoformat()
    metadata = {
        "parser": parser_name,
        "source_version": source_version,
        "extraction_timestamp": timestamp,
    }

    effective_industrial_context = _effective_industrial_context(result, industrial_context)
    if effective_industrial_context is not None and result.pages:
        drafts = _chunk_industrial_pages(result.pages, effective_industrial_context)
        if not drafts:
            drafts = _chunk_generic_content(result)
    else:
        drafts = _chunk_generic_content(result)

    merged = _merge_short_chunks(drafts)
    ordered = sorted(merged, key=lambda draft: draft.order)
    return [_finalize_chunk(index, draft, metadata) for index, draft in enumerate(ordered)]


def _chunk_generic_content(result: ExtractionResult) -> list[_ChunkDraft]:
    drafts: list[_ChunkDraft] = []
    for page_order, page in enumerate(result.pages):
        drafts.extend(_chunk_page(page, page_order))
    for sheet_order, sheet in enumerate(result.sheets):
        drafts.extend(_chunk_sheet(sheet, sheet_order))
    return drafts


def _effective_industrial_context(
    result: ExtractionResult,
    industrial_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if industrial_context is not None:
        return industrial_context
    section_diagnostics = result.metadata.get("section_diagnostics")
    return section_diagnostics if isinstance(section_diagnostics, dict) else None


def _parser_name(result: ExtractionResult) -> str:
    if "parser" in result.metadata:
        return str(result.metadata["parser"])
    return {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "text/csv": "csv",
        "text/plain": "txt",
    }.get(result.mime_type, "txt")


def _chunk_page(page: ExtractedPage, page_order: int) -> list[_ChunkDraft]:
    sections = _split_sections(page.text)
    drafts: list[_ChunkDraft] = []
    for section_order, (heading, text) in enumerate(sections):
        for block_order, block in enumerate(_split_text_block(text)):
            drafts.append(
                _ChunkDraft(
                    text=block,
                    source_page=page.page_number,
                    sheet_name=None,
                    row_start=None,
                    row_end=None,
                    section_heading=heading,
                    order=(page_order, section_order, block_order),
                )
            )
    return drafts


def _chunk_industrial_pages(
    pages: list[ExtractedPage],
    industrial_context: dict[str, Any],
) -> list[_ChunkDraft]:
    section_spans = _normalized_section_spans(industrial_context.get("section_spans"))
    if not section_spans:
        return []

    page_lines = {
        page.page_number: page.text.splitlines()
        for page in pages
    }
    boilerplate_positions = {
        (page_number, line_index)
        for span in _context_list(industrial_context.get("boilerplate_spans"))
        if (page_number := _safe_int(span.get("page_number"))) is not None
        and (line_index := _safe_int(span.get("line_index"))) is not None
    }
    sorted_spans = sorted(
        section_spans,
        key=lambda span: (
            span["page_start"],
            span["line_index"],
            span["section_path"],
        ),
    )
    drafts: list[_ChunkDraft] = []
    for span_index, span in enumerate(sorted_spans):
        page_start = span["page_start"]
        page_end = span["page_end"]
        next_span = sorted_spans[span_index + 1] if span_index + 1 < len(sorted_spans) else None
        text = _section_text(
            page_lines=page_lines,
            boilerplate_positions=boilerplate_positions,
            span=span,
            next_span=next_span,
            page_start=page_start,
            page_end=page_end,
        )
        if not text:
            continue
        for block_order, block in enumerate(_split_text_block(text)):
            drafts.append(
                _ChunkDraft(
                    text=block,
                    source_page=page_start,
                    sheet_name=None,
                    row_start=None,
                    row_end=None,
                    section_heading=span["section_title"],
                    order=(page_start - 1, span["line_index"], block_order),
                    page_start=page_start,
                    page_end=page_end,
                    section_path=span["section_path"],
                    section_title=span["section_title"],
                    chunk_kind=span["kind"],
                    structure_risk_codes=span["risk_codes"],
                )
            )
    return drafts


def _section_text(
    *,
    page_lines: dict[int, list[str]],
    boilerplate_positions: set[tuple[int, int]],
    span: dict[str, Any],
    next_span: dict[str, Any] | None,
    page_start: int,
    page_end: int,
) -> str:
    start_line = int(span.get("line_index") or 0)
    next_page = int(next_span.get("page_start") or next_span.get("page_number") or 0) if next_span else None
    next_line = int(next_span.get("line_index") or 0) if next_span else None
    selected: list[str] = []
    for page_number in range(page_start, page_end + 1):
        lines = page_lines.get(page_number, [])
        if not lines:
            continue
        line_start = start_line if page_number == page_start else 0
        line_end = len(lines)
        if next_page == page_number and next_line is not None:
            line_end = min(line_end, next_line)
        for line_index in range(line_start, line_end):
            if (page_number, line_index) in boilerplate_positions:
                continue
            line = sanitize_text(lines[line_index])
            if line:
                selected.append(line)
    return sanitize_text("\n".join(selected))


def _context_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _normalized_section_spans(value: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for span in _context_list(value):
        page_start = _safe_int(span.get("page_start")) or _safe_int(span.get("page_number"))
        line_index = _safe_int(span.get("line_index"))
        if page_start is None or line_index is None:
            continue
        section_path = _optional_string(span.get("section_path"))
        section_title = _optional_string(span.get("section_title")) or _optional_string(span.get("title"))
        kind = _optional_string(span.get("kind"))
        if section_path is None or section_title is None or kind is None:
            continue
        page_end = _safe_int(span.get("page_end")) or page_start
        normalized.append(
            {
                "kind": kind,
                "line_index": line_index,
                "page_start": page_start,
                "page_end": page_end,
                "section_path": section_path,
                "section_title": section_title,
                "risk_codes": _risk_codes(span.get("risk_codes")),
            }
        )
    return normalized


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _risk_codes(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(sorted({str(item) for item in value if str(item)}))


def _split_sections(text: str) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, list[str]]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        clean = sanitize_text(line)
        if not clean:
            current_lines.append("")
            continue
        if _is_heading(clean):
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = clean.lstrip("#").strip()
            current_lines = []
            continue
        current_lines.append(clean)

    if current_lines:
        sections.append((current_heading, current_lines))

    normalized_sections = []
    for heading, lines in sections:
        joined = "\n".join(lines)
        if joined.strip():
            normalized_sections.append((heading, sanitize_text(joined)))
    return normalized_sections


def _is_heading(line: str) -> bool:
    return line.startswith("#") or (len(line) <= 60 and line.isupper() and any(c.isalpha() for c in line))


def _split_text_block(text: str) -> list[str]:
    if _token_estimate(text) <= MAX_TOKENS:
        return [text] if text.strip() else []

    blocks: list[str] = []
    paragraphs = [paragraph for paragraph in text.split("\n\n") if paragraph.strip()]
    for paragraph in paragraphs:
        if _token_estimate(paragraph) <= MAX_TOKENS:
            blocks.append(sanitize_text(paragraph))
        else:
            blocks.extend(_window_text(paragraph))
    return blocks


def _window_text(text: str) -> list[str]:
    max_chars = MAX_TOKENS * 4
    overlap_chars = OVERLAP_TOKENS * 4
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunks.append(sanitize_text(text[start:end]))
        if end == len(text):
            break
        start = max(0, end - overlap_chars)
    return [chunk for chunk in chunks if chunk]


def _chunk_sheet(sheet: ExtractedSheet, sheet_order: int) -> list[_ChunkDraft]:
    drafts: list[_ChunkDraft] = []
    for offset in range(0, len(sheet.rows), SHEET_BLOCK_SIZE):
        block = sheet.rows[offset : offset + SHEET_BLOCK_SIZE]
        if not block:
            continue
        row_start = sheet.row_start + offset
        row_end = row_start + len(block) - 1
        drafts.append(
            _ChunkDraft(
                text=_sheet_block_text(sheet, block),
                source_page=None,
                sheet_name=sheet.sheet_name,
                row_start=row_start,
                row_end=row_end,
                section_heading=None,
                order=(sheet_order, row_start, row_end),
            )
        )
    return drafts


def _sheet_block_text(sheet: ExtractedSheet, rows: list[dict[str, str]]) -> str:
    header_line = "| " + " | ".join(sheet.headers) + " |"
    data_lines = []
    for row in rows:
        values = [sanitize_text(row.get(header, "")) for header in sheet.headers]
        data_lines.append("| " + " | ".join(values) + " |")
    return sanitize_text("\n".join([f"Tabela: {sheet.sheet_name}", header_line, *data_lines]))


def _merge_short_chunks(drafts: list[_ChunkDraft]) -> list[_ChunkDraft]:
    merged: list[_ChunkDraft] = []
    index = 0
    while index < len(drafts):
        current = drafts[index]
        if len(current.text) >= MIN_CHUNK_CHARS or index == len(drafts) - 1:
            if current.text.strip():
                merged.append(current)
            index += 1
            continue

        nxt = drafts[index + 1]
        if current.section_path != nxt.section_path:
            if current.text.strip():
                merged.append(current)
            index += 1
            continue
        combined = _ChunkDraft(
            text=sanitize_text(f"{current.text}\n\n{nxt.text}"),
            source_page=current.source_page,
            sheet_name=current.sheet_name or nxt.sheet_name,
            row_start=current.row_start or nxt.row_start,
            row_end=nxt.row_end or current.row_end,
            section_heading=current.section_heading or nxt.section_heading,
            order=current.order,
            page_start=current.page_start or nxt.page_start,
            page_end=nxt.page_end or current.page_end,
            section_path=current.section_path or nxt.section_path,
            section_title=current.section_title or nxt.section_title,
            chunk_kind=current.chunk_kind or nxt.chunk_kind,
            structure_risk_codes=tuple(sorted({
                *current.structure_risk_codes,
                *nxt.structure_risk_codes,
            })),
        )
        drafts[index + 1] = combined
        index += 1
    return merged


def _finalize_chunk(index: int, draft: _ChunkDraft, metadata: dict[str, object]) -> RawChunk:
    text = sanitize_text(draft.text)
    chunk_metadata = dict(metadata)
    if draft.page_start is not None:
        chunk_metadata["page_start"] = draft.page_start
    if draft.page_end is not None:
        chunk_metadata["page_end"] = draft.page_end
    if draft.section_path is not None:
        chunk_metadata["section_path"] = draft.section_path
    if draft.section_title is not None:
        chunk_metadata["section_title"] = draft.section_title
    if draft.chunk_kind is not None:
        chunk_metadata["chunk_kind"] = draft.chunk_kind
    if draft.structure_risk_codes:
        chunk_metadata["structure_risk_codes"] = list(draft.structure_risk_codes)
    return RawChunk(
        chunk_index=index,
        text=text,
        char_count=len(text),
        token_estimate=_token_estimate(text),
        chunk_hash=sha256(text.encode()).hexdigest(),
        source_page=draft.source_page,
        sheet_name=draft.sheet_name,
        row_start=draft.row_start,
        row_end=draft.row_end,
        section_heading=draft.section_heading,
        metadata=chunk_metadata,
        page_start=draft.page_start,
        page_end=draft.page_end,
        section_path=draft.section_path,
        section_title=draft.section_title,
        chunk_kind=draft.chunk_kind,
        structure_risk_codes=draft.structure_risk_codes,
    )


def _token_estimate(text: str) -> int:
    return len(text) // 4
