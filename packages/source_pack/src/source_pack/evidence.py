from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from context_builder.schemas.context_bundle import ContextBundleEvidence

from source_pack.ids import slugify, stable_uuid
from source_pack.readers import CsvRow, MarkdownSection

MAX_QUOTE_LEN = 500

_PRIVATE_PATH_RE = re.compile(
    r"\b[A-Za-z]:\\(?:Users|Documents and Settings)\\|"
    r"(^|\s)/(?:Users|home|root)/",
    re.IGNORECASE,
)
_SECRET_RE = re.compile(
    r"sk-[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{20,}",
    re.IGNORECASE,
)


def _safe_quote(text: str | None) -> str | None:
    if text is None:
        return None
    text = text[:MAX_QUOTE_LEN]
    text = _PRIVATE_PATH_RE.sub("[REDACTED_PATH]", text)
    text = _SECRET_RE.sub("[REDACTED_SECRET]", text)
    return text.strip() or None


def evidence_from_csv_row(source_id: UUID, row: CsvRow) -> dict[str, Any]:
    evidence_id = stable_uuid(f"evidence:{row.filename}:row:{row.row_number}")
    chunk_id = stable_uuid(f"chunk:{row.filename}:row:{row.row_number}")
    raw_quote = " | ".join(str(value) for value in row.row_data.values() if value)
    return {
        "id": evidence_id,
        "source_id": source_id,
        "chunk_id": chunk_id,
        "quote": _safe_quote(raw_quote),
        "page_number": None,
        "sheet_name": None,
        "row_number": row.row_number,
    }


def evidence_from_markdown_section(
    source_id: UUID,
    section: MarkdownSection,
) -> dict[str, Any]:
    evidence_id = stable_uuid(f"evidence:{section.filename}:{section.anchor}")
    chunk_id = stable_uuid(f"chunk:{section.filename}:{section.anchor}")
    raw_quote = f"{section.heading}: {section.body[:400]}"
    return {
        "id": evidence_id,
        "source_id": source_id,
        "chunk_id": chunk_id,
        "quote": _safe_quote(raw_quote),
        "page_number": None,
        "sheet_name": None,
        "row_number": None,
    }


def csv_row_evidence(
    *,
    filename: str,
    source_id: UUID,
    row: CsvRow,
) -> ContextBundleEvidence:
    data = evidence_from_csv_row(source_id, row)
    return ContextBundleEvidence(
        id=data["id"],
        source_id=data["source_id"],
        chunk_id=data["chunk_id"],
        quote=data["quote"],
        page_number=data["page_number"],
        sheet_name=filename,
        row_number=row.line_number,
    )


def markdown_section_evidence(
    *,
    filename: str,
    source_id: UUID,
    text: str,
) -> list[ContextBundleEvidence]:
    evidence: list[ContextBundleEvidence] = []
    for section in _sections_from_text(filename, text):
        data = evidence_from_markdown_section(source_id, section)
        evidence.append(
            ContextBundleEvidence(
                id=data["id"],
                source_id=data["source_id"],
                chunk_id=data["chunk_id"],
                quote=data["quote"],
                page_number=data["page_number"],
                sheet_name=filename,
                row_number=data["row_number"],
            )
        )
    return evidence


def _sections_from_text(filename: str, text: str) -> list[MarkdownSection]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines()
    content_start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                content_start = index + 1
                break
    headings: list[tuple[int, int, str]] = []
    pattern = re.compile(r"^(#+)\s+(.+)$")
    for index, line in enumerate(lines):
        if index < content_start:
            continue
        match = pattern.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))
    sections: list[MarkdownSection] = []
    for position, (line_index, level, heading) in enumerate(headings):
        body_start = line_index + 1
        body_end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        sections.append(
            MarkdownSection(
                filename=filename,
                heading=heading,
                level=level,
                anchor=slugify(heading),
                body="\n".join(lines[body_start:body_end]).strip(),
                start_line=line_index + 1,
            )
        )
    return sections
