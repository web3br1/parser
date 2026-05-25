from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "context_bundle" / "export_contract_manifest.py"
ARTIFACT_DIR = ROOT / "examples" / "context_bundle"
MANIFEST_PATH = ARTIFACT_DIR / "context-bundle-contract.v1.manifest.json"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "export_contract_manifest_under_test",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_manifest_export_matches_committed_artifact() -> None:
    module = _load_script()

    assert module.build_manifest() == _read_manifest()


def test_manifest_check_accepts_committed_artifact() -> None:
    module = _load_script()

    assert module.main(["--check"]) == 0


def test_manifest_check_detects_drift(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    output_path = tmp_path / "context-bundle-contract.v1.manifest.json"
    assert module.main(["--output-path", str(output_path)]) == 0

    manifest = _read_manifest(output_path)
    manifest["fixtures"][0]["readiness_score"] = 99
    output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    assert module.main(["--output-path", str(output_path), "--check"]) == 1
    captured = capsys.readouterr()

    assert "Manifest drift detected: context-bundle-contract.v1.manifest.json" in captured.err
    assert "afc81385492b" not in captured.err


def test_manifest_check_accepts_crlf_artifact(tmp_path: Path) -> None:
    module = _load_script()
    output_path = tmp_path / "context-bundle-contract.v1.manifest.json"
    assert module.main(["--output-path", str(output_path)]) == 0

    output_path.write_bytes(
        output_path.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
    )

    assert module.main(["--output-path", str(output_path), "--check"]) == 0


def test_manifest_has_contract_package_metadata() -> None:
    manifest = _read_manifest()

    assert manifest["manifest_version"] == "context_bundle_contract_manifest.v1"
    assert manifest["schema_version"] == "context_bundle.v1"
    assert manifest["generated_at"] == "2026-05-25T12:00:00Z"
    assert manifest["artifact_hash_algorithm"] == "sha256.normalized_lf.v1"
    assert manifest["bundle_hash_canonicalization"] == "json.sort_keys.compact.v1"
    assert manifest["schema"]["path"] == "context-bundle.v1.schema.json"
    assert manifest["schema"]["title"] == "context_bundle.v1"
    assert manifest["required_top_level_fields"] == _read_json(
        ARTIFACT_DIR / "context-bundle.v1.schema.json"
    )["required"]
    assert manifest["activation_policy"] == {
        "ready": "may_import_after_runtime_checks",
        "warning": "may_import_with_operator_warning",
        "blocked": "must_not_activate",
    }


def test_manifest_hashes_match_artifacts() -> None:
    module = _load_script()
    manifest = _read_manifest()

    assert manifest["schema"]["sha256"] == module.sha256_normalized_file(
        ARTIFACT_DIR / manifest["schema"]["path"]
    )
    for fixture in manifest["fixtures"]:
        assert fixture["sha256"] == module.sha256_normalized_file(
            ARTIFACT_DIR / fixture["path"]
        )


def test_manifest_fixture_metadata_matches_fixture_integrity() -> None:
    manifest = _read_manifest()

    fixtures = {fixture["name"]: fixture for fixture in manifest["fixtures"]}
    assert set(fixtures) == {"golden", "blocked"}
    assert fixtures["golden"]["readiness_status"] == "ready"
    assert fixtures["blocked"]["readiness_status"] == "blocked"
    assert fixtures["blocked"]["blocking_reasons"] == ["open_unknown_items"]

    for fixture in manifest["fixtures"]:
        payload = _read_json(ARTIFACT_DIR / fixture["path"])
        integrity = payload["integrity"]
        assert fixture["context_version"] == payload["context_version"]
        assert fixture["bundle_hash"] == integrity["bundle_hash"]
        assert fixture["bundle_hash_canonicalization"] == integrity["canonicalization"]
        assert fixture["bundle_hash_canonicalization"] == manifest[
            "bundle_hash_canonicalization"
        ]
        assert fixture["counts"] == {
            "sources": integrity["source_count"],
            "facts": integrity["fact_count"],
            "rules": integrity["rule_count"],
            "evidence": integrity["evidence_count"],
            "gaps": integrity["gap_count"],
            "tests": integrity["test_count"],
            "tool_recommendations": integrity["tool_recommendation_count"],
        }


def test_manifest_lists_required_verification_commands() -> None:
    manifest = _read_manifest()
    checks = {check["name"]: check["command"] for check in manifest["checks"]}

    assert set(checks) == {"schema_drift", "fixture_drift", "manifest_drift", "secret_scan"}
    assert "export_json_schema.py --check" in checks["schema_drift"]
    assert "export_golden_bundle.py --check" in checks["fixture_drift"]
    assert "export_contract_manifest.py --check" in checks["manifest_drift"]
    assert "secret_scan.py" in checks["secret_scan"]
    for command in checks.values():
        assert "\\" not in command
