from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from source_pack.evidence import evidence_from_csv_row, evidence_from_markdown_section
from source_pack.ids import stable_uuid
from source_pack.readers import CsvRow, MarkdownSection

FACT_SCHEMA_VERSION = "source_pack.fact.v1"
RULE_SCHEMA_VERSION = "source_pack.rule.v1"

# document_types that produce facts (from CSV rows)
_FACT_CSV_TYPES: frozenset[str] = frozenset(
    {
        "catalog",
        "catalog_backlog",
        "normalization_catalog",
        "forms_catalog",
        "excipient_matrix",
        "supplier_catalog",
        "normalization_policy",
        "inventory_catalog",
        "price_catalog",
        "operations",
    }
)

# document_types that produce rules from CSV rows
_RULE_CSV_TYPES: frozenset[str] = frozenset(
    {
        "tool_policy",
        "quote_rules",
        "fulfillment_policy",
        "risk_matrix",
        "safety_matrix",
        "population_safety",
        "interaction_triggers",
        "regulatory_matrix",
        "mutation_contract",
    }
)

# document_types that produce rules from Markdown sections
_RULE_MD_TYPES: frozenset[str] = frozenset(
    {
        "rules",
        "commercial_policy",
        "safety_policy",
        "clinical_boundary_policy",
        "labeling_policy",
        "stability_policy",
        "style_policy",
        "inventory_policy",
        "calendar_policy",
        "audit_policy",
        "refusal_examples",
        "sales_playbook",
        "objection_playbook",
        "quality_policy",
        "commercial_gap_policy",
    }
)

# document_types that produce test items
_TEST_TYPES: frozenset[str] = frozenset(
    {
        "tests",
        "eval_seed",
        "eval_set",
        "clinical_eval",
        "adverse_event_eval",
        "conversation_eval",
        "tool_trace_eval",
        "calendar_scenarios",
        "mutation_scenarios",
        "quote_scenarios",
        "release_gate",
        "regression_suite",
        "readiness_scorecard",
        "builder_spec",
        "style_guide",
    }
)

# Synthetic flag document types
_SYNTHETIC_FACT_TYPES: frozenset[str] = frozenset({"inventory_catalog", "price_catalog"})


@dataclass
class ExtractedDocument:
    facts: list[dict[str, Any]] = field(default_factory=list)
    rules: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    tests: list[dict[str, Any]] = field(default_factory=list)
    memory_policy_patch: dict[str, Any] = field(default_factory=dict)
    tool_recommendations: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)


def extract_document(
    document_type: str,
    source: dict[str, Any],
    csv_rows: list[CsvRow] | None,
    markdown_sections: list[MarkdownSection] | None,
) -> ExtractedDocument:
    """Dispatch extraction by document_type and return an ExtractedDocument."""
    source_id_uuid = UUID(source["id"])
    source_filename = source["original_filename"]
    result = ExtractedDocument()

    if document_type == "readiness":
        _extract_gaps(result, document_type, source_id_uuid, source_filename, csv_rows)

    elif document_type == "memory_tool_policy":
        _extract_memory_policy(result, source_id_uuid, source_filename, markdown_sections)

    elif document_type == "evidence_map":
        # evidence only — collect evidence but no facts/rules
        _collect_evidence_csv(result, source_id_uuid, csv_rows)
        _collect_evidence_md(result, source_id_uuid, markdown_sections)

    elif document_type == "policy":
        # identity-like sections → facts, rule sections → rules
        _extract_policy_mixed(result, document_type, source_id_uuid, source_filename, markdown_sections, csv_rows)

    elif document_type == "business_profile":
        _extract_facts_csv(result, document_type, source_id_uuid, source_filename, csv_rows)
        _extract_facts_md(result, document_type, source_id_uuid, source_filename, markdown_sections)

    elif document_type in _FACT_CSV_TYPES:
        _extract_facts_csv(result, document_type, source_id_uuid, source_filename, csv_rows)
        _extract_facts_md(result, document_type, source_id_uuid, source_filename, markdown_sections)

    elif document_type in _RULE_MD_TYPES:
        _extract_rules_md(result, document_type, source_id_uuid, source_filename, markdown_sections)

    elif document_type in _RULE_CSV_TYPES:
        _extract_rules_csv(result, document_type, source_id_uuid, source_filename, csv_rows)

    elif document_type in _TEST_TYPES:
        _extract_tests_csv(result, document_type, source_id_uuid, source_filename, csv_rows)
        _extract_tests_md(result, document_type, source_id_uuid, source_filename, markdown_sections)

    else:
        # Default: rules from sections/rows
        if markdown_sections:
            _extract_rules_md(result, document_type, source_id_uuid, source_filename, markdown_sections)
        if csv_rows:
            _extract_rules_csv(result, document_type, source_id_uuid, source_filename, csv_rows)

    return result


# ---------------------------------------------------------------------------
# Fact extraction
# ---------------------------------------------------------------------------


def _extract_facts_csv(
    result: ExtractedDocument,
    document_type: str,
    source_id: UUID,
    filename: str,
    csv_rows: list[CsvRow] | None,
) -> None:
    if not csv_rows:
        return
    is_synthetic = document_type in _SYNTHETIC_FACT_TYPES
    fact_type = _fact_type_from_document_type(document_type)
    for row in csv_rows:
        ev = evidence_from_csv_row(source_id, row)
        chunk_id = ev["chunk_id"]
        ev_id = ev["id"]
        content: dict[str, Any] = dict(row.row_data)
        if is_synthetic:
            content["is_synthetic"] = True
        fact: dict[str, Any] = {
            "id": stable_uuid(f"fact:{filename}:row:{row.row_number}"),
            "fact_type": fact_type,
            "schema_version": FACT_SCHEMA_VERSION,
            "normalized_content": content,
            "confidence": 1.0,
            "source_id": source_id,
            "chunk_id": chunk_id,
            "evidence_span_ids": [ev_id],
            "published_at": None,
        }
        result.facts.append(fact)
        result.evidence.append(ev)


def _extract_facts_md(
    result: ExtractedDocument,
    document_type: str,
    source_id: UUID,
    filename: str,
    markdown_sections: list[MarkdownSection] | None,
) -> None:
    if not markdown_sections:
        return
    fact_type = _fact_type_from_document_type(document_type)
    for section in markdown_sections:
        ev = evidence_from_markdown_section(source_id, section)
        chunk_id = ev["chunk_id"]
        ev_id = ev["id"]
        fact: dict[str, Any] = {
            "id": stable_uuid(f"fact:{filename}:{section.anchor}"),
            "fact_type": fact_type,
            "schema_version": FACT_SCHEMA_VERSION,
            "normalized_content": {
                "heading": section.heading,
                "body": section.body[:800],
            },
            "confidence": 1.0,
            "source_id": source_id,
            "chunk_id": chunk_id,
            "evidence_span_ids": [ev_id],
            "published_at": None,
        }
        result.facts.append(fact)
        result.evidence.append(ev)


# ---------------------------------------------------------------------------
# Rule extraction
# ---------------------------------------------------------------------------


def _extract_rules_md(
    result: ExtractedDocument,
    document_type: str,
    source_id: UUID,
    filename: str,
    markdown_sections: list[MarkdownSection] | None,
) -> None:
    if not markdown_sections:
        return
    rule_type = _rule_type_from_document_type(document_type)
    for section in markdown_sections:
        ev = evidence_from_markdown_section(source_id, section)
        chunk_id = ev["chunk_id"]
        ev_id = ev["id"]
        rule: dict[str, Any] = {
            "id": stable_uuid(f"rule:{filename}:{section.anchor}"),
            "rule_type": rule_type,
            "schema_version": RULE_SCHEMA_VERSION,
            "condition": {"section": section.heading},
            "action": {"text": section.body[:800]},
            "priority": section.start_line,
            "confidence": 1.0,
            "source_id": source_id,
            "chunk_id": chunk_id,
            "evidence_span_ids": [ev_id],
            "published_at": None,
        }
        result.rules.append(rule)
        result.evidence.append(ev)


def _extract_rules_csv(
    result: ExtractedDocument,
    document_type: str,
    source_id: UUID,
    filename: str,
    csv_rows: list[CsvRow] | None,
) -> None:
    if not csv_rows:
        return
    rule_type = _rule_type_from_document_type(document_type)
    for row in csv_rows:
        ev = evidence_from_csv_row(source_id, row)
        chunk_id = ev["chunk_id"]
        ev_id = ev["id"]
        rule: dict[str, Any] = {
            "id": stable_uuid(f"rule:{filename}:row:{row.row_number}"),
            "rule_type": rule_type,
            "schema_version": RULE_SCHEMA_VERSION,
            "condition": _extract_condition(row.row_data),
            "action": _extract_action(row.row_data),
            "priority": row.row_number,
            "confidence": 1.0,
            "source_id": source_id,
            "chunk_id": chunk_id,
            "evidence_span_ids": [ev_id],
            "published_at": None,
        }
        result.rules.append(rule)
        result.evidence.append(ev)


# ---------------------------------------------------------------------------
# Gap extraction
# ---------------------------------------------------------------------------


def _extract_gaps(
    result: ExtractedDocument,
    document_type: str,
    source_id: UUID,
    filename: str,
    csv_rows: list[CsvRow] | None,
) -> None:
    if not csv_rows:
        return
    _SKIP = frozenset({"gap_type", "kind", "description", "gap_description", "severity", "status"})
    for row in csv_rows:
        ev = evidence_from_csv_row(source_id, row)
        result.evidence.append(ev)
        gap: dict[str, Any] = {
            "id": str(stable_uuid(f"gap:{filename}:row:{row.row_number}")),
            "kind": row.row_data.get("gap_type") or row.row_data.get("kind") or "unknown",
            "description": row.row_data.get("description") or row.row_data.get("gap_description") or "",
            "severity": row.row_data.get("severity") or "medium",
            "status": row.row_data.get("status") or "open",
            "source_ids": [str(source_id)],
            "created_at": None,
            "details": {k: v for k, v in row.row_data.items() if k not in _SKIP},
        }
        result.gaps.append(gap)


# ---------------------------------------------------------------------------
# Test extraction
# ---------------------------------------------------------------------------


def _extract_tests_csv(
    result: ExtractedDocument,
    document_type: str,
    source_id: UUID,
    filename: str,
    csv_rows: list[CsvRow] | None,
) -> None:
    if not csv_rows:
        return
    for row in csv_rows:
        ev = evidence_from_csv_row(source_id, row)
        result.evidence.append(ev)
        test: dict[str, Any] = {
            "id": str(stable_uuid(f"test:{filename}:row:{row.row_number}")),
            "name": (
                row.row_data.get("name")
                or row.row_data.get("test_name")
                or row.row_data.get("scenario")
                or f"test_{row.row_number}"
            ),
            "status": "pending",
            "prompt": (
                row.row_data.get("prompt")
                or row.row_data.get("query")
                or row.row_data.get("question")
                or row.row_data.get("user_query")
                or ""
            ),
            "expected_behavior": (
                row.row_data.get("expected_behavior")
                or row.row_data.get("expected_action")
                or row.row_data.get("expected_primary_action")
                or ""
            ),
            "expected_answer_contains": [],
            "forbidden_answer_contains": [],
            "required_fact_ids": [],
            "required_rule_ids": [],
            "required_evidence_span_ids": [],
            "must_not_use_unvalidated_data": True,
            "critical": row.row_data.get("critical", "").lower() in ("true", "yes", "1"),
            "assertion": {},
            "details": dict(row.row_data),
        }
        result.tests.append(test)


def _extract_tests_md(
    result: ExtractedDocument,
    document_type: str,
    source_id: UUID,
    filename: str,
    markdown_sections: list[MarkdownSection] | None,
) -> None:
    if not markdown_sections:
        return
    for section in markdown_sections:
        ev = evidence_from_markdown_section(source_id, section)
        result.evidence.append(ev)
        test: dict[str, Any] = {
            "id": str(stable_uuid(f"test:{filename}:{section.anchor}")),
            "name": section.heading,
            "status": "pending",
            "prompt": "",
            "expected_behavior": section.body[:500],
            "expected_answer_contains": [],
            "forbidden_answer_contains": [],
            "required_fact_ids": [],
            "required_rule_ids": [],
            "required_evidence_span_ids": [],
            "must_not_use_unvalidated_data": True,
            "critical": False,
            "assertion": {},
            "details": {"anchor": section.anchor, "filename": section.filename},
        }
        result.tests.append(test)


# ---------------------------------------------------------------------------
# Memory policy & tool recommendations extraction
# ---------------------------------------------------------------------------

_DENIED_KEYS: frozenset[str] = frozenset(
    {
        "diagnosis",
        "full_prescription",
        "card_numbers",
        "controlled_substance_details",
    }
)

_MEMORY_HEADING_RE = re.compile(r"\b(memory|retention)\b", re.IGNORECASE)


def _extract_memory_policy(
    result: ExtractedDocument,
    source_id: UUID,
    filename: str,
    markdown_sections: list[MarkdownSection] | None,
) -> None:
    if not markdown_sections:
        result.memory_policy_patch = {}
        return

    patch: dict[str, Any] = {}

    for section in markdown_sections:
        ev = evidence_from_markdown_section(source_id, section)
        result.evidence.append(ev)

        heading_lower = section.heading.lower()
        body = section.body

        if "retention" in heading_lower or "memory" in heading_lower:
            # Parse bullets from body
            notes_lines: list[str] = []

            for line in body.splitlines():
                stripped = line.strip().lstrip("-").strip()
                if not stripped:
                    continue
                if not any(k in stripped.lower() for k in _DENIED_KEYS):
                    notes_lines.append(stripped)

            if "allowed" in heading_lower or "permitted" in heading_lower:
                patch["allowed"] = [line.strip().lstrip("-").strip() for line in body.splitlines() if line.strip()]
            elif "forbidden" in heading_lower or "denied" in heading_lower or "not" in heading_lower:
                patch["denied"] = [line.strip().lstrip("-").strip() for line in body.splitlines() if line.strip()]
            else:
                if notes_lines:
                    patch.setdefault("notes", " ".join(notes_lines[:5]))
                patch.setdefault("retention", body[:200].strip())

        elif "tool" in heading_lower:
            # tool-section: produce a tool recommendation entry
            rec: dict[str, Any] = {
                "id": str(stable_uuid(f"tool_rec:{filename}:{section.anchor}")),
                "tool_name": section.heading,
                "category": "tool_policy",
                "risk_level": "medium",
                "recommended": True,
                "allowed_operations": [],
                "requires_human_approval": False,
                "input_policy": "",
                "output_policy": "",
                "reason": section.body[:200],
                "confidence": 1.0,
            }
            result.tool_recommendations.append(rec)

    result.memory_policy_patch = patch


# ---------------------------------------------------------------------------
# Mixed policy extraction (policy document_type)
# ---------------------------------------------------------------------------

_IDENTITY_HEADING_RE = re.compile(
    r"\b(name|address|contact|profile|identity|about|hours|overview|mission)\b",
    re.IGNORECASE,
)


def _extract_policy_mixed(
    result: ExtractedDocument,
    document_type: str,
    source_id: UUID,
    filename: str,
    markdown_sections: list[MarkdownSection] | None,
    csv_rows: list[CsvRow] | None,
) -> None:
    if markdown_sections:
        rule_type = _rule_type_from_document_type(document_type)
        fact_type = _fact_type_from_document_type(document_type)
        for section in markdown_sections:
            ev = evidence_from_markdown_section(source_id, section)
            result.evidence.append(ev)
            if _IDENTITY_HEADING_RE.search(section.heading):
                fact: dict[str, Any] = {
                    "id": stable_uuid(f"fact:{filename}:{section.anchor}"),
                    "fact_type": fact_type,
                    "schema_version": FACT_SCHEMA_VERSION,
                    "normalized_content": {"heading": section.heading, "body": section.body[:800]},
                    "confidence": 1.0,
                    "source_id": source_id,
                    "chunk_id": ev["chunk_id"],
                    "evidence_span_ids": [ev["id"]],
                    "published_at": None,
                }
                result.facts.append(fact)
            else:
                rule: dict[str, Any] = {
                    "id": stable_uuid(f"rule:{filename}:{section.anchor}"),
                    "rule_type": rule_type,
                    "schema_version": RULE_SCHEMA_VERSION,
                    "condition": {"section": section.heading},
                    "action": {"text": section.body[:800]},
                    "priority": section.start_line,
                    "confidence": 1.0,
                    "source_id": source_id,
                    "chunk_id": ev["chunk_id"],
                    "evidence_span_ids": [ev["id"]],
                    "published_at": None,
                }
                result.rules.append(rule)
    if csv_rows:
        _extract_rules_csv(result, document_type, source_id, filename, csv_rows)


# ---------------------------------------------------------------------------
# Evidence-only collection helpers
# ---------------------------------------------------------------------------


def _collect_evidence_csv(
    result: ExtractedDocument,
    source_id: UUID,
    csv_rows: list[CsvRow] | None,
) -> None:
    if not csv_rows:
        return
    for row in csv_rows:
        result.evidence.append(evidence_from_csv_row(source_id, row))


def _collect_evidence_md(
    result: ExtractedDocument,
    source_id: UUID,
    markdown_sections: list[MarkdownSection] | None,
) -> None:
    if not markdown_sections:
        return
    for section in markdown_sections:
        result.evidence.append(evidence_from_markdown_section(source_id, section))


# ---------------------------------------------------------------------------
# Helper: fact_type and rule_type derivation
# ---------------------------------------------------------------------------

_FACT_TYPE_MAP: dict[str, str] = {
    "catalog": "active_ingredient",
    "catalog_backlog": "catalog_entry",
    "normalization_catalog": "normalization_entry",
    "forms_catalog": "pharmaceutical_form",
    "excipient_matrix": "excipient",
    "supplier_catalog": "supplier",
    "normalization_policy": "normalization_policy",
    "inventory_catalog": "inventory_status",
    "price_catalog": "price_entry",
    "operations": "operation_state",
    "business_profile": "business_profile",
    "policy": "policy_profile",
}

_RULE_TYPE_MAP: dict[str, str] = {
    "rules": "sales_triage",
    "commercial_policy": "quote_policy",
    "safety_policy": "safety_policy",
    "clinical_boundary_policy": "clinical_boundary",
    "labeling_policy": "labeling_policy",
    "stability_policy": "stability_policy",
    "style_policy": "style_policy",
    "inventory_policy": "inventory_policy",
    "calendar_policy": "calendar_policy",
    "audit_policy": "audit_policy",
    "refusal_examples": "refusal_rule",
    "sales_playbook": "sales_playbook",
    "objection_playbook": "objection_handling",
    "quality_policy": "quality_policy",
    "commercial_gap_policy": "commercial_gap",
    "tool_policy": "tool_policy",
    "quote_rules": "quote_eligibility",
    "fulfillment_policy": "fulfillment_policy",
    "risk_matrix": "risk_rule",
    "safety_matrix": "safety_rule",
    "population_safety": "population_safety",
    "interaction_triggers": "interaction_trigger",
    "regulatory_matrix": "regulatory_rule",
    "mutation_contract": "mutation_rule",
    "policy": "policy_rule",
}


def _fact_type_from_document_type(document_type: str) -> str:
    return _FACT_TYPE_MAP.get(document_type, document_type.replace("-", "_"))


def _rule_type_from_document_type(document_type: str) -> str:
    return _RULE_TYPE_MAP.get(document_type, document_type.replace("-", "_"))


# ---------------------------------------------------------------------------
# Condition / action column extraction helpers
# ---------------------------------------------------------------------------

_CONDITION_KEYS = ("trigger", "condition", "when", "if", "user_intent_class", "item_or_class", "blocking_conditions")
_ACTION_KEYS = ("action", "response", "then", "result", "next_action", "expected_final_action", "allowed_quote_status", "expected_action")


def _extract_condition(row_data: dict[str, str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in _CONDITION_KEYS:
        if row_data.get(key):
            values[key] = row_data[key]
    return values or {"match": dict(row_data)}


def _extract_action(row_data: dict[str, str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in _ACTION_KEYS:
        if row_data.get(key):
            values[key] = row_data[key]
    return values or {"apply": dict(row_data)}
