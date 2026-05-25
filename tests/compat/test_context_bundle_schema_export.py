from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "context_bundle" / "export_json_schema.py"
SCHEMA_PATH = ROOT / "examples" / "context_bundle" / "context-bundle.v1.schema.json"
FIXTURE_DIR = ROOT / "examples" / "context_bundle"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "export_json_schema_under_test",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_schema() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8")),
    )


def _read_fixture(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8")),
    )


def test_json_schema_export_matches_committed_artifact() -> None:
    module = _load_script()

    assert module.build_schema() == _read_schema()


def test_json_schema_check_accepts_committed_artifact() -> None:
    module = _load_script()

    assert module.main(["--check"]) == 0


def test_json_schema_check_detects_drift(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    output_path = tmp_path / "context-bundle.v1.schema.json"
    assert module.main(["--output-path", str(output_path)]) == 0

    schema = json.loads(output_path.read_text(encoding="utf-8"))
    schema["title"] = "context_bundle.v1.drifted"
    output_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

    assert module.main(["--output-path", str(output_path), "--check"]) == 1
    captured = capsys.readouterr()

    assert "Schema drift detected: context-bundle.v1.schema.json" in captured.err
    assert "ContextBundleFact" not in captured.err


def test_json_schema_check_accepts_crlf_artifact(tmp_path: Path) -> None:
    module = _load_script()
    output_path = tmp_path / "context-bundle.v1.schema.json"
    assert module.main(["--output-path", str(output_path)]) == 0

    output_path.write_bytes(
        output_path.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
    )

    assert module.main(["--output-path", str(output_path), "--check"]) == 0


def test_json_schema_has_versioned_contract_metadata() -> None:
    schema = _read_schema()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == "https://context-builder.local/schemas/context-bundle.v1.schema.json"
    assert schema["title"] == "context_bundle.v1"
    assert schema["properties"]["schema_version"]["const"] == "context_bundle.v1"


def test_json_schema_requires_exported_top_level_sections() -> None:
    schema = _read_schema()

    expected_required = {
        "schema_version",
        "context_version",
        "workspace_id",
        "generated_at",
        "sources",
        "facts",
        "rules",
        "evidence",
        "identity",
        "gaps",
        "tests",
        "memory_policy",
        "tool_recommendations",
        "readiness",
        "integrity",
    }

    assert schema["required"] == list(schema["properties"])
    assert set(schema["required"]) == expected_required


@pytest.mark.parametrize(
    "fixture_name",
    [
        "golden-context-bundle.v1.json",
        "blocked-context-bundle.v1.json",
    ],
)
def test_json_schema_required_sections_exist_in_fixtures(fixture_name: str) -> None:
    schema = _read_schema()
    fixture = _read_fixture(fixture_name)

    for field_name in schema["required"]:
        assert field_name in fixture


def test_json_schema_preserves_strict_contract_objects() -> None:
    schema = _read_schema()
    defs = schema["$defs"]
    strict_definitions = [
        "ContextBundleEvidence",
        "ContextBundleFact",
        "ContextBundleGap",
        "ContextBundleIdentity",
        "ContextBundleIntegrity",
        "ContextBundleMemoryPolicy",
        "ContextBundleReadiness",
        "ContextBundleRule",
        "ContextBundleSource",
        "ContextBundleTest",
        "ContextBundleToolRecommendation",
    ]

    assert schema["additionalProperties"] is False
    for definition in strict_definitions:
        assert defs[definition]["additionalProperties"] is False

    assert defs["ContextBundleFact"]["properties"]["normalized_content"][
        "additionalProperties"
    ] is True
    assert defs["ContextBundleIdentity"]["properties"]["attributes"][
        "additionalProperties"
    ] is True


def test_json_schema_preserves_allowed_flexible_maps() -> None:
    schema = _read_schema()
    defs = schema["$defs"]

    flexible_maps = [
        ("ContextBundleFact", "normalized_content"),
        ("ContextBundleRule", "condition"),
        ("ContextBundleRule", "action"),
        ("ContextBundleIdentity", "attributes"),
        ("ContextBundleGap", "details"),
        ("ContextBundleTest", "assertion"),
        ("ContextBundleTest", "details"),
        ("ContextBundleToolRecommendation", "inputs"),
    ]

    for definition, field_name in flexible_maps:
        assert defs[definition]["properties"][field_name]["additionalProperties"] is True


def test_json_schema_keeps_readiness_and_integrity_requirements() -> None:
    schema = _read_schema()
    defs = schema["$defs"]

    assert defs["ContextBundleReadiness"]["properties"]["status"]["enum"] == [
        "ready",
        "warning",
        "blocked",
    ]
    assert "bundle_hash" in defs["ContextBundleIntegrity"]["required"]
    assert defs["ContextBundleIntegrity"]["properties"]["canonicalization"]["default"] == (
        "json.sort_keys.compact.v1"
    )
