from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class IndustrialReviewPacket:
    packet_id: str
    reason_code: str
    severity: str
    evidence: list[dict[str, Any]]
    suggested_decision: str
    section_path: str | None = None
    page_number: int | None = None
    risk_codes: tuple[str, ...] = field(default_factory=tuple)


def build_review_packets(
    *,
    document_id: str,
    metadata: dict[str, Any] | None = None,
    section_diagnostics: dict[str, Any] | None = None,
    semantic_candidates: list[dict[str, Any]] | None = None,
    table_figure_candidates: list[dict[str, Any]] | None = None,
    revision_conflicts: list[dict[str, Any]] | None = None,
    quality_profile: dict[str, Any] | None = None,
) -> list[IndustrialReviewPacket]:
    packets: list[IndustrialReviewPacket] = []
    packets.extend(_metadata_packets(document_id, metadata or {}))
    packets.extend(_revision_conflict_packets(document_id, revision_conflicts or []))
    packets.extend(_quality_profile_packets(document_id, quality_profile or {}))
    packets.extend(_section_packets(document_id, section_diagnostics or {}))
    packets.extend(_semantic_packets(document_id, semantic_candidates or []))
    packets.extend(_table_figure_packets(document_id, table_figure_candidates or []))
    return sorted(packets, key=lambda packet: packet.packet_id)


def summarize_review_packets(packets: list[IndustrialReviewPacket]) -> dict[str, Any]:
    reason_counts = Counter(packet.reason_code for packet in packets)
    severity_counts = Counter(packet.severity for packet in packets)
    return {
        "total_packet_count": len(packets),
        "reason_code_counts": dict(sorted(reason_counts.items())),
        "severity_counts": dict(sorted(severity_counts.items())),
    }


def review_packets_to_metadata(packets: list[IndustrialReviewPacket]) -> list[dict[str, Any]]:
    return [
        {
            **asdict(packet),
            "risk_codes": list(packet.risk_codes),
        }
        for packet in packets
    ]


def _metadata_packets(document_id: str, metadata: dict[str, Any]) -> list[IndustrialReviewPacket]:
    gap_codes = [str(code) for code in metadata.get("gap_codes", [])]
    packets = [
        IndustrialReviewPacket(
            packet_id=f"{document_id}:missing_metadata:{gap_code}",
            reason_code="missing_metadata",
            severity="high",
            evidence=[{"risk_code": gap_code}],
            suggested_decision="fill_missing_metadata",
            risk_codes=(gap_code,),
        )
        for gap_code in sorted(gap_codes)
        if gap_code.startswith("missing_")
    ]
    packets.extend(
        IndustrialReviewPacket(
            packet_id=f"{document_id}:ambiguous_metadata:{gap_code}",
            reason_code="ambiguous_metadata",
            severity="critical",
            evidence=[{"risk_code": gap_code}],
            suggested_decision="inspect_metadata_evidence",
            risk_codes=(gap_code,),
        )
        for gap_code in sorted(gap_codes)
        if gap_code.startswith("ambiguous_")
    )
    return packets


def _revision_conflict_packets(
    document_id: str,
    conflicts: list[dict[str, Any]],
) -> list[IndustrialReviewPacket]:
    packets: list[IndustrialReviewPacket] = []
    for index, conflict in enumerate(conflicts):
        code = str(conflict.get("document_code") or "unknown")
        revision = str(conflict.get("revision") or "unknown")
        packets.append(
            IndustrialReviewPacket(
                packet_id=f"{document_id}:revision_family_conflict:{code}:{revision}:{index}",
                reason_code="revision_family_conflict",
                severity="critical",
                evidence=[dict(conflict)],
                suggested_decision="choose_canonical_revision",
                risk_codes=("revision_family_conflict",),
            )
        )
    return packets


def _quality_profile_packets(
    document_id: str,
    profile: dict[str, Any],
) -> list[IndustrialReviewPacket]:
    if profile.get("document_family_candidate") is not True:
        return []
    risk_codes = tuple(sorted({str(code) for code in profile.get("risk_codes", [])}))
    evidence = [
        item for item in profile.get("nested_identifiers", []) if isinstance(item, dict)
    ][:10]
    if not evidence:
        evidence = [{"risk_code": "document_family_candidate"}]
    return [
        IndustrialReviewPacket(
            packet_id=f"{document_id}:document_family_requires_review",
            reason_code="document_family_requires_review",
            severity="critical",
            evidence=evidence,
            suggested_decision="classify_collection_before_publication",
            risk_codes=risk_codes or ("document_family_candidate",),
        )
    ]


def _section_packets(
    document_id: str,
    diagnostics: dict[str, Any],
) -> list[IndustrialReviewPacket]:
    packets: list[IndustrialReviewPacket] = []
    evidence_by_risk: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for span in diagnostics.get("section_spans", []):
        if not isinstance(span, dict):
            continue
        span_risks = tuple(sorted({str(code) for code in span.get("risk_codes", [])}))
        if not span_risks:
            continue
        section_path = _optional_string(span.get("section_path"))
        page_number = _safe_int(span.get("page_start"))
        evidence = {
            "section_path": section_path,
            "section_title": span.get("section_title"),
            "page_number": page_number,
            "risk_codes": list(span_risks),
        }
        for risk_code in span_risks:
            evidence_by_risk[risk_code].append(evidence)

    all_risk_codes = sorted({
        str(code)
        for code in diagnostics.get("risk_codes", [])
    } | set(evidence_by_risk))
    for risk_code in all_risk_codes:
        evidence_items = evidence_by_risk.get(risk_code) or [{"risk_code": risk_code}]
        section_path = _single_evidence_section_path(evidence_items)
        page_number = _first_page(evidence_items)
        packets.append(
            IndustrialReviewPacket(
                packet_id=f"{document_id}:ambiguous_section_hierarchy:{risk_code}",
                reason_code="ambiguous_section_hierarchy",
                severity="medium",
                evidence=evidence_items,
                suggested_decision="inspect_section_hierarchy",
                section_path=section_path,
                page_number=page_number,
                risk_codes=(risk_code,),
            )
        )
    return packets


def _semantic_packets(
    document_id: str,
    candidates: list[dict[str, Any]],
) -> list[IndustrialReviewPacket]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        confidence = _safe_float(candidate.get("confidence"))
        if confidence is None or confidence >= 0.6:
            continue
        evidence = candidate.get("evidence")
        section_path = None
        page_number = None
        if isinstance(evidence, dict):
            section_path = _optional_string(evidence.get("section_path"))
            page_number = _safe_int(evidence.get("page_start"))
        group_key = section_path or "unsectioned"
        grouped[group_key].append(
            {
                "kind": candidate.get("kind"),
                "confidence": confidence,
                "quote": evidence.get("quote") if isinstance(evidence, dict) else None,
                "section_path": section_path,
                "page_number": page_number,
            }
        )
    return [
        IndustrialReviewPacket(
            packet_id=f"{document_id}:low_confidence_semantic_unit:{section_path}",
            reason_code="low_confidence_semantic_unit",
            severity="medium",
            evidence=evidence_items,
            suggested_decision="accept_edit_or_reject_candidate",
            section_path=None if section_path == "unsectioned" else section_path,
            page_number=_first_page(evidence_items),
            risk_codes=("low_confidence_semantic_unit",),
        )
        for section_path, evidence_items in sorted(grouped.items())
    ]


def _table_figure_packets(
    document_id: str,
    candidates: list[dict[str, Any]],
) -> list[IndustrialReviewPacket]:
    packets: list[IndustrialReviewPacket] = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("kind") != "visual_risk":
            continue
        page_number = _safe_int(candidate.get("page_number"))
        risk_codes = tuple(sorted({str(code) for code in candidate.get("risk_codes", [])}))
        packets.append(
            IndustrialReviewPacket(
                packet_id=f"{document_id}:visual_table_figure_risk:{page_number or 'unknown'}",
                reason_code="visual_table_figure_risk",
                severity="medium",
                evidence=[dict(candidate)],
                suggested_decision="inspect_visual_evidence",
                page_number=page_number,
                risk_codes=risk_codes,
            )
        )
    return packets


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_page(evidence_items: list[dict[str, Any]]) -> int | None:
    for item in evidence_items:
        page_number = _safe_int(item.get("page_number"))
        if page_number is not None:
            return page_number
    return None


def _single_evidence_section_path(evidence_items: list[dict[str, Any]]) -> str | None:
    paths = {
        section_path
        for item in evidence_items
        if (section_path := _optional_string(item.get("section_path"))) is not None
    }
    if len(paths) == 1:
        return next(iter(paths))
    return None
