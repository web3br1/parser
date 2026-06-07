from __future__ import annotations

import json
import re
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from parsers.base import ExtractedPage, ExtractionResult
from parsers.chunker import RawChunk, chunk_extraction
from parsers.industrial_metadata import extract_metadata_candidates
from parsers.industrial_review import IndustrialReviewPacket, build_review_packets
from parsers.industrial_sections import (
    resolve_document_sections,
    section_diagnostics_to_metadata,
)
from parsers.industrial_semantics import (
    IndustrialSemanticCandidate,
    IndustrialSemanticEvidence,
    extract_semantic_candidates,
    semantic_candidates_to_metadata,
)
from parsers.industrial_tables import (
    extract_table_figure_candidates,
    table_figure_candidates_to_metadata,
)

from packages.parsers.tests.industrial_invariant_helpers import (
    assert_candidate_evidence_pages_within_result,
    assert_candidate_evidence_quotes_in_source,
    assert_chunks_have_valid_source_spans,
    assert_diagnostics_preserve_extraction_text,
    assert_known_parser_risk_codes,
    assert_review_packet_counts_bounded,
    assert_review_packets_well_formed,
    assert_section_metadata_hash_invariant,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "examples" / "parser_fragility"
MANIFEST = FIXTURE_DIR / "manifest.json"
SCENARIOS_EXPECTING_SEMANTIC_CANDIDATES = {
    "evidence_quote_boundary_drift",
    "figure_reference_without_visual_evidence",
    "split_document_stress_surrogate",
}
SCENARIOS_EXPECTING_TABLE_CANDIDATES = {
    "figure_reference_without_visual_evidence",
    "sparse_image_placeholder_review_risk",
    "split_document_stress_surrogate",
}


def _page(page_number: int, text: str) -> ExtractedPage:
    return ExtractedPage(
        page_number=page_number,
        text=text,
        char_count=len(text),
        is_empty=not bool(text.strip()),
    )


def _result(pages: list[ExtractedPage], metadata: dict[str, Any] | None = None) -> ExtractionResult:
    return ExtractionResult(
        mime_type="text/plain",
        pages=pages,
        total_chars=sum(page.char_count for page in pages),
        metadata=metadata or {"parser": "txt"},
    )


def _chunk(
    text: str,
    *,
    chunk_index: int = 0,
    page_start: int | None = 1,
    page_end: int | None = 1,
    source_page: int | None = 1,
    section_path: str | None = "1",
    section_title: str | None = "Objetivo",
    chunk_hash: str | None = None,
) -> RawChunk:
    return RawChunk(
        chunk_index=chunk_index,
        text=text,
        char_count=len(text),
        token_estimate=max(1, len(text) // 4),
        chunk_hash=chunk_hash or sha256(text.encode()).hexdigest(),
        source_page=source_page,
        sheet_name=None,
        row_start=None,
        row_end=None,
        section_heading=section_title,
        metadata={"parser": "txt"},
        page_start=page_start,
        page_end=page_end,
        section_path=section_path,
        section_title=section_title,
        chunk_kind="numbered_heading" if section_path else None,
    )


def _semantic_candidate(
    quote: str,
    *,
    page_start: int | None = 1,
    page_end: int | None = 1,
    chunk: RawChunk | None = None,
) -> IndustrialSemanticCandidate:
    source_chunk = chunk or _chunk("Deve registrar lote.")
    return IndustrialSemanticCandidate(
        candidate_id=f"{source_chunk.chunk_hash}:requirement:0",
        kind="requirement",
        normalized_text=quote,
        normalized_content={"requirement": quote},
        confidence=0.82,
        evidence=IndustrialSemanticEvidence(
            quote=quote,
            chunk_index=source_chunk.chunk_index,
            chunk_hash=source_chunk.chunk_hash,
            section_path=source_chunk.section_path,
            section_title=source_chunk.section_title,
            page_start=page_start,
            page_end=page_end,
            char_start=0,
            char_end=len(quote),
        ),
    )


def _fixture_documents() -> list[dict[str, Any]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [document for document in manifest["documents"] if isinstance(document, dict)]


def _pages_from_fixture_text(text: str) -> list[ExtractedPage]:
    pages: list[ExtractedPage] = []
    current_page: int | None = None
    current_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_page, current_lines
        if current_page is not None:
            pages.append(_page(current_page, "\n".join(current_lines).strip()))
        current_page = None
        current_lines = []

    for line in text.splitlines():
        bare_marker = re.fullmatch(r"Pagina\s+(\d+)", line.strip(), flags=re.IGNORECASE)
        inline_marker = re.fullmatch(r"Pagina\s+(\d+):\s*(.*)", line.strip(), flags=re.IGNORECASE)
        if bare_marker:
            flush_current()
            current_page = int(bare_marker.group(1))
            continue
        if inline_marker:
            flush_current()
            pages.append(_page(int(inline_marker.group(1)), inline_marker.group(2).strip()))
            continue
        if current_page is not None:
            current_lines.append(line)

    flush_current()
    return pages or [_page(1, text)]


def _fixture_page_profiles(pages: list[ExtractedPage]) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for page in pages:
        if "[IMAGEM-APENAS" not in page.text:
            continue
        profiles.append(
            {
                "page_number": page.page_number,
                "image_count": 1,
                "text_chars": 0,
                "risk_codes": [
                    "ocr_required",
                    "sparse_text_with_images",
                    "visual_content_without_caption",
                ],
            }
        )
    return profiles


def test_invalid_evidence_quote_drift_fails_invariant() -> None:
    result = _result([_page(1, "Deve registrar lote.")])
    candidate = _semantic_candidate("Deve liberar lote.")

    with pytest.raises(AssertionError, match="quote.*not found"):
        assert_candidate_evidence_quotes_in_source([candidate], result)


def test_invalid_evidence_page_span_fails_invariant() -> None:
    result = _result([_page(1, "Deve registrar lote."), _page(2, "Deve revisar lote.")])
    candidate = _semantic_candidate("Deve revisar lote.", page_start=3, page_end=3)

    with pytest.raises(AssertionError, match="page.*outside"):
        assert_candidate_evidence_pages_within_result([candidate], result)


def test_unsupported_candidate_evidence_list_item_fails_quote_invariant() -> None:
    result = _result([_page(1, "Deve registrar lote.")])
    candidate = {
        "candidate_id": "bad:evidence:item",
        "kind": "requirement",
        "evidence": [object()],
    }

    with pytest.raises(AssertionError, match="evidence item"):
        assert_candidate_evidence_quotes_in_source([candidate], result)


def test_empty_explicit_candidate_evidence_list_fails_page_invariant() -> None:
    result = _result([_page(1, "Deve registrar lote.")])
    candidate = {
        "candidate_id": "bad:empty:evidence",
        "kind": "requirement",
        "evidence": [],
    }

    with pytest.raises(AssertionError, match="evidence"):
        assert_candidate_evidence_pages_within_result([candidate], result)


def test_candidate_page_span_fails_when_result_has_no_pages() -> None:
    result = _result([])
    candidate = _semantic_candidate("Deve registrar lote.", page_start=1, page_end=1)

    with pytest.raises(AssertionError, match="no parsed pages"):
        assert_candidate_evidence_pages_within_result([candidate], result)


def test_empty_chunk_text_fails_source_span_invariant() -> None:
    empty_chunk = _chunk("", page_start=1, page_end=1)

    with pytest.raises(AssertionError, match="non-empty"):
        assert_chunks_have_valid_source_spans([empty_chunk])


def test_reversed_chunk_page_span_fails_source_span_invariant() -> None:
    reversed_span = _chunk("Deve registrar lote.", page_start=2, page_end=1, source_page=2)

    with pytest.raises(AssertionError, match="ordered"):
        assert_chunks_have_valid_source_spans([reversed_span])


def test_section_metadata_hash_drift_fails_invariant() -> None:
    baseline = [_chunk("Mesmo texto tecnico.", section_path="1")]
    drifted = [
        _chunk(
            "Mesmo texto tecnico.",
            section_path="2",
            chunk_hash=sha256(b"2:Mesmo texto tecnico.").hexdigest(),
        )
    ]

    with pytest.raises(AssertionError, match="hash"):
        assert_section_metadata_hash_invariant(baseline, drifted)


def test_unknown_risk_code_fails_invariant() -> None:
    diagnostics = {"risk_codes": ["unknown_space_risk"]}

    with pytest.raises(AssertionError, match="unknown risk code"):
        assert_known_parser_risk_codes(diagnostics)


def test_diagnostics_that_delete_source_text_fail_invariant() -> None:
    before = _result([_page(1, "Linha preservada.\nLinha que nao pode sumir.")])
    after = _result(
        [_page(1, "Linha preservada.")],
        metadata={"parser": "txt", "section_diagnostics": {"risk_codes": []}},
    )

    with pytest.raises(AssertionError, match="source text"):
        assert_diagnostics_preserve_extraction_text(before, after)


def test_review_packet_missing_shape_fields_fails_invariant() -> None:
    packet = IndustrialReviewPacket(
        packet_id="",
        reason_code="missing_metadata",
        severity="high",
        evidence=[{"risk_code": "missing_revision"}],
        suggested_decision="fill_missing_metadata",
        risk_codes=("missing_revision",),
    )

    with pytest.raises(AssertionError, match="packet_id"):
        assert_review_packets_well_formed([packet])


def test_review_packet_without_evidence_or_document_level_reason_fails_invariant() -> None:
    packet = IndustrialReviewPacket(
        packet_id="doc:low_confidence_semantic_unit:5",
        reason_code="low_confidence_semantic_unit",
        severity="medium",
        evidence=[],
        suggested_decision="accept_edit_or_reject_candidate",
        section_path="5",
        risk_codes=("low_confidence_semantic_unit",),
    )

    with pytest.raises(AssertionError, match="evidence"):
        assert_review_packets_well_formed([packet])


def test_review_packet_anchorless_evidence_item_fails_invariant() -> None:
    packet = IndustrialReviewPacket(
        packet_id="doc:missing_metadata:missing_revision",
        reason_code="missing_metadata",
        severity="high",
        evidence=[{}],
        suggested_decision="fill_missing_metadata",
        risk_codes=("missing_revision",),
    )

    with pytest.raises(AssertionError, match="anchor"):
        assert_review_packets_well_formed([packet])


def test_review_packet_generator_unknown_risk_code_fails_invariant() -> None:
    packet = IndustrialReviewPacket(
        packet_id="doc:missing_metadata:unknown_space_risk",
        reason_code="missing_metadata",
        severity="high",
        evidence=[{"risk_code": "unknown_space_risk"}],
        suggested_decision="fill_missing_metadata",
        risk_codes=("unknown_space_risk",),
    )

    def packet_generator():
        yield packet

    with pytest.raises(AssertionError, match="unknown risk code"):
        assert_review_packets_well_formed(packet_generator())


def test_repeated_equivalent_review_packets_fail_bounded_grouping_invariant() -> None:
    packets = [
        IndustrialReviewPacket(
            packet_id="doc:visual_table_figure_risk:1:a",
            reason_code="visual_table_figure_risk",
            severity="medium",
            evidence=[{"page_number": 1, "risk_codes": ["visual_content_without_caption"]}],
            suggested_decision="inspect_visual_evidence",
            page_number=1,
            risk_codes=("visual_content_without_caption",),
        ),
        IndustrialReviewPacket(
            packet_id="doc:visual_table_figure_risk:1:b",
            reason_code="visual_table_figure_risk",
            severity="medium",
            evidence=[{"page_number": 1, "risk_codes": ["visual_content_without_caption"]}],
            suggested_decision="inspect_visual_evidence",
            page_number=1,
            risk_codes=("visual_content_without_caption",),
        ),
    ]

    with pytest.raises(AssertionError, match="equivalent"):
        assert_review_packet_counts_bounded(packets)


def test_valid_section_metadata_does_not_change_chunk_text_hashes() -> None:
    result = _result([_page(1, "1 Objetivo\nMesmo texto tecnico.")])
    base_span = {
        "kind": "numbered_heading",
        "page_number": 1,
        "line_index": 0,
        "section_title": "Objetivo",
        "section_path": "1",
        "page_start": 1,
        "page_end": 1,
        "risk_codes": [],
    }

    first = chunk_extraction(result, industrial_context={"section_spans": [base_span]})
    second = chunk_extraction(
        result,
        industrial_context={
            "section_spans": [
                {
                    **base_span,
                    "section_title": "Titulo alterado",
                    "section_path": "2",
                }
            ]
        },
    )

    assert_section_metadata_hash_invariant(first, second)


def test_repeated_section_gap_risks_are_bounded_in_review_packets() -> None:
    pages = [
        _page(
            1,
            "5.2 Subsecao sem pai\n"
            "Deve revisar o registro.\n"
            "5.3 Outra subsecao sem pai\n"
            "Deve aprovar o registro.",
        )
    ]
    diagnostics = resolve_document_sections(pages)
    packets = build_review_packets(
        document_id="section-gap",
        section_diagnostics=section_diagnostics_to_metadata(diagnostics),
    )

    assert len(packets) == 1
    assert_review_packets_well_formed(packets)
    assert_review_packet_counts_bounded(packets)
    assert_known_parser_risk_codes(section_diagnostics_to_metadata(diagnostics), packets)


@pytest.mark.parametrize("document", _fixture_documents(), ids=lambda item: str(item["scenario"]))
def test_parser_fragility_fixture_outputs_satisfy_invariants(document: dict[str, Any]) -> None:
    text = (FIXTURE_DIR / str(document["filename"])).read_text(encoding="utf-8")
    pages = _pages_from_fixture_text(text)
    base_result = _result(pages)
    diagnostics = resolve_document_sections(pages)
    section_metadata = section_diagnostics_to_metadata(diagnostics)
    enriched_result = _result(
        pages,
        metadata={"parser": "txt", "section_diagnostics": section_metadata},
    )

    assert_diagnostics_preserve_extraction_text(base_result, enriched_result)
    chunks = chunk_extraction(enriched_result)
    semantic_candidates = extract_semantic_candidates(chunks)
    table_candidates = extract_table_figure_candidates(
        chunks,
        page_profiles=_fixture_page_profiles(pages),
    )
    metadata = extract_metadata_candidates(filename=str(document["filename"]), text=text)
    packets = build_review_packets(
        document_id=str(document["scenario"]),
        metadata=asdict(metadata),
        section_diagnostics=section_metadata,
        semantic_candidates=semantic_candidates_to_metadata(semantic_candidates),
        table_figure_candidates=table_figure_candidates_to_metadata(table_candidates),
    )

    assert_chunks_have_valid_source_spans(chunks)
    scenario = str(document["scenario"])
    if scenario in SCENARIOS_EXPECTING_SEMANTIC_CANDIDATES:
        assert semantic_candidates, f"{scenario} should produce semantic candidates"
    if scenario in SCENARIOS_EXPECTING_TABLE_CANDIDATES:
        assert table_candidates, f"{scenario} should produce table/figure candidates"
    assert_candidate_evidence_pages_within_result(semantic_candidates, enriched_result)
    assert_candidate_evidence_pages_within_result(table_candidates, enriched_result)
    assert_candidate_evidence_quotes_in_source(semantic_candidates, enriched_result)
    assert_candidate_evidence_quotes_in_source(table_candidates, enriched_result)
    assert_review_packets_well_formed(packets)
    assert_review_packet_counts_bounded(packets)
    assert_known_parser_risk_codes(
        asdict(metadata),
        section_metadata,
        semantic_candidates,
        table_candidates,
        packets,
        chunks,
    )
