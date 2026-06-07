from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from hashlib import sha256
from typing import Any

from parsers.base import ExtractionResult, sanitize_text

KNOWN_PARSER_RISK_CODES = {
    "ambiguous_nested_document_codes",
    "ambiguous_section_heading",
    "empty_page",
    "high_layout_complexity",
    "low_confidence_semantic_unit",
    "missing_document_code",
    "missing_revision",
    "ocr_required",
    "revision_family_conflict",
    "rotated_page",
    "section_hierarchy_gap",
    "sparse_text_with_images",
    "table_candidates_present",
    "visual_content_without_caption",
}

KNOWN_REVIEW_REASON_CODES = {
    "ambiguous_metadata",
    "ambiguous_section_hierarchy",
    "low_confidence_semantic_unit",
    "missing_metadata",
    "revision_family_conflict",
    "visual_table_figure_risk",
}

KNOWN_REVIEW_SEVERITIES = {"critical", "high", "medium", "low"}

KNOWN_REVIEW_DECISIONS = {
    "accept_edit_or_reject_candidate",
    "choose_canonical_revision",
    "fill_missing_metadata",
    "inspect_metadata_evidence",
    "inspect_section_hierarchy",
    "inspect_visual_evidence",
}

DOCUMENT_LEVEL_REASON_CODES = {
    "ambiguous_metadata",
    "missing_metadata",
    "revision_family_conflict",
}

GENERATED_DIAGNOSTIC_KINDS = {"visual_risk"}

MEANINGFUL_EVIDENCE_ANCHORS = {
    "page_number",
    "quote",
    "risk_code",
    "risk_codes",
    "section_path",
}


def assert_candidate_evidence_quotes_in_source(
    candidates: Iterable[Any],
    result: ExtractionResult,
) -> None:
    pages_by_number = {page.page_number: sanitize_text(page.text) for page in result.pages}
    document_text = sanitize_text("\n".join(page.text for page in result.pages))

    for index, candidate in enumerate(candidates):
        kind = _candidate_kind(candidate)
        if kind in GENERATED_DIAGNOSTIC_KINDS:
            continue
        for evidence in _candidate_evidence_items(candidate, fallback_index=index):
            quote = evidence.get("quote")
            if not isinstance(quote, str) or not sanitize_text(quote):
                raise AssertionError(f"candidate {index} has empty evidence quote")
            normalized_quote = sanitize_text(quote)
            source_text = _source_text_for_evidence(evidence, pages_by_number, document_text)
            if normalized_quote not in source_text:
                candidate_id = _candidate_id(candidate, index)
                raise AssertionError(
                    f"candidate {candidate_id} quote not found in sanitized source text: "
                    f"{normalized_quote!r}"
                )


def assert_candidate_evidence_pages_within_result(
    candidates: Iterable[Any],
    result: ExtractionResult,
) -> None:
    page_range = (
        (min(page.page_number for page in result.pages), max(page.page_number for page in result.pages))
        if result.pages
        else None
    )

    for index, candidate in enumerate(candidates):
        for evidence in _candidate_evidence_items(candidate, fallback_index=index):
            page_start = _safe_int(evidence.get("page_start"))
            page_end = _safe_int(evidence.get("page_end"))
            if page_start is None and page_end is None:
                continue
            if page_range is None:
                raise AssertionError(
                    f"candidate {index} has evidence page span but result has no parsed pages"
                )
            if page_start is None or page_end is None:
                raise AssertionError(f"candidate {index} has partial evidence page span")
            if page_start > page_end:
                raise AssertionError(
                    f"candidate {index} evidence page span is not ordered: "
                    f"{page_start}>{page_end}"
                )
            first_page, last_page = page_range
            if page_start < first_page or page_end > last_page:
                raise AssertionError(
                    f"candidate {index} evidence page span outside parsed page range "
                    f"{first_page}-{last_page}: {page_start}-{page_end}"
                )


def assert_chunks_have_valid_source_spans(chunks: Iterable[Any]) -> None:
    for index, chunk in enumerate(chunks):
        mapping = _as_mapping(chunk)
        text = mapping.get("text")
        chunk_label = mapping.get("chunk_index", index)
        if not isinstance(text, str) or not sanitize_text(text):
            raise AssertionError(f"chunk {chunk_label} text must be non-empty")
        if _safe_int(mapping.get("char_count")) != len(text):
            raise AssertionError(f"chunk {chunk_label} char_count does not match text length")
        expected_hash = sha256(text.encode()).hexdigest()
        if mapping.get("chunk_hash") != expected_hash:
            raise AssertionError(f"chunk {chunk_label} hash is not stable for its text")

        page_start = _safe_int(mapping.get("page_start"))
        page_end = _safe_int(mapping.get("page_end"))
        source_page = _safe_int(mapping.get("source_page"))
        row_start = _safe_int(mapping.get("row_start"))
        row_end = _safe_int(mapping.get("row_end"))
        sheet_name = mapping.get("sheet_name")

        if page_start is not None or page_end is not None:
            if page_start is None or page_end is None:
                raise AssertionError(f"chunk {chunk_label} has partial page span")
            if page_start <= 0 or page_end <= 0:
                raise AssertionError(f"chunk {chunk_label} page span must be positive")
            if page_start > page_end:
                raise AssertionError(
                    f"chunk {chunk_label} page span is not ordered: {page_start}>{page_end}"
                )
            if source_page is not None and not page_start <= source_page <= page_end:
                raise AssertionError(
                    f"chunk {chunk_label} source_page is outside page span: {source_page}"
                )
        elif source_page is not None and source_page <= 0:
            raise AssertionError(f"chunk {chunk_label} source_page must be positive")

        if row_start is not None or row_end is not None:
            if not isinstance(sheet_name, str) or not sheet_name:
                raise AssertionError(f"chunk {chunk_label} row span is missing sheet_name")
            if row_start is None or row_end is None:
                raise AssertionError(f"chunk {chunk_label} has partial row span")
            if row_start <= 0 or row_end <= 0:
                raise AssertionError(f"chunk {chunk_label} row span must be positive")
            if row_start > row_end:
                raise AssertionError(
                    f"chunk {chunk_label} row span is not ordered: {row_start}>{row_end}"
                )

        if source_page is None and page_start is None and row_start is None:
            raise AssertionError(f"chunk {chunk_label} has no source span")


def assert_section_metadata_hash_invariant(
    baseline_chunks: Sequence[Any],
    enriched_chunks: Sequence[Any],
) -> None:
    if len(baseline_chunks) != len(enriched_chunks):
        raise AssertionError(
            "section metadata changed chunk count: "
            f"{len(baseline_chunks)}!={len(enriched_chunks)}"
        )

    for index, (baseline, enriched) in enumerate(zip(baseline_chunks, enriched_chunks, strict=True)):
        baseline_map = _as_mapping(baseline)
        enriched_map = _as_mapping(enriched)
        baseline_text = baseline_map.get("text")
        enriched_text = enriched_map.get("text")
        if baseline_text != enriched_text:
            raise AssertionError(f"section metadata changed chunk {index} source text")
        if not isinstance(baseline_text, str):
            raise AssertionError(f"chunk {index} text is not a string")
        expected_hash = sha256(baseline_text.encode()).hexdigest()
        if baseline_map.get("chunk_hash") != expected_hash:
            raise AssertionError(f"baseline chunk {index} hash is not stable for text")
        if enriched_map.get("chunk_hash") != expected_hash:
            raise AssertionError(f"section metadata changed chunk {index} hash")


def assert_diagnostics_preserve_extraction_text(
    before: ExtractionResult,
    after: ExtractionResult,
) -> None:
    before_pages = [(page.page_number, page.text) for page in before.pages]
    after_pages = [(page.page_number, page.text) for page in after.pages]
    if before_pages != after_pages:
        raise AssertionError("diagnostics changed or removed source text from extraction pages")
    if before.total_chars != after.total_chars:
        raise AssertionError("diagnostics changed extraction total_chars")
    before_sheets = [(sheet.sheet_name, sheet.headers, sheet.rows) for sheet in before.sheets]
    after_sheets = [(sheet.sheet_name, sheet.headers, sheet.rows) for sheet in after.sheets]
    if before_sheets != after_sheets:
        raise AssertionError("diagnostics changed or removed source text from extraction sheets")


def assert_known_parser_risk_codes(*sources: Any) -> None:
    risk_codes: list[str] = []
    for source in sources:
        _collect_risk_codes(source, risk_codes)
    unknown = sorted({code for code in risk_codes if code not in KNOWN_PARSER_RISK_CODES})
    if unknown:
        raise AssertionError(f"unknown risk code(s): {unknown}")


def assert_review_packets_well_formed(packets: Iterable[Any]) -> None:
    packet_list = list(packets)
    packet_ids: set[str] = set()
    for index, packet in enumerate(packet_list):
        mapping = _as_mapping(packet)
        packet_id = _required_string(mapping, "packet_id", index)
        reason_code = _required_string(mapping, "reason_code", index)
        severity = _required_string(mapping, "severity", index)
        suggested_decision = _required_string(mapping, "suggested_decision", index)

        if re.search(r"\s", packet_id):
            raise AssertionError(f"packet {index} packet_id must be whitespace-free")
        if packet_id in packet_ids:
            raise AssertionError(f"duplicate packet_id: {packet_id}")
        packet_ids.add(packet_id)
        if reason_code not in KNOWN_REVIEW_REASON_CODES:
            raise AssertionError(f"packet {packet_id} has unknown reason_code: {reason_code}")
        if severity not in KNOWN_REVIEW_SEVERITIES:
            raise AssertionError(f"packet {packet_id} has unknown severity: {severity}")
        if suggested_decision not in KNOWN_REVIEW_DECISIONS:
            raise AssertionError(
                f"packet {packet_id} has unknown suggested_decision: {suggested_decision}"
            )

        evidence = mapping.get("evidence")
        if not isinstance(evidence, list):
            raise AssertionError(f"packet {packet_id} evidence must be a list")
        if not evidence and reason_code not in DOCUMENT_LEVEL_REASON_CODES:
            raise AssertionError(
                f"packet {packet_id} needs evidence or an explicit document-level reason"
            )
        if not evidence and not _risk_code_tuple(mapping.get("risk_codes")):
            raise AssertionError(f"packet {packet_id} document-level reason needs risk_codes")
        for evidence_index, evidence_item in enumerate(evidence):
            if not isinstance(evidence_item, dict):
                raise AssertionError(
                    f"packet {packet_id} evidence item {evidence_index} must be a dict"
                )
            if not _has_meaningful_evidence_anchor(evidence_item):
                raise AssertionError(
                    f"packet {packet_id} evidence item {evidence_index} needs an anchor"
                )
    assert_known_parser_risk_codes(packet_list)


def assert_review_packet_counts_bounded(
    packets: Iterable[Any],
    *,
    max_equivalent_packets: int = 1,
) -> None:
    packet_list = list(packets)
    counts = Counter(_review_packet_equivalence_key(packet) for packet in packet_list)
    repeated = {
        key: count
        for key, count in counts.items()
        if count > max_equivalent_packets
    }
    if repeated:
        raise AssertionError(f"equivalent review packet count exceeds bound: {repeated}")


def _candidate_kind(candidate: Any) -> str:
    mapping = _as_mapping(candidate)
    return str(mapping.get("kind") or "")


def _candidate_id(candidate: Any, fallback_index: int) -> str:
    mapping = _as_mapping(candidate)
    candidate_id = mapping.get("candidate_id")
    if isinstance(candidate_id, str) and candidate_id:
        return candidate_id
    return f"index:{fallback_index}"


def _candidate_evidence_items(candidate: Any, *, fallback_index: int) -> list[dict[str, Any]]:
    mapping = _as_mapping(candidate)
    if "evidence" in mapping:
        evidence = mapping.get("evidence")
        candidate_id = _candidate_id(candidate, fallback_index)
        if isinstance(evidence, Mapping):
            return [dict(evidence)]
        if isinstance(evidence, list):
            if not evidence:
                raise AssertionError(f"candidate {candidate_id} has empty evidence collection")
            evidence_items: list[dict[str, Any]] = []
            for evidence_index, item in enumerate(evidence):
                if not isinstance(item, Mapping):
                    raise AssertionError(
                        f"candidate {candidate_id} evidence item {evidence_index} must be a dict"
                    )
                evidence_items.append(dict(item))
            return evidence_items
        raise AssertionError(f"candidate {candidate_id} has unsupported evidence collection")

    page_number = _safe_int(mapping.get("page_number"))
    page_start = _safe_int(mapping.get("page_start")) or page_number
    page_end = _safe_int(mapping.get("page_end")) or page_start
    return [
        {
            "quote": mapping.get("quote"),
            "page_start": page_start,
            "page_end": page_end,
        }
    ]


def _source_text_for_evidence(
    evidence: Mapping[str, Any],
    pages_by_number: Mapping[int, str],
    document_text: str,
) -> str:
    page_start = _safe_int(evidence.get("page_start"))
    page_end = _safe_int(evidence.get("page_end")) or page_start
    if page_start is None or page_end is None:
        return document_text
    page_texts = [
        pages_by_number[page_number]
        for page_number in range(page_start, page_end + 1)
        if page_number in pages_by_number
    ]
    return sanitize_text("\n".join(page_texts)) if page_texts else document_text


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return {
        name: getattr(value, name)
        for name in dir(value)
        if not name.startswith("_") and not callable(getattr(value, name))
    }


def _collect_risk_codes(value: Any, target: list[str]) -> None:
    if value is None or isinstance(value, str):
        return
    if is_dataclass(value) and not isinstance(value, type):
        _collect_risk_codes(asdict(value), target)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"risk_code"}:
                if isinstance(item, str) and item:
                    target.append(item)
                continue
            if key in {"risk_codes", "structure_risk_codes"}:
                target.extend(_risk_code_tuple(item))
                continue
            if key == "risk_code_counts" and isinstance(item, Mapping):
                target.extend(str(code) for code in item if str(code))
                continue
            _collect_risk_codes(item, target)
        return
    if isinstance(value, Iterable):
        for item in value:
            _collect_risk_codes(item, target)


def _review_packet_equivalence_key(packet: Any) -> tuple[str, tuple[str, ...], str | None, int | None]:
    mapping = _as_mapping(packet)
    return (
        str(mapping.get("reason_code") or ""),
        _risk_code_tuple(mapping.get("risk_codes")),
        _optional_string(mapping.get("section_path")),
        _safe_int(mapping.get("page_number")),
    )


def _has_meaningful_evidence_anchor(evidence_item: Mapping[str, Any]) -> bool:
    for key in MEANINGFUL_EVIDENCE_ANCHORS:
        value = evidence_item.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, int):
            return True
        if isinstance(value, list | tuple | set) and any(str(item).strip() for item in value):
            return True
    return False


def _risk_code_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        return tuple(sorted(str(code) for code in value if str(code)))
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Iterable):
        return tuple(sorted({str(code) for code in value if str(code)}))
    return ()


def _required_string(mapping: Mapping[str, Any], key: str, index: int) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AssertionError(f"packet {index} missing {key}")
    return value.strip()


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
