from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from context_builder.services.context_bundle_service import build_context_bundle_from_rows

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "examples" / "context_bundle"
GENERATED_AT = "2026-05-24T12:00:00Z"

Variant = Literal["golden", "blocked"]

WORKSPACE_ID = "5f7c6e4d-0000-4000-8000-000000000001"
SOURCE_ID = "5f7c6e4d-0000-4000-8000-000000000010"
FACT_ID = "5f7c6e4d-0000-4000-8000-000000000020"
EVIDENCE_ID = "5f7c6e4d-0000-4000-8000-000000000030"
RULE_ID = "5f7c6e4d-0000-4000-8000-000000000040"
CHUNK_ID = "5f7c6e4d-0000-4000-8000-000000000050"

FIXTURE_FILENAMES: dict[Variant, str] = {
    "golden": "golden-context-bundle.v1.json",
    "blocked": "blocked-context-bundle.v1.json",
}


def build_fixture_payload(variant: Variant) -> dict[str, Any]:
    open_unknown_count = 1 if variant == "blocked" else 0
    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=_sources(),
        facts=_facts(),
        rules=_rules(),
        evidence=_evidence(),
        open_unknown_count=open_unknown_count,
        blocking_contradiction_count=0,
        identity=_identity(),
        gaps=_gaps() if variant == "blocked" else [],
        tests=_tests(variant),
        memory_policy=_memory_policy(),
        tool_recommendations=_tool_recommendations(),
    )
    payload = bundle.model_dump(mode="json")
    payload["generated_at"] = GENERATED_AT
    return payload


def render_fixture_payload(variant: Variant) -> str:
    return json.dumps(build_fixture_payload(variant), indent=2) + "\n"


def selected_variants(value: str) -> list[Variant]:
    if value == "all":
        return ["golden", "blocked"]
    if value not in FIXTURE_FILENAMES:
        raise ValueError(f"Unsupported fixture variant: {value}")
    return [value]


def write_or_check_fixture(
    *,
    variant: Variant,
    output_dir: Path,
    check: bool,
) -> bool:
    output_path = output_dir / FIXTURE_FILENAMES[variant]
    expected = render_fixture_payload(variant)

    if check:
        if not output_path.exists():
            print(
                f"Missing fixture: {_display_path(output_path)}",
                file=sys.stderr,
            )
            return False
        current = _normalize_newlines(output_path.read_text(encoding="utf-8"))
        if current != expected:
            print(
                f"Fixture drift detected: {_display_path(output_path)}",
                file=sys.stderr,
            )
            return False
        print(f"Fixture is current: {_display_path(output_path)}")
        return True

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(expected, encoding="utf-8")
    print(f"Wrote fixture: {_display_path(output_path)}")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or check deterministic context_bundle.v1 fixtures.",
    )
    parser.add_argument(
        "--variant",
        choices=["golden", "blocked", "all"],
        default="all",
        help="Fixture variant to generate or check.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory containing context_bundle.v1 fixture JSON files.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated output differs from committed fixtures.",
    )
    args = parser.parse_args(argv)

    ok = True
    for variant in selected_variants(args.variant):
        ok = write_or_check_fixture(
            variant=variant,
            output_dir=args.output_dir,
            check=args.check,
        ) and ok
    return 0 if ok else 1


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _sources() -> list[dict[str, Any]]:
    return [
        {
            "id": SOURCE_ID,
            "title": "Tabela de precos publicada",
            "original_filename": "clinica-luminaris-precos.md",
            "type": "markdown",
            "source_reliability": "official",
            "authority_level": "published_policy",
            "status": "published",
            "created_at": "2026-05-24T10:00:00Z",
            "updated_at": "2026-05-24T10:30:00Z",
        }
    ]


def _facts() -> list[dict[str, Any]]:
    return [
        {
            "id": FACT_ID,
            "fact_type": "service_price",
            "schema_version": "fact.v1",
            "normalized_content": {
                "service_name": "Limpeza de pele",
                "price": {"amount": 120, "currency": "BRL"},
                "payment_method": "Pix",
                "discount_percent": 5,
            },
            "confidence": 0.96,
            "source_id": SOURCE_ID,
            "chunk_id": CHUNK_ID,
            "evidence_span_ids": [EVIDENCE_ID],
            "status": "published",
            "published_at": "2026-05-24T11:00:00Z",
        }
    ]


def _rules() -> list[dict[str, Any]]:
    return [
        {
            "id": RULE_ID,
            "rule_type": "commercial_policy",
            "schema_version": "rule.v1",
            "condition": {"payment_method": "Pix"},
            "action": {
                "allow_discount_percent": 5,
                "restriction": "Do not promise unpublished discounts.",
            },
            "priority": 90,
            "confidence": 0.94,
            "source_id": SOURCE_ID,
            "chunk_id": CHUNK_ID,
            "evidence_span_ids": [EVIDENCE_ID],
            "status": "published",
            "published_at": "2026-05-24T11:05:00Z",
        }
    ]


def _evidence() -> list[dict[str, Any]]:
    return [
        {
            "id": EVIDENCE_ID,
            "source_id": SOURCE_ID,
            "chunk_id": CHUNK_ID,
            "quote": "Limpeza de pele: R$120. Pagamentos via Pix recebem 5% de desconto.",
            "page_number": None,
            "sheet_name": None,
            "row_number": 12,
        }
    ]


def _identity() -> dict[str, Any]:
    return {
        "workspace_name": "Clinica Luminaris",
        "summary": "Clinica de estetica com servicos faciais e corporais.",
        "attributes": {
            "business_type": "aesthetic_clinic",
            "default_language": "pt-BR",
            "locale": "pt-BR",
            "timezone": "America/Sao_Paulo",
            "brand_voice": {
                "tone": "calm",
                "style": "objective",
                "avoid": ["Do not promise unpublished discounts."],
            },
        },
    }


def _gaps() -> list[dict[str, Any]]:
    return [
        {
            "id": "gap_5f7c6e4d_0001",
            "kind": "missing_policy",
            "description": "Cancellation policy was not present in the published corpus.",
            "severity": "blocking",
            "status": "open",
            "source_ids": [SOURCE_ID],
            "created_at": "2026-05-24T11:20:00Z",
            "details": {"missing_field": "cancellation_policy"},
        }
    ]


def _tests(variant: Variant) -> list[dict[str, Any]]:
    tests = [_price_test()]
    if variant == "blocked":
        tests.append(_gap_test())
    return tests


def _price_test() -> dict[str, Any]:
    return {
        "id": "ctx_test_5f7c6e4d_0001",
        "name": "price_pix_discount",
        "status": "pending",
        "prompt": "Qual e o preco da limpeza de pele se eu pagar via Pix?",
        "expected_behavior": "Answer with the published price and Pix discount, citing evidence.",
        "expected_answer_contains": ["Limpeza de pele", "R$120", "5%", "Pix"],
        "forbidden_answer_contains": [
            "estimated price",
            "no evidence",
            "local path",
            "token",
        ],
        "required_fact_ids": [FACT_ID],
        "required_rule_ids": [RULE_ID],
        "required_evidence_span_ids": [EVIDENCE_ID],
        "must_not_use_unvalidated_data": True,
        "critical": True,
        "assertion": {"answer_state": "valid_answer"},
        "details": {"source_title": "Tabela de precos publicada"},
    }


def _gap_test() -> dict[str, Any]:
    return {
        "id": "ctx_test_5f7c6e4d_0002",
        "name": "cancellation_policy_unknown",
        "status": "blocked",
        "prompt": "Posso cancelar a limpeza de pele no mesmo dia?",
        "expected_behavior": "Do not invent a cancellation policy; surface the knowledge gap.",
        "expected_answer_contains": ["nao tenho essa politica publicada"],
        "forbidden_answer_contains": ["cancelamento gratis", "multa de cancelamento"],
        "required_fact_ids": [],
        "required_rule_ids": [],
        "required_evidence_span_ids": [],
        "must_not_use_unvalidated_data": True,
        "critical": True,
        "assertion": {"answer_state": "gap_required"},
        "details": {"gap_id": "gap_5f7c6e4d_0001"},
    }


def _memory_policy() -> dict[str, Any]:
    return {
        "retention": "none",
        "profile_memory": "disabled",
        "conversation_memory": "session_only",
        "persist_user_personal_data": False,
        "store_unvalidated_claims": False,
        "retention_days": 0,
        "allowed_memory_scopes": ["active_context_version"],
        "deletion_policy": "delete_imported_context_on_workspace_delete",
        "allowed": ["published_facts", "published_rules", "evidence_refs"],
        "denied": ["secrets"],
        "notes": None,
    }


def _tool_recommendations() -> list[dict[str, Any]]:
    return [
        {
            "id": "toolrec_5f7c6e4d_0001",
            "tool_name": "search_knowledge",
            "category": "read_only",
            "risk_level": "low",
            "recommended": True,
            "allowed_operations": [
                "semantic_search",
                "lookup_by_source",
                "lookup_by_evidence",
            ],
            "requires_human_approval": False,
            "input_policy": "no_secrets_no_raw_documents",
            "output_policy": "cite_evidence_ids",
            "reason": "Answer service questions with published evidence.",
            "confidence": 0.92,
            "inputs": {"workspace_scope": "active_context_version"},
        }
    ]


if __name__ == "__main__":
    raise SystemExit(main())
