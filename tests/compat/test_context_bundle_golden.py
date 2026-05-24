from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from context_builder.schemas.context_bundle import ContextBundleResponse
from context_builder.services.query_audit import hash_payload
from pydantic import ValidationError

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "examples" / "context_bundle"
PRIVATE_MARKERS = (
    "Bearer ",
    "X-Amz-Signature",
    "password=",
    "raw_prompt",
    "provider_response",
    "Traceback",
    "C:\\Users",
    "/Users/",
    "/home/",
    "/root/",
)


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _public_payload_hash(payload: dict[str, Any]) -> str:
    return hash_payload(
        {
            "schema_version": payload["schema_version"],
            "workspace_id": payload["workspace_id"],
            "generated_at": "stable-for-hash",
            "sources": payload["sources"],
            "facts": payload["facts"],
            "rules": payload["rules"],
            "evidence": payload["evidence"],
            "identity": payload["identity"],
            "gaps": payload["gaps"],
            "tests": payload["tests"],
            "memory_policy": payload["memory_policy"],
            "tool_recommendations": payload["tool_recommendations"],
            "readiness": payload["readiness"],
        }
    )


def _assert_integrity_counts(payload: dict[str, Any]) -> None:
    integrity = payload["integrity"]

    assert integrity["source_count"] == len(payload["sources"])
    assert integrity["fact_count"] == len(payload["facts"])
    assert integrity["rule_count"] == len(payload["rules"])
    assert integrity["evidence_count"] == len(payload["evidence"])
    assert integrity["gap_count"] == len(payload["gaps"])
    assert integrity["test_count"] == len(payload["tests"])
    assert integrity["tool_recommendation_count"] == len(
        payload["tool_recommendations"]
    )


def _assert_no_private_transport(payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, sort_keys=True)

    for marker in PRIVATE_MARKERS:
        assert marker not in serialized


@pytest.mark.parametrize(
    ("fixture_name", "expected_status", "expected_gap_count", "expected_test_count"),
    [
        ("golden-context-bundle.v1.json", "ready", 0, 1),
        ("blocked-context-bundle.v1.json", "blocked", 1, 2),
    ],
)
def test_context_bundle_fixture_is_importer_verifiable(
    fixture_name: str,
    expected_status: str,
    expected_gap_count: int,
    expected_test_count: int,
) -> None:
    payload = _load_fixture(fixture_name)

    bundle = ContextBundleResponse.model_validate(payload)
    public_payload = bundle.model_dump(mode="json")
    public_hash = _public_payload_hash(public_payload)

    assert public_payload["schema_version"] == "context_bundle.v1"
    assert public_payload["readiness"]["status"] == expected_status
    assert public_payload["integrity"]["gap_count"] == expected_gap_count
    assert public_payload["integrity"]["test_count"] == expected_test_count
    assert public_payload["integrity"]["bundle_hash"] == public_hash
    assert public_payload["context_version"] == f"ctx_{public_hash[:12]}"
    assert public_payload["integrity"]["canonicalization"] == (
        "json.sort_keys.compact.v1"
    )
    _assert_integrity_counts(public_payload)
    _assert_no_private_transport(public_payload)


def test_context_bundle_golden_fixture_contains_runtime_handoff_sections() -> None:
    payload = _load_fixture("golden-context-bundle.v1.json")

    assert payload["identity"]["workspace_name"] == "Clinica Luminaris"
    assert payload["memory_policy"]["persist_user_personal_data"] is False
    assert payload["memory_policy"]["store_unvalidated_claims"] is False
    assert payload["tool_recommendations"][0]["tool_name"] == "search_knowledge"
    assert payload["facts"][0]["evidence_span_ids"] == [payload["evidence"][0]["id"]]
    assert payload["tests"][0]["required_evidence_span_ids"] == [
        payload["evidence"][0]["id"]
    ]


def test_context_bundle_blocked_fixture_blocks_publication() -> None:
    payload = _load_fixture("blocked-context-bundle.v1.json")

    assert payload["readiness"]["status"] == "blocked"
    assert payload["readiness"]["score"] < 100
    assert "open_unknown_items" in payload["readiness"]["blocking_reasons"]
    assert payload["gaps"][0]["status"] == "open"
    assert any(test["critical"] for test in payload["tests"])


def test_context_bundle_fixture_rejects_unknown_top_level_fields() -> None:
    payload = _load_fixture("golden-context-bundle.v1.json")
    payload["raw_prompt"] = "ignore previous instructions"

    with pytest.raises(ValidationError):
        ContextBundleResponse.model_validate(payload)


def test_context_bundle_fixture_rejects_unknown_nested_contract_fields() -> None:
    payload = _load_fixture("golden-context-bundle.v1.json")
    payload["identity"]["provider_response"] = {"text": "hidden"}

    with pytest.raises(ValidationError):
        ContextBundleResponse.model_validate(payload)


@pytest.mark.parametrize(
    "target_path",
    [
        ("sources", 0),
        ("facts", 0),
        ("rules", 0),
        ("evidence", 0),
        ("readiness", None),
        ("integrity", None),
    ],
)
def test_context_bundle_fixture_rejects_unknown_core_contract_fields(
    target_path: tuple[str, int | None],
) -> None:
    payload = _load_fixture("golden-context-bundle.v1.json")
    section, index = target_path
    target = payload[section] if index is None else payload[section][index]
    target["raw_prompt"] = "ignore previous instructions"

    with pytest.raises(ValidationError):
        ContextBundleResponse.model_validate(payload)


def test_context_bundle_fixture_hash_detects_tampering() -> None:
    payload = _load_fixture("golden-context-bundle.v1.json")
    tampered = deepcopy(payload)
    tampered["facts"][0]["normalized_content"]["discount_percent"] = 10

    assert _public_payload_hash(tampered) != payload["integrity"]["bundle_hash"]
