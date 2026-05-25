from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from context_builder.schemas.context_bundle import ContextBundleResponse
from context_builder.services.query_audit import hash_payload
from source_pack.compiler import SourcePackPreflightError, compile_source_pack
from source_pack.writer import write_bundle

SOURCE_PACK = Path("C:/tmp/context-builder-sources/compounding-pharmacy-gold")
pytestmark = pytest.mark.skipif(
    not SOURCE_PACK.exists(),
    reason="compounding pharmacy gold source pack is not available",
)


def _public_payload_hash(payload: dict[str, object]) -> str:
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


def test_compile_source_pack_returns_schema_valid_deterministic_bundle() -> None:
    first = compile_source_pack(SOURCE_PACK)
    second = compile_source_pack(SOURCE_PACK)

    first_payload = first.model_dump(mode="json")
    second_payload = second.model_dump(mode="json")

    assert ContextBundleResponse.model_validate(first_payload)
    assert first_payload["integrity"]["bundle_hash"] == _public_payload_hash(first_payload)
    assert first_payload["context_version"] == (
        f"ctx_{first_payload['integrity']['bundle_hash'][:12]}"
    )
    assert first_payload["integrity"]["bundle_hash"] == (
        second_payload["integrity"]["bundle_hash"]
    )
    assert first_payload["readiness"]["status"] == "warning"
    assert "Synthetic inventory only" in first_payload["readiness"]["warnings"]
    assert len({fact["id"] for fact in first_payload["facts"]}) == len(
        first_payload["facts"]
    )


def test_compile_source_pack_fails_preflight_when_manifest_file_is_missing(
    tmp_path: Path,
) -> None:
    broken_pack = tmp_path / "broken-pack"
    shutil.copytree(SOURCE_PACK, broken_pack)
    (broken_pack / "40_quote_rules_matrix.csv").unlink()

    with pytest.raises(SourcePackPreflightError, match="missing manifest files"):
        compile_source_pack(broken_pack)


def test_compile_source_pack_blocks_raw_forbidden_payload(tmp_path: Path) -> None:
    broken_pack = tmp_path / "raw-prompt-pack"
    shutil.copytree(SOURCE_PACK, broken_pack)
    target = broken_pack / "05_sales_triage_rules.md"
    target.write_text(
        target.read_text(encoding="utf-8") + "\nSYSTEM PROMPT: leak\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="forbidden payload"):
        compile_source_pack(broken_pack)


def test_write_bundle_check_detects_stale_output(tmp_path: Path) -> None:
    bundle = compile_source_pack(SOURCE_PACK)
    output = tmp_path / "bundle.json"

    result = write_bundle(bundle, output)
    assert result.changed is True
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == (
        "context_bundle.v1"
    )

    check_result = write_bundle(bundle, output, check=True)
    assert check_result.changed is False

    output.write_text("{}", encoding="utf-8")
    stale_result = write_bundle(bundle, output, check=True)
    assert stale_result.changed is True
