from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from parsers.base import ExtractedPage
from parsers.industrial_structure import hint_from_line

LineRef = tuple[int, str]


@dataclass(frozen=True)
class BoilerplateSpan:
    kind: str
    page_number: int
    line_index: int
    quote: str


@dataclass(frozen=True)
class SectionSpan:
    kind: str
    page_number: int
    line_index: int
    label: str
    section_title: str
    section_path: str
    page_start: int
    page_end: int
    risk_codes: tuple[str, ...] = ()

    @property
    def title(self) -> str:
        return self.section_title


@dataclass(frozen=True)
class SectionDiagnostics:
    boilerplate_spans: list[BoilerplateSpan] = field(default_factory=list)
    section_spans: list[SectionSpan] = field(default_factory=list)
    risk_codes: list[str] = field(default_factory=list)


def resolve_document_sections(pages: list[ExtractedPage]) -> SectionDiagnostics:
    lines_by_page = [(_page.page_number, _non_empty_lines(_page.text)) for _page in pages]
    recurring_headers = _recurring_edge_lines(lines_by_page, edge="first")
    recurring_footers = _recurring_edge_lines(lines_by_page, edge="last")

    boilerplate_spans: list[BoilerplateSpan] = []
    boilerplate_positions: set[tuple[int, int]] = set()
    for page_number, lines in lines_by_page:
        if not lines:
            continue
        first_line_index, first_line = lines[0]
        if (
            _normalize_boilerplate_line(first_line) in recurring_headers
            and not _is_structural_line(first_line)
        ):
            boilerplate_spans.append(
                BoilerplateSpan(
                    kind="header",
                    page_number=page_number,
                    line_index=first_line_index,
                    quote=first_line,
                )
            )
            boilerplate_positions.add((page_number, first_line_index))
        last_line_index, last_line = lines[-1]
        if _normalize_boilerplate_line(last_line) in recurring_footers:
            boilerplate_spans.append(
                BoilerplateSpan(
                    kind="footer",
                    page_number=page_number,
                    line_index=last_line_index,
                    quote=last_line,
                )
            )
            boilerplate_positions.add((page_number, last_line_index))

    section_spans: list[SectionSpan] = []
    risk_codes: list[str] = []
    section_stack: dict[int, str] = {}
    for page_number, lines in lines_by_page:
        for line_index, line in lines:
            if (page_number, line_index) in boilerplate_positions:
                continue
            hint = hint_from_line(line, 0, len(line), section_stack=section_stack)
            if hint is None:
                continue
            if hint.kind == "ambiguous_section":
                _extend_unique(risk_codes, hint.risk_codes)
                continue
            if hint.kind != "section" or hint.section_path is None or hint.title is None:
                continue
            section_spans.append(
                SectionSpan(
                    kind=_section_kind(hint.label),
                    page_number=page_number,
                    line_index=line_index,
                    label=hint.label,
                    section_title=hint.title,
                    section_path=hint.section_path,
                    page_start=page_number,
                    page_end=page_number,
                    risk_codes=hint.risk_codes,
                )
            )
            _extend_unique(risk_codes, hint.risk_codes)

    _extend_unique(risk_codes, _duplicate_qms_risks(section_spans))
    return SectionDiagnostics(
        boilerplate_spans=boilerplate_spans,
        section_spans=_finalize_page_bounds(section_spans, pages),
        risk_codes=risk_codes,
    )


def section_diagnostics_to_metadata(diagnostics: SectionDiagnostics) -> dict[str, Any]:
    return {
        "boilerplate_spans": [asdict(span) for span in diagnostics.boilerplate_spans],
        "section_spans": [asdict(span) for span in diagnostics.section_spans],
        "risk_codes": list(diagnostics.risk_codes),
        "summary": summarize_section_diagnostics(diagnostics),
    }


def summarize_section_diagnostics(diagnostics: SectionDiagnostics) -> dict[str, Any]:
    boilerplate_counts = Counter(span.kind for span in diagnostics.boilerplate_spans)
    section_kind_counts = Counter(span.kind for span in diagnostics.section_spans)
    risk_counts = Counter(diagnostics.risk_codes)
    return {
        "section_count": len(diagnostics.section_spans),
        "section_path_count": sum(1 for span in diagnostics.section_spans if span.section_path),
        "boilerplate_counts": dict(sorted(boilerplate_counts.items())),
        "section_kind_counts": dict(sorted(section_kind_counts.items())),
        "risk_code_counts": dict(sorted(risk_counts.items())),
        "risk_codes": list(diagnostics.risk_codes),
    }


def _non_empty_lines(text: str) -> list[LineRef]:
    return [
        (line_index, line.strip())
        for line_index, line in enumerate(text.splitlines())
        if line.strip()
    ]


def _recurring_edge_lines(
    lines_by_page: list[tuple[int, list[LineRef]]],
    *,
    edge: str,
) -> set[str]:
    if len(lines_by_page) < 2:
        return set()
    edge_lines = [
        _normalize_boilerplate_line((lines[0] if edge == "first" else lines[-1])[1])
        for _page_number, lines in lines_by_page
        if lines
    ]
    minimum = max(2, (len(lines_by_page) + 1) // 2)
    counts = Counter(edge_lines)
    return {line for line, count in counts.items() if count >= minimum}


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip()).casefold()


def _normalize_boilerplate_line(line: str) -> str:
    return re.sub(r"\d+", "#", _normalize_line(line))


def _is_structural_line(line: str) -> bool:
    hint = hint_from_line(line, 0, len(line), section_stack={})
    return hint is not None and hint.kind == "section"


def _section_kind(label: str) -> str:
    if label and label[0].isdigit():
        return "numbered_heading"
    return "qms_heading"


def _finalize_page_bounds(spans: list[SectionSpan], pages: list[ExtractedPage]) -> list[SectionSpan]:
    if not spans:
        return []
    last_page = pages[-1].page_number if pages else spans[-1].page_number
    finalized: list[SectionSpan] = []
    for index, span in enumerate(spans):
        if index + 1 < len(spans):
            next_page = spans[index + 1].page_number
            page_end = span.page_number if next_page == span.page_number else max(span.page_number, next_page - 1)
        else:
            page_end = max(span.page_number, last_page)
        finalized.append(replace(span, page_end=page_end))
    return finalized


def _duplicate_qms_risks(spans: list[SectionSpan]) -> tuple[str, ...]:
    qms_counts = Counter(span.label for span in spans if span.kind == "qms_heading")
    if any(count > 1 for count in qms_counts.values()):
        return ("ambiguous_section_heading",)
    return ()


def _extend_unique(target: list[str], values: tuple[str, ...] | list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)
