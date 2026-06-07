from __future__ import annotations

import re
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from parsers.base import ExtractedPage, ExtractionResult
from parsers.chunker import RawChunk, chunk_extraction
from parsers.industrial_metadata import extract_metadata_candidates
from parsers.industrial_review import build_review_packets, summarize_review_packets
from parsers.industrial_sections import (
    resolve_document_sections,
    section_diagnostics_to_metadata,
)
from parsers.industrial_semantics import extract_semantic_candidates
from parsers.industrial_tables import (
    extract_table_figure_candidates,
    table_figure_candidates_to_metadata,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "examples" / "parser_fragility"


def _fixture(filename: str) -> str:
    return (FIXTURE_DIR / filename).read_text(encoding="utf-8")


def _page(page_number: int, text: str) -> ExtractedPage:
    return ExtractedPage(
        page_number=page_number,
        text=text,
        char_count=len(text),
        is_empty=not bool(text.strip()),
    )


def _pages_from_page_markers(text: str) -> list[ExtractedPage]:
    pages: list[ExtractedPage] = []
    current_page: int | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        marker = re.fullmatch(r"Pagina\s+(\d+)", line.strip(), flags=re.IGNORECASE)
        if marker:
            if current_page is not None:
                pages.append(_page(current_page, "\n".join(current_lines).strip()))
            current_page = int(marker.group(1))
            current_lines = []
            continue
        if current_page is not None:
            current_lines.append(line)
    if current_page is not None:
        pages.append(_page(current_page, "\n".join(current_lines).strip()))
    return pages


def _split_fixture_visual_profiles(text: str) -> list[dict[str, object]]:
    profiles: list[dict[str, object]] = []
    for line in text.splitlines():
        marker = re.fullmatch(r"Pagina\s+(\d+):\s*(.+)", line.strip(), flags=re.IGNORECASE)
        if not marker:
            continue
        page_number = int(marker.group(1))
        content = marker.group(2)
        if "[IMAGEM-APENAS" not in content:
            continue
        profiles.append(
            {
                "page_number": page_number,
                "image_count": 1,
                "text_chars": 0,
                "risk_codes": [
                    "visual_content_without_caption",
                    "ocr_required",
                    "sparse_text_with_images",
                ],
            }
        )
    return profiles


def _split_fixture_section_gap_pages(text: str) -> list[ExtractedPage]:
    pages: list[ExtractedPage] = []
    for line in text.splitlines():
        marker = re.fullmatch(r"Pagina\s+(\d+):\s*(\d+\.\d+\s+.+)", line.strip())
        if not marker:
            continue
        page_number = int(marker.group(1))
        section_text = marker.group(2).rstrip(".")
        pages.append(_page(page_number, section_text))
    return pages


def _chunk(
    text: str,
    *,
    chunk_index: int = 0,
    page_start: int = 1,
    page_end: int | None = None,
    section_path: str | None = None,
    section_title: str | None = None,
    chunk_kind: str | None = "adversarial_fixture",
    metadata: dict[str, object] | None = None,
    structure_risk_codes: tuple[str, ...] = (),
) -> RawChunk:
    return RawChunk(
        chunk_index=chunk_index,
        text=text,
        char_count=len(text),
        token_estimate=max(1, len(text) // 4),
        chunk_hash=sha256(f"{chunk_index}:{text}".encode()).hexdigest(),
        source_page=page_start,
        sheet_name=None,
        row_start=None,
        row_end=None,
        section_heading=section_title,
        metadata=metadata or {"fixture": "parser_fragility.v1"},
        page_start=page_start,
        page_end=page_end or page_start,
        section_path=section_path,
        section_title=section_title,
        chunk_kind=chunk_kind,
        structure_risk_codes=structure_risk_codes,
    )


def test_nested_appendix_codes_are_not_promoted_and_raise_metadata_risk() -> None:
    text = _fixture("multi_document_appendix_codes.txt")

    metadata = extract_metadata_candidates(
        filename="multi_document_appendix_codes.txt",
        text=text,
    )
    packets = build_review_packets(
        document_id="multi-document-appendix-codes",
        metadata=asdict(metadata),
    )
    summary = summarize_review_packets(packets)

    assert metadata.document_code is None
    assert "POP 101" not in {metadata.document_code}
    assert "POP 102" not in {metadata.document_code}
    assert "missing_document_code" in metadata.gap_codes
    assert "ambiguous_nested_document_codes" in metadata.gap_codes
    assert summary["reason_code_counts"]["ambiguous_metadata"] == 1


def test_nested_codes_before_toc_delimiter_are_not_promoted_as_file_metadata() -> None:
    text = (
        "Titulo: Apostila operacional sem codigo unico\n"
        "POP 101 - Higienizacao de bancada\n"
        "IT 202 - Conferencia de rotulos\n"
        "Anexo A - POP 101\n"
        "Executar limpeza antes do turno.\n"
        "Anexo B - IT 202\n"
        "Conferir rotulos antes da liberacao.\n"
    )

    metadata = extract_metadata_candidates(
        filename="apostila-operacional.txt",
        text=text,
    )
    packets = build_review_packets(
        document_id="apostila-operacional",
        metadata=asdict(metadata),
    )
    summary = summarize_review_packets(packets)

    assert metadata.document_code is None
    assert "missing_document_code" in metadata.gap_codes
    assert "ambiguous_nested_document_codes" in metadata.gap_codes
    assert summary["reason_code_counts"]["ambiguous_metadata"] == 1


def test_toc_requirement_words_are_not_semantic_requirements_when_page_numbers_are_lost() -> None:
    text = _fixture("toc_requirement_words.txt")
    toc_lines = [
        re.sub(r"\s*\.{3,}\s*\d+\s*$", "", line).strip()
        for line in text.splitlines()
        if "Deve" in line and "." in line
    ]

    candidates = extract_semantic_candidates([
        _chunk(
            "\n".join(toc_lines),
            section_path="sumario",
            section_title="Sumario",
        )
    ])

    assert toc_lines == [
        "5.1 Deve registrar incidentes",
        "5.2 Deve comunicar supervisor",
        "5.3 Deve arquivar evidencias",
    ]
    assert [
        candidate.evidence.quote
        for candidate in candidates
        if candidate.kind == "requirement"
    ] == []


def test_toc_alias_sections_do_not_promote_requirement_or_step_entries() -> None:
    lines = "5.1 Deve registrar incidentes\n5.2 Executar bloqueio da linha."

    for title in ("Indice", "Table of Contents"):
        candidates = extract_semantic_candidates([
            _chunk(lines, section_path=title.casefold().replace(" ", "-"), section_title=title)
        ])

        assert [
            candidate.kind
            for candidate in candidates
            if candidate.kind in {"requirement", "procedure_step"}
        ] == []


def test_boilerplate_header_with_requirement_words_is_not_a_semantic_candidate() -> None:
    text = _fixture("repeated_boilerplate_sections.txt")
    header_quote = "Cabecalho: Toda NC deve ser registrada"
    assert header_quote in text

    candidates = extract_semantic_candidates([
        _chunk(
            header_quote,
            chunk_kind="boilerplate",
            metadata={"boilerplate_kind": "header", "fixture": "parser_fragility.v1"},
        )
    ])

    assert candidates == []


def test_step_shaped_header_and_footer_boilerplate_do_not_become_procedure_steps() -> None:
    text = _fixture("repeated_boilerplate_sections.txt")
    assert "Cabecalho:" in text
    assert "Rodape:" in text
    header_line = "1. Registrar cabecalho controlado antes do procedimento."
    footer_line = "2. Encerrar rodape controlado apos a impressao."

    control_candidates = extract_semantic_candidates([
        _chunk(header_line, chunk_index=1),
        _chunk(footer_line, chunk_index=2),
    ])
    boilerplate_candidates = extract_semantic_candidates([
        _chunk(
            header_line,
            chunk_index=3,
            chunk_kind="boilerplate",
            metadata={"boilerplate_kind": "header", "fixture": "parser_fragility.v1"},
        ),
        _chunk(
            footer_line,
            chunk_index=4,
            chunk_kind="boilerplate",
            metadata={"boilerplate_kind": "footer", "fixture": "parser_fragility.v1"},
        ),
    ])

    assert [
        candidate.evidence.quote
        for candidate in control_candidates
        if candidate.kind == "procedure_step"
    ] == [header_line, footer_line]
    assert [
        candidate.evidence.quote
        for candidate in boilerplate_candidates
        if candidate.kind == "procedure_step"
    ] == []


def test_figure_reference_without_real_caption_stays_reference_plus_visual_risk() -> None:
    text = _fixture("figure_reference_without_caption.txt")

    candidates = extract_table_figure_candidates(
        [
            _chunk(
                text,
                page_start=1,
                section_path="3",
                section_title="Verificacao visual",
            )
        ],
        page_profiles=[
            {
                "page_number": 1,
                "image_count": 1,
                "text_chars": len(text),
                "risk_codes": ["visual_content_without_caption"],
            }
        ],
    )

    assert any(candidate.kind == "figure_reference" for candidate in candidates)
    assert not any(candidate.kind == "visual_understanding" for candidate in candidates)
    assert [
        candidate.risk_codes
        for candidate in candidates
        if candidate.kind == "visual_risk"
    ] == [("visual_content_without_caption",)]


def test_sparse_visual_placeholder_emits_review_packet_instead_of_clean_text_claim() -> None:
    text = _fixture("sparse_visual_placeholder.txt")
    candidates = extract_table_figure_candidates(
        [],
        page_profiles=[
            {
                "page_number": 1,
                "image_count": 1,
                "text_chars": 0,
                "risk_codes": ["ocr_required", "sparse_text_with_images"],
            }
        ],
    )

    packets = build_review_packets(
        document_id="sparse-visual-placeholder",
        table_figure_candidates=table_figure_candidates_to_metadata(candidates),
    )
    summary = summarize_review_packets(packets)
    visual_packet = packets[0]

    assert "[IMAGEM-APENAS" in text
    assert [
        candidate.risk_codes
        for candidate in candidates
        if candidate.kind == "visual_risk"
    ] == [("ocr_required", "sparse_text_with_images", "visual_content_without_caption")]
    assert summary["reason_code_counts"]["visual_table_figure_risk"] == 1
    assert visual_packet.suggested_decision == "inspect_visual_evidence"
    assert visual_packet.risk_codes == (
        "ocr_required",
        "sparse_text_with_images",
        "visual_content_without_caption",
    )
    assert visual_packet.evidence[0]["risk_codes"] == [
        "ocr_required",
        "sparse_text_with_images",
        "visual_content_without_caption",
    ]


def test_hierarchy_gap_stays_on_section_spans_as_risk_code() -> None:
    diagnostics = resolve_document_sections([
        _page(1, _fixture("section_hierarchy_gap.txt"))
    ])

    gap_spans = [
        span
        for span in diagnostics.section_spans
        if "section_hierarchy_gap" in span.risk_codes
    ]

    assert [span.section_path for span in gap_spans] == ["5.2", "5.3", "5.4"]
    assert diagnostics.risk_codes == ["section_hierarchy_gap"]


def test_repeated_boilerplate_does_not_enter_body_chunks() -> None:
    pages = _pages_from_page_markers(_fixture("repeated_boilerplate_sections.txt"))
    diagnostics = resolve_document_sections(pages)
    result = ExtractionResult(
        mime_type="text/plain",
        pages=pages,
        total_chars=sum(page.char_count for page in pages),
    )

    chunks = chunk_extraction(
        result,
        industrial_context=section_diagnostics_to_metadata(diagnostics),
    )
    chunk_text = "\n".join(chunk.text for chunk in chunks)

    assert "Cabecalho: Toda NC deve ser registrada" not in chunk_text
    assert "Rodape: copia controlada" not in chunk_text
    assert [chunk.section_path for chunk in chunks] == ["1", "2", "3"]


def test_section_hierarchy_gap_review_packets_are_grouped_by_risk() -> None:
    diagnostics = resolve_document_sections([
        _page(1, _fixture("section_hierarchy_gap.txt"))
    ])

    packets = build_review_packets(
        document_id="section-hierarchy-gap",
        section_diagnostics=section_diagnostics_to_metadata(diagnostics),
    )
    hierarchy_packets = [
        packet
        for packet in packets
        if packet.reason_code == "ambiguous_section_hierarchy"
        and "section_hierarchy_gap" in packet.risk_codes
    ]

    assert len(hierarchy_packets) == 1
    assert len(hierarchy_packets[0].evidence) == 3
    assert {
        item["section_path"]
        for item in hierarchy_packets[0].evidence
        if isinstance(item, dict)
    } == {"5.2", "5.3", "5.4"}


def test_semantic_evidence_quotes_stay_on_their_claimed_source_page() -> None:
    pages = _pages_from_page_markers(_fixture("evidence_boundary_drift.txt"))
    chunks = [
        _chunk(
            page.text,
            chunk_index=index,
            page_start=page.page_number,
            page_end=page.page_number,
            section_path="4.1",
            section_title="Requisito",
        )
        for index, page in enumerate(pages)
    ]

    candidates = extract_semantic_candidates(chunks)
    source_text_by_page = {page.page_number: page.text for page in pages}

    assert candidates
    for candidate in candidates:
        page_start = candidate.evidence.page_start
        assert page_start is not None
        assert candidate.evidence.quote in source_text_by_page[page_start]


def test_late_split_range_risks_remain_visible_to_review_layers() -> None:
    text = _fixture("split_stress_surrogate.txt")
    page_profiles = _split_fixture_visual_profiles(text)
    section_pages = _split_fixture_section_gap_pages(text)
    diagnostics = resolve_document_sections(section_pages)

    table_candidates = extract_table_figure_candidates([], page_profiles=page_profiles)
    packets = build_review_packets(
        document_id="split-stress-surrogate",
        section_diagnostics=section_diagnostics_to_metadata(diagnostics),
        table_figure_candidates=table_figure_candidates_to_metadata(table_candidates),
    )
    summary = summarize_review_packets(packets)

    assert "Faixa 2" in text
    assert page_profiles == [
        {
            "page_number": 4,
            "image_count": 1,
            "text_chars": 0,
            "risk_codes": [
                "visual_content_without_caption",
                "ocr_required",
                "sparse_text_with_images",
            ],
        }
    ]
    assert [(page.page_number, page.text) for page in section_pages] == [
        (5, "8.2 Subsecao sem secao pai 8")
    ]
    assert diagnostics.risk_codes == ["section_hierarchy_gap"]
    assert summary["reason_code_counts"]["ambiguous_section_hierarchy"] == 1
    assert summary["reason_code_counts"]["visual_table_figure_risk"] == 1
