from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

from source_pack.manifest import parse_manifest

from context_builder.schemas.source import SourcePackPreflightResponse
from context_builder.schemas.source_pack_import import SourcePackImportRunResponse


def create_import_run_from_preflight(
    db: Any,
    *,
    workspace_id: str,
    actor_user_id: str | None,
    source_dir: str,
    preflight: SourcePackPreflightResponse,
) -> SourcePackImportRunResponse:
    status = "rejected" if preflight.recommended_action == "reject" else "preflighted"
    errors = _preflight_errors(preflight)
    payload = {
        "workspace_id": workspace_id,
        "actor_user_id": actor_user_id,
        "source_pack_id": preflight.source_pack_id,
        "source_pack_version": preflight.source_pack_version,
        "source_dir": source_dir,
        "input_hash": source_pack_input_hash(Path(source_dir)),
        "status": status,
        "recommended_action": preflight.recommended_action,
        "bundle_hash": None,
        "context_version": None,
        "output_path": None,
        "readiness_status": None,
        "readiness_score": None,
        "numbered_source_count": preflight.numbered_source_count,
        "csv_count": preflight.csv_count,
        "markdown_count": preflight.markdown_count,
        "manifest_document_count": preflight.manifest_document_count,
        "official_reference_count": preflight.official_reference_count,
        "missing_files": preflight.missing_files,
        "extra_files": preflight.extra_files,
        "warnings": [],
        "errors": errors,
        "metadata": {
            "is_source_pack": preflight.is_source_pack,
            "preflight_status": preflight.status,
            "language": preflight.language,
            "publication_status": preflight.publication_status,
            "readme_present": preflight.readme_present,
        },
    }
    result = db.table("source_pack_import_runs").insert(payload).execute()
    return _response_from_result(result)


def update_import_run_compiled(
    db: Any,
    *,
    workspace_id: str,
    run_id: str,
    bundle_hash: str,
    context_version: str,
    output_path: str,
    readiness_status: str,
    readiness_score: int,
    warnings: list[str],
) -> SourcePackImportRunResponse:
    payload = {
        "status": "compiled",
        "bundle_hash": bundle_hash,
        "context_version": context_version,
        "output_path": output_path,
        "readiness_status": readiness_status,
        "readiness_score": readiness_score,
        "warnings": warnings,
        "errors": [],
    }
    result = (
        db.table("source_pack_import_runs")
        .update(payload)
        .eq("id", run_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )
    return _response_from_result(result)


def source_pack_input_hash(source_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in _input_files(source_dir):
        relative_path = path.relative_to(source_dir).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _input_files(source_dir: Path) -> list[Path]:
    manifest_path = source_dir / "00_source_manifest.md"
    if manifest_path.exists():
        manifest = parse_manifest(manifest_path)
        paths = [manifest_path]
        readme_path = source_dir / "README.md"
        if readme_path.exists():
            paths.append(readme_path)
        paths.extend(
            source_dir / role.file
            for role in manifest.document_roles
            if (source_dir / role.file).is_file()
        )
        return sorted(paths, key=lambda path: path.relative_to(source_dir).as_posix())
    return sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file() and not _is_generated_artifact(path)
    )


def _is_generated_artifact(path: Path) -> bool:
    return path.name.endswith(".context_bundle.v1.json") or path.suffix == ".log"


def _preflight_errors(preflight: SourcePackPreflightResponse) -> list[str]:
    errors: list[str] = []
    if preflight.missing_files:
        errors.append("missing_files")
    if preflight.extra_files:
        errors.append("extra_files")
    errors.extend(preflight.errors)
    return errors


def _response_from_result(result: Any) -> SourcePackImportRunResponse:
    data = getattr(result, "data", None)
    if isinstance(data, list) and data:
        row = data[0]
    elif isinstance(data, dict):
        row = data
    else:
        raise RuntimeError("source_pack_import_run_write_failed")
    return SourcePackImportRunResponse(**cast(dict[str, Any], row))
