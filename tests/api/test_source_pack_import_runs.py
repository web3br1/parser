from __future__ import annotations

from pathlib import Path
from typing import Any

from context_builder.schemas.source import SourcePackPreflightResponse
from context_builder.schemas.source_pack_import import (
    SourcePackImportRunCreate,
    SourcePackImportRunResponse,
    SourcePackImportRunUpdate,
)
from context_builder.services.source_pack_import_runs import (
    create_import_run_from_preflight,
    source_pack_input_hash,
    update_import_run_compiled,
)
from pydantic import ValidationError


def test_source_pack_import_run_create_accepts_preflight_fields() -> None:
    payload = SourcePackImportRunCreate(
        workspace_id="ws_1",
        actor_user_id="user_1",
        source_pack_id="compounding-pharmacy-gold-source-pack",
        source_pack_version="2026-05-25.v4",
        source_dir="C:/tmp/context-builder-sources/compounding-pharmacy-gold",
        input_hash="sha256:pack-input",
        status="preflighted",
        recommended_action="compile_as_source_pack",
        numbered_source_count=64,
        csv_count=39,
        markdown_count=25,
        manifest_document_count=64,
        official_reference_count=15,
        missing_files=[],
        extra_files=[],
        errors=[],
    )

    assert payload.status == "preflighted"
    assert payload.recommended_action == "compile_as_source_pack"


def test_source_pack_import_run_create_rejects_invalid_status() -> None:
    try:
        SourcePackImportRunCreate(
            workspace_id="ws_1",
            input_hash="sha256:pack-input",
            status="queued",
            recommended_action="compile_as_source_pack",
        )
    except ValidationError as exc:
        assert "status" in str(exc)
    else:
        raise AssertionError("expected ValidationError")


def test_source_pack_import_run_update_accepts_compile_result() -> None:
    payload = SourcePackImportRunUpdate(
        status="compiled",
        bundle_hash="abc123",
        context_version="ctx_abc123",
        output_path="C:/tmp/out/context_bundle.v1.json",
        readiness_status="warning",
        readiness_score=86,
        warnings=["Synthetic inventory only"],
        errors=[],
    )

    assert payload.status == "compiled"
    assert payload.readiness_status == "warning"


def test_source_pack_import_run_response_exposes_audit_fields() -> None:
    response = SourcePackImportRunResponse(
        id="run_1",
        workspace_id="ws_1",
        actor_user_id="user_1",
        source_pack_id="pack",
        source_pack_version="v1",
        source_dir=None,
        input_hash="sha256:pack-input",
        status="rejected",
        recommended_action="reject",
        bundle_hash=None,
        context_version=None,
        output_path=None,
        readiness_status=None,
        readiness_score=None,
        numbered_source_count=1,
        csv_count=0,
        markdown_count=1,
        manifest_document_count=1,
        official_reference_count=0,
        missing_files=["x.md"],
        extra_files=[],
        warnings=[],
        errors=["missing manifest files: x.md"],
        metadata={},
        created_at="2026-05-25T00:00:00+00:00",
        updated_at="2026-05-25T00:00:00+00:00",
    )

    assert response.id == "run_1"
    assert response.missing_files == ["x.md"]


class Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class Query:
    def __init__(self, db: ImportRunDB, table: str) -> None:
        self.db = db
        self.table = table
        self.payload: dict[str, Any] = {}
        self.filters: dict[str, Any] = {}

    def insert(self, payload: dict[str, Any]) -> Query:
        self.payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> Query:
        self.payload = payload
        return self

    def eq(self, field: str, value: Any) -> Query:
        self.filters[field] = value
        return self

    def execute(self) -> Result:
        if self.table != "source_pack_import_runs":
            raise AssertionError(self.table)
        if self.payload and self.filters:
            row = {**self.db.rows[0], **self.payload}
            self.db.rows[0] = row
            return Result([row])
        if self.payload:
            row = {
                "id": "run_1",
                "created_at": "2026-05-25T00:00:00+00:00",
                "updated_at": "2026-05-25T00:00:00+00:00",
                **self.payload,
            }
            self.db.rows.append(row)
            return Result([row])
        return Result([])


class ImportRunDB:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def table(self, name: str) -> Query:
        return Query(self, name)


def _complete_preflight() -> SourcePackPreflightResponse:
    return SourcePackPreflightResponse(
        is_source_pack=True,
        status="complete",
        recommended_action="compile_as_source_pack",
        source_pack_id="compounding-pharmacy-gold-source-pack",
        source_pack_version="2026-05-25.v4",
        language="pt-BR",
        publication_status="source_seed",
        numbered_source_count=64,
        csv_count=39,
        markdown_count=25,
        manifest_document_count=64,
        official_reference_count=15,
        readme_present=True,
        missing_files=[],
        extra_files=[],
        errors=[],
    )


def _pack_dir(tmp_path: Path) -> Path:
    source_dir = tmp_path / "pack"
    source_dir.mkdir()
    (source_dir / "00_source_manifest.md").write_text(
        """---
source_pack_id: test-pack
source_pack_version: v1
---

## Document Roles

| file | document_type | expected_extraction |
|---|---|---|
| 01_policy.md | policy | rules |
""",
        encoding="utf-8",
    )
    (source_dir / "01_policy.md").write_text("hello\n", encoding="utf-8")
    return source_dir


def test_create_import_run_from_complete_preflight(tmp_path: Path) -> None:
    db = ImportRunDB()
    source_dir = _pack_dir(tmp_path)

    run = create_import_run_from_preflight(
        db,
        workspace_id="ws_1",
        actor_user_id="user_1",
        source_dir=str(source_dir),
        preflight=_complete_preflight(),
    )

    assert run.id == "run_1"
    assert run.status == "preflighted"
    assert run.recommended_action == "compile_as_source_pack"
    assert run.input_hash.startswith("sha256:")
    assert db.rows[0]["source_pack_id"] == "compounding-pharmacy-gold-source-pack"
    assert db.rows[0]["manifest_document_count"] == 64


def test_create_import_run_from_rejected_preflight(tmp_path: Path) -> None:
    db = ImportRunDB()
    source_dir = _pack_dir(tmp_path)
    preflight = _complete_preflight().model_copy(
        update={
            "status": "incomplete",
            "recommended_action": "reject",
            "missing_files": ["40_quote_rules_matrix.csv"],
        }
    )

    run = create_import_run_from_preflight(
        db,
        workspace_id="ws_1",
        actor_user_id="user_1",
        source_dir=str(source_dir),
        preflight=preflight,
    )

    assert run.status == "rejected"
    assert run.errors == ["missing_files"]
    assert run.missing_files == ["40_quote_rules_matrix.csv"]


def test_update_import_run_compiled_sets_bundle_fields(tmp_path: Path) -> None:
    db = ImportRunDB()
    source_dir = _pack_dir(tmp_path)
    create_import_run_from_preflight(
        db,
        workspace_id="ws_1",
        actor_user_id="user_1",
        source_dir=str(source_dir),
        preflight=_complete_preflight(),
    )

    run = update_import_run_compiled(
        db,
        workspace_id="ws_1",
        run_id="run_1",
        bundle_hash="abc123",
        context_version="ctx_abc123",
        output_path="C:/tmp/out/context_bundle.v1.json",
        readiness_status="warning",
        readiness_score=86,
        warnings=["Synthetic inventory only"],
    )

    assert run.status == "compiled"
    assert run.bundle_hash == "abc123"
    assert run.output_path == "C:/tmp/out/context_bundle.v1.json"
    assert run.readiness_status == "warning"
    assert db.rows[0]["workspace_id"] == "ws_1"


def test_source_pack_input_hash_is_content_based(tmp_path: Path) -> None:
    source_dir = _pack_dir(tmp_path)

    first_hash = source_pack_input_hash(source_dir)
    second_hash = source_pack_input_hash(source_dir)
    (source_dir / "01_policy.md").write_text("changed\n", encoding="utf-8")
    changed_hash = source_pack_input_hash(source_dir)

    assert first_hash == second_hash
    assert first_hash.startswith("sha256:")
    assert changed_hash != first_hash


def test_source_pack_input_hash_ignores_generated_outputs(tmp_path: Path) -> None:
    source_dir = _pack_dir(tmp_path)

    before_output = source_pack_input_hash(source_dir)
    (source_dir / "test-pack.context_bundle.v1.json").write_text(
        '{"generated": true}\n',
        encoding="utf-8",
    )
    (source_dir / "run.log").write_text("debug\n", encoding="utf-8")
    after_output = source_pack_input_hash(source_dir)

    assert after_output == before_output
