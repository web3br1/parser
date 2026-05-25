from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from contract_artifacts import (  # noqa: E402
    ROOT,
    display_path,
    read_text_normalized,
    sha256_normalized_file,
)

DEFAULT_ARTIFACT_DIR = ROOT / "examples" / "context_bundle"
DEFAULT_MANIFEST_PATH = DEFAULT_ARTIFACT_DIR / "context-bundle-contract.v1.manifest.json"
GENERATED_AT = "2026-05-25T12:00:00Z"
MANIFEST_VERSION = "context_bundle_contract_manifest.v1"
SCHEMA_VERSION = "context_bundle.v1"
ARTIFACT_HASH_ALGORITHM = "sha256.normalized_lf.v1"
SCHEMA_FILENAME = "context-bundle.v1.schema.json"
FIXTURE_FILENAMES = {
    "golden": "golden-context-bundle.v1.json",
    "blocked": "blocked-context-bundle.v1.json",
}


def build_manifest(*, artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> dict[str, Any]:
    schema = _read_json(artifact_dir / SCHEMA_FILENAME)
    fixtures = [
        _fixture_entry(name=name, path=artifact_dir / filename)
        for name, filename in FIXTURE_FILENAMES.items()
    ]
    fixture_canonicalizations = sorted(
        {fixture["bundle_hash_canonicalization"] for fixture in fixtures}
    )
    if len(fixture_canonicalizations) != 1:
        raise ValueError("Fixture bundle hash canonicalization mismatch")

    return {
        "manifest_version": MANIFEST_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "artifact_hash_algorithm": ARTIFACT_HASH_ALGORITHM,
        "bundle_hash_canonicalization": fixture_canonicalizations[0],
        "schema": {
            "path": SCHEMA_FILENAME,
            "sha256": sha256_normalized_file(artifact_dir / SCHEMA_FILENAME),
            "schema_id": schema["$id"],
            "title": schema["title"],
            "json_schema_draft": schema["$schema"],
        },
        "fixtures": fixtures,
        "required_top_level_fields": schema["required"],
        "activation_policy": {
            "ready": "may_import_after_runtime_checks",
            "warning": "may_import_with_operator_warning",
            "blocked": "must_not_activate",
        },
        "checks": [
            {
                "name": "schema_drift",
                "command": (
                    "uv run --cache-dir .uv-cache python "
                    "scripts/context_bundle/export_json_schema.py --check"
                ),
            },
            {
                "name": "fixture_drift",
                "command": (
                    "uv run --cache-dir .uv-cache python "
                    "scripts/context_bundle/export_golden_bundle.py --check"
                ),
            },
            {
                "name": "manifest_drift",
                "command": (
                    "uv run --cache-dir .uv-cache python "
                    "scripts/context_bundle/export_contract_manifest.py --check"
                ),
            },
            {
                "name": "secret_scan",
                "command": "uv run --cache-dir .uv-cache python scripts/ci/secret_scan.py",
            },
        ],
    }


def render_manifest(*, artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> str:
    return json.dumps(build_manifest(artifact_dir=artifact_dir), indent=2) + "\n"


def write_or_check_manifest(
    *,
    artifact_dir: Path,
    output_path: Path,
    check: bool,
) -> bool:
    expected = render_manifest(artifact_dir=artifact_dir)

    if check:
        if not output_path.exists():
            print(f"Missing manifest: {display_path(output_path)}", file=sys.stderr)
            return False
        current = read_text_normalized(output_path)
        if current != expected:
            print(f"Manifest drift detected: {display_path(output_path)}", file=sys.stderr)
            return False
        print(f"Manifest is current: {display_path(output_path)}")
        return True

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(expected, encoding="utf-8")
    print(f"Wrote manifest: {display_path(output_path)}")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or check the context_bundle.v1 contract manifest.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_DIR,
        help="Directory containing schema and fixture artifacts.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Destination manifest path.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated manifest differs from the committed artifact.",
    )
    args = parser.parse_args(argv)

    return 0 if write_or_check_manifest(
        artifact_dir=args.artifact_dir,
        output_path=args.output_path,
        check=args.check,
    ) else 1


def _fixture_entry(*, name: str, path: Path) -> dict[str, Any]:
    fixture = _read_json(path)
    integrity = fixture["integrity"]
    readiness = fixture["readiness"]
    return {
        "name": name,
        "path": path.name,
        "sha256": sha256_normalized_file(path),
        "context_version": fixture["context_version"],
        "bundle_hash": integrity["bundle_hash"],
        "bundle_hash_canonicalization": integrity["canonicalization"],
        "readiness_status": readiness["status"],
        "readiness_score": readiness["score"],
        "blocking_reasons": readiness["blocking_reasons"],
        "counts": {
            "sources": integrity["source_count"],
            "facts": integrity["fact_count"],
            "rules": integrity["rule_count"],
            "evidence": integrity["evidence_count"],
            "gaps": integrity["gap_count"],
            "tests": integrity["test_count"],
            "tool_recommendations": integrity["tool_recommendation_count"],
        },
    }


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(read_text_normalized(path)))


if __name__ == "__main__":
    raise SystemExit(main())
