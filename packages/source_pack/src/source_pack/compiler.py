from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from context_builder.schemas.context_bundle import (
    ContextBundleEvidence,
    ContextBundleFact,
    ContextBundleGap,
    ContextBundleIdentity,
    ContextBundleIntegrity,
    ContextBundleMemoryPolicy,
    ContextBundleReadiness,
    ContextBundleResponse,
    ContextBundleRule,
    ContextBundleSource,
    ContextBundleTest,
    ContextBundleToolRecommendation,
)
from context_builder.services.query_audit import hash_payload

from source_pack.evidence import csv_row_evidence, markdown_section_evidence
from source_pack.ids import slugify, stable_uuid
from source_pack.manifest import SourcePackManifest, preflight_source_pack
from source_pack.readers import CsvRow, list_numbered_sources, read_csv_rows, read_text
from source_pack.validators import sanitize_text, validate_no_forbidden_payload

SCHEMA_VERSION: Literal["context_bundle.v1"] = "context_bundle.v1"
CANONICALIZATION = "json.sort_keys.compact.v1"
WORKSPACE_ID = stable_uuid("workspace:compounding-pharmacy-gold")
GENERATED_AT = datetime(2026, 5, 25, tzinfo=UTC)

RULE_FILES = {
    "04_allergens_excipients_triage.csv": "allergen_handoff",
    "05_sales_triage_rules.md": "sales_triage",
    "10_quote_pricing_policy.md": "quote_pricing",
    "16_memory_and_tool_policy.md": "memory_tool_policy",
    "21_controlled_antimicrobial_handoff_matrix.csv": "safety_handoff",
    "28_inventory_freshness_policy.md": "inventory_freshness",
    "31_calendar_event_policy.md": "calendar_event",
    "40_quote_rules_matrix.csv": "quote_rule",
    "53_tool_calling_policy_matrix.csv": "tool_policy",
    "55_audit_and_rollback_policy.md": "audit_rollback",
    "63_release_gate_eval_suite.md": "release_gate",
}
TEST_FILES = {
    "06_context_builder_expected_tests.md",
    "17_sample_user_queries.csv",
    "47_adverse_event_scenarios.csv",
    "49_clinical_boundary_eval_cases.csv",
    "54_tool_calling_expected_traces.csv",
    "58_long_conversation_scenarios.csv",
    "59_synthetic_customer_query_eval_set.csv",
    "63_release_gate_eval_suite.md",
    "64_failure_modes_and_regression_tests.md",
}
GAP_FILES = {"14_known_gaps_and_publish_gates.csv", "43_payment_discount_gap_policy.md"}


class SourcePackPreflightError(ValueError):
    pass


def compile_source_pack(source_dir: Path) -> ContextBundleResponse:
    preflight = preflight_source_pack(source_dir)
    if preflight.missing_listed_files:
        raise SourcePackPreflightError(
            "missing manifest files: " + ", ".join(preflight.missing_listed_files)
        )
    if preflight.extra_unlisted_files:
        raise SourcePackPreflightError(
            "extra unlisted source files: " + ", ".join(preflight.extra_unlisted_files)
        )
    manifest = preflight.manifest
    source_paths = list_numbered_sources(source_dir)
    sources = [_source_from_path(path, manifest) for path in source_paths]
    source_ids = {source.original_filename or "": source.id for source in sources}

    evidence: list[ContextBundleEvidence] = []
    evidence_by_anchor: dict[str, UUID] = {}
    evidence_by_file: dict[str, UUID] = {}
    csv_rows_by_file: dict[str, list[CsvRow]] = {}
    markdown_sections_by_file: dict[str, list[ContextBundleEvidence]] = {}

    for path in source_paths:
        filename = path.name
        source_id = source_ids[filename]
        _validate_raw_file(path)
        if path.suffix.lower() == ".csv":
            rows = read_csv_rows(path)
            csv_rows_by_file[filename] = rows
            for row in rows:
                item = csv_row_evidence(filename=filename, source_id=source_id, row=row)
                evidence.append(item)
                evidence_by_file.setdefault(filename, item.id)
                anchor = row.row_data.get("evidence_anchor") or row.row_data.get("anchor")
                if anchor:
                    evidence_by_anchor[anchor] = item.id
        else:
            sections = markdown_section_evidence(
                filename=filename,
                source_id=source_id,
                text=read_text(path),
            )
            markdown_sections_by_file[filename] = sections
            for section in sections:
                evidence.append(section)
                evidence_by_file.setdefault(filename, section.id)
                for anchor in _anchors_from_quote(section.quote or ""):
                    evidence_by_anchor.setdefault(anchor, section.id)

    facts = _facts(csv_rows_by_file, manifest, source_ids, evidence_by_anchor, evidence_by_file)
    rules = _rules(
        csv_rows_by_file,
        markdown_sections_by_file,
        source_ids,
        evidence_by_anchor,
        evidence_by_file,
    )
    gaps = _gaps(csv_rows_by_file, markdown_sections_by_file, source_ids)
    tests = _tests(csv_rows_by_file, markdown_sections_by_file, evidence_by_anchor, evidence_by_file)
    memory_policy = _memory_policy(markdown_sections_by_file)
    tools = _tool_recommendations(csv_rows_by_file, markdown_sections_by_file)
    readiness = _readiness(sources, facts, rules, evidence, gaps, tests)
    identity = ContextBundleIdentity(
        workspace_name="Compounding Pharmacy Gold",
        summary="Context Compiler bundle generated from the normalized compounding pharmacy source pack.",
        attributes={
            "source_pack_id": manifest.source_pack_id,
            "source_pack_version": manifest.source_pack_version,
            "language": manifest.language,
            "intended_consumer": manifest.intended_consumer,
            "numbered_source_count": len(source_paths),
        },
    )
    bundle_hash = _bundle_hash(
        sources=sources,
        facts=facts,
        rules=rules,
        evidence=evidence,
        identity=identity,
        gaps=gaps,
        tests=tests,
        memory_policy=memory_policy,
        tool_recommendations=tools,
        readiness=readiness,
    )
    bundle = ContextBundleResponse(
        schema_version=SCHEMA_VERSION,
        context_version=f"ctx_{bundle_hash[:12]}",
        workspace_id=WORKSPACE_ID,
        generated_at=GENERATED_AT,
        sources=sources,
        facts=facts,
        rules=rules,
        evidence=evidence,
        identity=identity,
        gaps=gaps,
        tests=tests,
        memory_policy=memory_policy,
        tool_recommendations=tools,
        readiness=readiness,
        integrity=ContextBundleIntegrity(
            bundle_hash=bundle_hash,
            canonicalization=CANONICALIZATION,
            source_count=len(sources),
            fact_count=len(facts),
            rule_count=len(rules),
            evidence_count=len(evidence),
            gap_count=len(gaps),
            test_count=len(tests),
            tool_recommendation_count=len(tools),
        ),
    )
    errors = validate_no_forbidden_payload(bundle.model_dump(mode="json"))
    if errors:
        raise ValueError(f"Source pack contains forbidden payload: {', '.join(errors)}")
    return bundle


def _validate_raw_file(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"source file not found: {path.name}")
    if path.stat().st_size == 0:
        raise ValueError(f"source file is empty: {path.name}")
    errors = validate_no_forbidden_payload(read_text(path))
    if errors:
        raise ValueError(
            f"Source pack file {path.name} contains forbidden payload: {', '.join(errors)}"
        )


def _source_from_path(path: Path, manifest: SourcePackManifest) -> ContextBundleSource:
    role = manifest.document_role_by_file(path.name)
    return ContextBundleSource(
        id=stable_uuid(f"source:{path.name}"),
        title=path.stem[3:].replace("_", " ").title(),
        original_filename=path.name,
        type="markdown" if path.suffix.lower() == ".md" else "csv",
        source_reliability="synthetic_approved",
        authority_level=role.document_type if role else manifest.publication_status,
        status="published",
        created_at=GENERATED_AT,
        updated_at=GENERATED_AT,
    )


def _facts(
    csv_rows_by_file: dict[str, list[CsvRow]],
    manifest: SourcePackManifest,
    source_ids: dict[str, UUID],
    evidence_by_anchor: dict[str, UUID],
    evidence_by_file: dict[str, UUID],
) -> list[ContextBundleFact]:
    facts: list[ContextBundleFact] = []
    for filename, rows in csv_rows_by_file.items():
        if filename in GAP_FILES or filename in TEST_FILES or filename == "53_tool_calling_policy_matrix.csv":
            continue
        role = manifest.document_role_by_file(filename)
        fact_type = _fact_type(filename, role.document_type if role else "csv")
        for row in rows:
            record_id = _row_identifier(row)
            evidence_id = _evidence_id(filename, row, evidence_by_anchor, evidence_by_file)
            facts.append(
                ContextBundleFact(
                    id=stable_uuid(f"fact:{filename}:{row.row_number}:{record_id}"),
                    fact_type=fact_type,
                    schema_version="source_pack.fact.v1",
                    normalized_content={
                        "source_file": filename,
                        "record_id": record_id,
                        "document_type": role.document_type if role else "csv",
                        "data": _sanitized_dict(row.row_data),
                    },
                    confidence=0.9,
                    source_id=source_ids[filename],
                    chunk_id=evidence_id,
                    evidence_span_ids=[evidence_id],
                    published_at=GENERATED_AT,
                )
            )
    return facts


def _rules(
    csv_rows_by_file: dict[str, list[CsvRow]],
    markdown_sections_by_file: dict[str, list[ContextBundleEvidence]],
    source_ids: dict[str, UUID],
    evidence_by_anchor: dict[str, UUID],
    evidence_by_file: dict[str, UUID],
) -> list[ContextBundleRule]:
    rules: list[ContextBundleRule] = []
    priority = 100
    for filename, rule_type in RULE_FILES.items():
        if filename.endswith(".csv"):
            for row in csv_rows_by_file.get(filename, []):
                record_id = _row_identifier(row)
                evidence_id = _evidence_id(filename, row, evidence_by_anchor, evidence_by_file)
                rules.append(
                    ContextBundleRule(
                        id=stable_uuid(f"rule:{filename}:{record_id}"),
                        rule_type=rule_type,
                        schema_version="source_pack.rule.v1",
                        condition=_condition_from_row(row.row_data),
                        action=_action_from_row(row.row_data),
                        priority=priority,
                        confidence=0.9,
                        source_id=source_ids[filename],
                        chunk_id=evidence_id,
                        evidence_span_ids=[evidence_id],
                        published_at=GENERATED_AT,
                    )
                )
                priority += 1
        else:
            for section in markdown_sections_by_file.get(filename, []):
                heading = _heading(section.quote or "")
                if not heading:
                    continue
                rules.append(
                    ContextBundleRule(
                        id=stable_uuid(f"rule:{filename}:{slugify(heading)}"),
                        rule_type=rule_type,
                        schema_version="source_pack.rule.v1",
                        condition={"section": heading, "source_file": filename},
                        action={"policy": sanitize_text((section.quote or "")[:1000])},
                        priority=priority,
                        confidence=0.85,
                        source_id=source_ids[filename],
                        chunk_id=section.id,
                        evidence_span_ids=[section.id],
                        published_at=GENERATED_AT,
                    )
                )
                priority += 1
    return rules


def _gaps(
    csv_rows_by_file: dict[str, list[CsvRow]],
    markdown_sections_by_file: dict[str, list[ContextBundleEvidence]],
    source_ids: dict[str, UUID],
) -> list[ContextBundleGap]:
    gaps: list[ContextBundleGap] = []
    for row in csv_rows_by_file.get("14_known_gaps_and_publish_gates.csv", []):
        gaps.append(
            ContextBundleGap(
                id=row.row_data.get("gap_id") or f"gap-{row.row_number}",
                kind="publish_gap",
                description=sanitize_text(row.row_data.get("summary", "")),
                severity=row.row_data.get("severity") or "medium",
                status=row.row_data.get("status") or "open",
                source_ids=[source_ids["14_known_gaps_and_publish_gates.csv"]],
                created_at=GENERATED_AT,
                details=_sanitized_dict(row.row_data),
            )
        )
    for section in markdown_sections_by_file.get("43_payment_discount_gap_policy.md", []):
        gaps.append(
            ContextBundleGap(
                id=f"gap-{slugify(_heading(section.quote or '') or 'payment-discount-policy')}",
                kind="commercial_gap_policy",
                description=sanitize_text((section.quote or "")[:500]),
                severity="medium",
                status="open",
                source_ids=[source_ids["43_payment_discount_gap_policy.md"]],
                created_at=GENERATED_AT,
                details={"source_file": "43_payment_discount_gap_policy.md"},
            )
        )
    return gaps


def _tests(
    csv_rows_by_file: dict[str, list[CsvRow]],
    markdown_sections_by_file: dict[str, list[ContextBundleEvidence]],
    evidence_by_anchor: dict[str, UUID],
    evidence_by_file: dict[str, UUID],
) -> list[ContextBundleTest]:
    tests: list[ContextBundleTest] = []
    for filename in sorted(TEST_FILES):
        if filename.endswith(".csv"):
            for row in csv_rows_by_file.get(filename, []):
                evidence_id = _evidence_id(filename, row, evidence_by_anchor, evidence_by_file)
                query = _first_value(row.row_data, ("user_query", "query", "scenario", "input"))
                expected = _first_value(
                    row.row_data,
                    ("expected_behavior", "expected_action", "expected_output_class", "required_refusal_phrase"),
                )
                tests.append(
                    ContextBundleTest(
                        id=f"test-{slugify(_row_identifier(row))}",
                        name=_row_identifier(row),
                        status="published",
                        prompt=sanitize_text(query),
                        expected_behavior=sanitize_text(expected),
                        forbidden_answer_contains=_split_values(row.row_data.get("forbidden_behavior", "")),
                        required_evidence_span_ids=[evidence_id],
                        critical=_is_critical(row.row_data),
                        assertion={"source_file": filename, "row_number": row.row_number},
                        details=_sanitized_dict(row.row_data),
                    )
                )
        else:
            for section in markdown_sections_by_file.get(filename, []):
                heading = _heading(section.quote or "")
                if not heading:
                    continue
                tests.append(
                    ContextBundleTest(
                        id=f"test-{slugify(filename)}-{slugify(heading)}",
                        name=heading,
                        status="published",
                        prompt=heading,
                        expected_behavior=sanitize_text((section.quote or "")[:800]),
                        required_evidence_span_ids=[section.id],
                        critical=_critical_text(section.quote or ""),
                        assertion={"source_file": filename, "section": heading},
                        details={"source_file": filename},
                    )
                )
    return tests


def _memory_policy(
    markdown_sections_by_file: dict[str, list[ContextBundleEvidence]],
) -> ContextBundleMemoryPolicy:
    text = "\n".join(
        section.quote or ""
        for filename in (
            "16_memory_and_tool_policy.md",
            "13_prescription_document_handling.md",
            "24_patient_friendly_safe_language.md",
        )
        for section in markdown_sections_by_file.get(filename, [])
    )
    return ContextBundleMemoryPolicy(
        retention="30 days for low-risk operational preferences",
        profile_memory="workspace",
        conversation_memory="ephemeral unless explicitly allowed",
        persist_user_personal_data=False,
        store_unvalidated_claims=False,
        retention_days=30,
        allowed_memory_scopes=["workspace"],
        deletion_policy="Delete on request; never retain sensitive medical or payment data.",
        allowed=[
            "preferred_contact_channel",
            "pickup_or_delivery_preference",
            "general_product_interest",
            "preferred_follow_up_time_window",
            "non_sensitive_communication_preference",
        ],
        denied=[
            "diagnosis",
            "full_prescription_text",
            "prescription_image_content",
            "medical_document_images",
            "controlled_substance_details",
            "payment_card_numbers",
            "identity_documents",
            "provider_secrets",
        ],
        notes=sanitize_text(text[:1200]),
    )


def _tool_recommendations(
    csv_rows_by_file: dict[str, list[CsvRow]],
    markdown_sections_by_file: dict[str, list[ContextBundleEvidence]],
) -> list[ContextBundleToolRecommendation]:
    recommendations: dict[str, ContextBundleToolRecommendation] = {}
    for row in csv_rows_by_file.get("53_tool_calling_policy_matrix.csv", []):
        first_tool = row.row_data.get("required_first_tool", "")
        if not first_tool:
            continue
        recommendations.setdefault(
            first_tool,
            ContextBundleToolRecommendation(
                id=f"tool-{slugify(first_tool)}",
                tool_name=first_tool,
                category="tool_policy",
                risk_level="medium",
                recommended=True,
                allowed_operations=_split_values(row.row_data.get("allowed_followup_tools", "")),
                requires_human_approval=first_tool == "handoff_to_human",
                input_policy=sanitize_text(row.row_data.get("blocking_conditions", "")),
                output_policy=sanitize_text(row.row_data.get("expected_final_action", "")),
                reason=f"Required for {row.row_data.get('user_intent_class', 'source-pack intent')}.",
                confidence=0.9,
                inputs={"source_file": "53_tool_calling_policy_matrix.csv"},
            ),
        )
    for tool_name in ("search_knowledge", "query_graph", "check_inventory", "create_quote", "schedule_event", "handoff_to_human", "create_ticket"):
        recommendations.setdefault(
            tool_name,
            ContextBundleToolRecommendation(
                id=f"tool-{slugify(tool_name)}",
                tool_name=tool_name,
                category="runtime",
                risk_level="medium",
                recommended=True,
                allowed_operations=[],
                requires_human_approval=tool_name == "handoff_to_human",
                input_policy="Follow source-pack memory and tool policy.",
                output_policy="Return grounded action or human handoff.",
                reason=f"{tool_name} is part of the compounding pharmacy tool policy.",
                confidence=0.85,
            ),
        )
    return sorted(recommendations.values(), key=lambda item: item.tool_name or "")


def _readiness(
    sources: list[ContextBundleSource],
    facts: list[ContextBundleFact],
    rules: list[ContextBundleRule],
    evidence: list[ContextBundleEvidence],
    gaps: list[ContextBundleGap],
    tests: list[ContextBundleTest],
) -> ContextBundleReadiness:
    blocking: list[str] = []
    warnings = [
        "Synthetic inventory only",
        "Official full DCB list not materialized",
        "ERP not integrated",
        "Prices are synthetic",
    ]
    if not sources:
        blocking.append("no_published_sources")
    if not facts and not rules:
        blocking.append("no_published_records")
    if any(source.status != "published" for source in sources):
        blocking.append("source_without_published_status")
    evidence_ids = {item.id for item in evidence}
    if any(not set(rule.evidence_span_ids) & evidence_ids for rule in rules):
        blocking.append("rule_without_evidence")
    if any(test.critical and not test.required_evidence_span_ids for test in tests):
        blocking.append("critical_test_without_evidence")
    warnings.extend(gap.description or gap.id or "open gap" for gap in gaps if gap.status in {"open", "accepted"})
    return ContextBundleReadiness(
        status="blocked" if blocking else "warning",
        score=max(0, 100 - len(warnings) * 2 - len(blocking) * 25),
        blocking_reasons=blocking,
        warnings=warnings,
    )


def _bundle_hash(
    *,
    sources: list[ContextBundleSource],
    facts: list[ContextBundleFact],
    rules: list[ContextBundleRule],
    evidence: list[ContextBundleEvidence],
    identity: ContextBundleIdentity,
    gaps: list[ContextBundleGap],
    tests: list[ContextBundleTest],
    memory_policy: ContextBundleMemoryPolicy,
    tool_recommendations: list[ContextBundleToolRecommendation],
    readiness: ContextBundleReadiness,
) -> str:
    return hash_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "workspace_id": str(WORKSPACE_ID),
            "generated_at": "stable-for-hash",
            "sources": [source.model_dump(mode="json") for source in sources],
            "facts": [fact.model_dump(mode="json") for fact in facts],
            "rules": [rule.model_dump(mode="json") for rule in rules],
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "identity": identity.model_dump(mode="json"),
            "gaps": [gap.model_dump(mode="json") for gap in gaps],
            "tests": [test.model_dump(mode="json") for test in tests],
            "memory_policy": memory_policy.model_dump(mode="json"),
            "tool_recommendations": [item.model_dump(mode="json") for item in tool_recommendations],
            "readiness": readiness.model_dump(mode="json"),
        }
    )


def _fact_type(filename: str, document_type: str) -> str:
    if filename == "02_active_ingredients_catalog.csv":
        return "active_ingredient"
    if filename == "04_allergens_excipients_triage.csv":
        return "allergen_excipient"
    if "inventory" in filename:
        return "inventory"
    if "price" in filename:
        return "price"
    if "calendar" in filename:
        return "calendar"
    return document_type.replace("-", "_")


def _row_identifier(row: CsvRow) -> str:
    for key in ("item_id", "rule_id", "gap_id", "test_id", "case_id", "query_id", "policy_id", "trace_id", "scenario_id", "stock_id", "price_id"):
        value = row.row_data.get(key)
        if value:
            return value
    return f"row-{row.row_number}"


def _condition_from_row(data: dict[str, str]) -> dict[str, Any]:
    values = {key: sanitize_text(data[key]) for key in ("trigger", "user_intent_class", "item_or_class", "blocking_conditions") if data.get(key)}
    return values or {"match": _sanitized_dict(data)}


def _action_from_row(data: dict[str, str]) -> dict[str, Any]:
    values = {key: sanitize_text(data[key]) for key in ("next_action", "expected_final_action", "allowed_quote_status", "expected_action") if data.get(key)}
    return values or {"apply": _sanitized_dict(data)}


def _evidence_id(
    filename: str,
    row: CsvRow,
    evidence_by_anchor: dict[str, UUID],
    evidence_by_file: dict[str, UUID],
) -> UUID:
    anchor = row.row_data.get("evidence_anchor") or row.row_data.get("anchor")
    if anchor and anchor in evidence_by_anchor:
        return evidence_by_anchor[anchor]
    return evidence_by_file[filename]


def _anchors_from_quote(quote: str) -> list[str]:
    anchors: list[str] = []
    in_anchor_section = False
    for line in quote.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_anchor_section = "Evidence Anchors" in stripped
            continue
        if in_anchor_section and stripped.startswith("- `") and "`" in stripped[3:]:
            anchors.append(stripped.split("`", 2)[1])
    return anchors


def _heading(quote: str) -> str:
    for line in quote.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def _sanitized_dict(data: dict[str, str]) -> dict[str, str]:
    return {key: sanitize_text(value) for key, value in data.items()}


def _split_values(value: str) -> list[str]:
    values = [value]
    for separator in (";", "|", ","):
        values = [part for item in values for part in item.split(separator)]
    return [sanitize_text(item.strip()) for item in values if item.strip()]


def _first_value(data: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        if data.get(key):
            return data[key]
    return ""


def _is_critical(data: dict[str, str]) -> bool:
    joined = " ".join(data.values()).lower()
    return any(token in joined for token in ("critical", "high", "adverse", "boundary", "controlled", "allergy"))


def _critical_text(text: str) -> bool:
    return any(token in text.lower() for token in ("critical", "must", "blocked", "forbidden", "regression", "failure"))

