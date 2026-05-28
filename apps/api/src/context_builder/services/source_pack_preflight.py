from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from source_pack.manifest import preflight_source_pack

from context_builder.schemas.source import SourcePackPreflightResponse


def inspect_source_pack_upload(source_dir: Path) -> SourcePackPreflightResponse:
    if not source_dir.exists() or not source_dir.is_dir():
        return SourcePackPreflightResponse(
            is_source_pack=False,
            status="invalid",
            recommended_action="reject",
            missing_files=[],
            extra_files=[],
            errors=["source_dir_not_found"],
        )

    manifest_path = source_dir / "00_source_manifest.md"
    if not manifest_path.exists():
        return SourcePackPreflightResponse(
            is_source_pack=False,
            status="not_source_pack",
            recommended_action="normal_ingest",
            numbered_source_count=_count_numbered_sources(source_dir),
            csv_count=_count_suffix(source_dir, ".csv"),
            markdown_count=_count_suffix(source_dir, ".md"),
            readme_present=(source_dir / "README.md").exists(),
            missing_files=[],
            extra_files=[],
            errors=[],
        )

    try:
        preflight = preflight_source_pack(source_dir)
    except Exception as exc:
        return SourcePackPreflightResponse(
            is_source_pack=True,
            status="invalid",
            recommended_action="reject",
            missing_files=[],
            extra_files=[],
            errors=[f"manifest_parse_failed:{type(exc).__name__}"],
        )

    manifest = preflight.manifest
    status: Literal["complete", "incomplete"] = (
        "complete" if preflight.ok and not preflight.extra_unlisted_files else "incomplete"
    )
    return SourcePackPreflightResponse(
        is_source_pack=True,
        status=status,
        recommended_action="compile_as_source_pack" if status == "complete" else "reject",
        source_pack_id=manifest.source_pack_id,
        source_pack_version=manifest.source_pack_version,
        language=manifest.language,
        publication_status=manifest.publication_status,
        numbered_source_count=preflight.numbered_source_count,
        csv_count=_count_suffix(source_dir, ".csv"),
        markdown_count=_count_numbered_suffix(source_dir, ".md"),
        manifest_document_count=len(manifest.document_roles),
        official_reference_count=len(manifest.official_references),
        readme_present=preflight.readme_present,
        missing_files=preflight.missing_listed_files,
        extra_files=preflight.extra_unlisted_files,
        errors=[],
    )


def _count_suffix(source_dir: Path, suffix: str) -> int:
    return sum(1 for path in source_dir.iterdir() if path.is_file() and path.suffix == suffix)


def _count_numbered_suffix(source_dir: Path, suffix: str) -> int:
    return sum(
        1
        for path in source_dir.iterdir()
        if path.is_file()
        and path.suffix == suffix
        and re.match(r"^\d{2}_", path.name)
        and not path.name.startswith("00_")
    )


def _count_numbered_sources(source_dir: Path) -> int:
    return sum(
        1
        for path in source_dir.iterdir()
        if path.is_file()
        and re.match(r"^\d{2}_.+\.(?:csv|md)$", path.name)
        and not path.name.startswith("00_")
    )
