from __future__ import annotations

import json
from pathlib import Path

import pytest
from context_builder.schemas.context_bundle import ContextBundleResponse
from context_builder.services.query_audit import hash_payload
from source_pack.compiler import compile_source_pack

SOURCE_PACK = Path("C:/tmp/context-builder-sources/compounding-pharmacy-gold")
pytestmark = pytest.mark.skipif(
    not SOURCE_PACK.exists(),
    reason="compounding pharmacy gold source pack is not available",
)


def test_compounding_pharmacy_gold_pack_compiles_to_importable_context_bundle() -> None:
    bundle = compile_source_pack(SOURCE_PACK)
    payload = bundle.model_dump(mode="json")
    serialized = json.dumps(payload, sort_keys=True)

    ContextBundleResponse.model_validate(payload)
    assert len(payload["sources"]) == 64
    assert payload["integrity"]["source_count"] == 64
    assert payload["integrity"]["fact_count"] == len(payload["facts"])
    assert payload["integrity"]["rule_count"] == len(payload["rules"])
    assert payload["integrity"]["evidence_count"] == len(payload["evidence"])
    assert payload["readiness"]["status"] == "warning"
    assert payload["integrity"]["bundle_hash"] == hash_payload(
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

    for marker in ("Bearer ", "raw_prompt", "provider_response", "Traceback", "C:\\Users"):
        assert marker not in serialized
