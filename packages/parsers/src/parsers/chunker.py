from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

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


@dataclass(frozen=True)
class _ChunkDraft:
    text: str
    source_page: int | None
    sheet_name: str | None
    row_start: int | None
    row_end: int | None
    section_heading: str | None
    order: tuple[int, int, int]


def chunk_extraction(result: ExtractionResult, *, source_version: int = 1) -> list[RawChunk]:
    if result.error is not None:
        return []

    parser_name = _parser_name(result)
    timestamp = datetime.now(UTC).isoformat()
    metadata = {
        "parser": parser_name,
        "source_version": source_version,
        "extraction_timestamp": timestamp,
    }

    drafts: list[_ChunkDraft] = []
    for page_order, page in enumerate(result.pages):
        drafts.extend(_chunk_page(page, page_order))
    for sheet_order, sheet in enumerate(result.sheets):
        drafts.extend(_chunk_sheet(sheet, sheet_order))

    merged = _merge_short_chunks(drafts)
    ordered = sorted(merged, key=lambda draft: draft.order)
    return [_finalize_chunk(index, draft, metadata) for index, draft in enumerate(ordered)]


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
        combined = _ChunkDraft(
            text=sanitize_text(f"{current.text}\n\n{nxt.text}"),
            source_page=current.source_page,
            sheet_name=current.sheet_name or nxt.sheet_name,
            row_start=current.row_start or nxt.row_start,
            row_end=nxt.row_end or current.row_end,
            section_heading=current.section_heading or nxt.section_heading,
            order=current.order,
        )
        drafts[index + 1] = combined
        index += 1
    return merged


def _finalize_chunk(index: int, draft: _ChunkDraft, metadata: dict[str, object]) -> RawChunk:
    text = sanitize_text(draft.text)
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
        metadata=dict(metadata),
    )


def _token_estimate(text: str) -> int:
    return len(text) // 4
