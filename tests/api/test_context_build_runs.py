from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from context_builder.config import get_settings
from context_builder.dependencies import (
    get_current_user,
    get_supabase_anon,
    get_supabase_service_for_backend_only,
    require_upload_permission,
    require_workspace_member,
)
from context_builder.main import create_app
from fastapi.testclient import TestClient


def _client(monkeypatch: pytest.MonkeyPatch, db: object | None = None) -> TestClient:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("TRUSTED_HOSTS", '["testserver"]')
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides.clear()
    app.dependency_overrides[get_current_user] = lambda: {"id": "user_1"}
    app.dependency_overrides[get_supabase_anon] = lambda: None
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: db
    app.dependency_overrides[require_workspace_member] = lambda: {
        "workspace_id": "ws_1",
        "role": "manager",
        "user": {"id": "user_1"},
    }
    app.dependency_overrides[require_upload_permission] = lambda: {
        "workspace_id": "ws_1",
        "role": "manager",
        "user": {"id": "user_1"},
    }
    return TestClient(app)


class Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class Query:
    def __init__(self, db: ContextBuildRunDB, table: str) -> None:
        self.db = db
        self.table = table
        self.insert_payload: dict[str, Any] | None = None
        self.update_payload: dict[str, Any] | None = None
        self.filters: dict[str, Any] = {}
        self.single = False

    def insert(self, payload: dict[str, Any]) -> Query:
        self.insert_payload = payload
        return self

    def select(self, _columns: str) -> Query:
        return self

    def update(self, payload: dict[str, Any]) -> Query:
        self.update_payload = payload
        return self

    def eq(self, field: str, value: Any) -> Query:
        self.filters[field] = value
        return self

    def order(self, _field: str, *, desc: bool = False) -> Query:
        return self

    def maybe_single(self) -> Query:
        self.single = True
        return self

    def execute(self) -> Result:
        if self.table != "context_build_runs":
            raise AssertionError(self.table)
        if self.insert_payload is not None:
            row = {
                "id": f"run_{len(self.db.rows) + 1}",
                "created_at": "2026-05-26T00:00:00+00:00",
                "updated_at": "2026-05-26T00:00:00+00:00",
                **self.insert_payload,
            }
            self.db.rows.append(row)
            return Result([row])
        if self.update_payload is not None:
            row = self.db.match(self.filters)
            if row is None:
                return Result([])
            row.update(self.update_payload)
            row["updated_at"] = "2026-05-26T00:01:00+00:00"
            return Result([row])
        matches = [row for row in self.db.rows if self.db.matches(row, self.filters)]
        if self.single:
            return Result(matches[0] if matches else None)
        return Result(matches)


class ContextBuildRunDB:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def table(self, name: str) -> Query:
        return Query(self, name)

    def matches(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        return all(row.get(field) == value for field, value in filters.items())

    def match(self, filters: dict[str, Any]) -> dict[str, Any] | None:
        return next((row for row in self.rows if self.matches(row, filters)), None)


def _source_pack_dir(tmp_path: Path) -> Path:
    source_dir = tmp_path / "pack"
    source_dir.mkdir()
    (source_dir / "00_source_manifest.md").write_text(
        """---
source_pack_id: test-pack
source_pack_version: v1
language: pt-BR
publication_status: source_seed
---

## Document Roles

| file | document_type | expected_extraction |
|---|---|---|
| 01_policy.md | policy | rules |
""",
        encoding="utf-8",
    )
    (source_dir / "01_policy.md").write_text("# Policy\nhello\n", encoding="utf-8")
    return source_dir


def test_preflight_single_file_detects_single_document(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)

    response = client.post(
        "/workspaces/ws_1/context-build-runs/preflight",
        json={"files": [{"name": "policy.md", "size": 120}], "persist": False},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["input_mode"] == "single_document"
    assert body["recommended_action"] == "normal_ingest"
    assert body["status"] == "preflighted"
    assert body["run_id"] is None


def test_preflight_batch_detects_multi_document_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)

    response = client.post(
        "/workspaces/ws_1/context-build-runs/preflight",
        json={
            "files": [
                {"name": "policy.md", "size": 120},
                {"name": "catalog.csv", "size": 80},
            ],
            "persist": False,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["input_mode"] == "multi_document_batch"
    assert body["recommended_action"] == "batch_ingest"
    assert body["counts"]["file_count"] == 2
    assert body["counts"]["csv_count"] == 1
    assert body["counts"]["markdown_count"] == 1


def test_preflight_manifest_metadata_detects_source_pack_but_blocks_compile_until_staged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = ContextBuildRunDB()
    client = _client(monkeypatch, db=db)

    response = client.post(
        "/workspaces/ws_1/context-build-runs/preflight",
        json={
            "files": [
                {
                    "name": "00_source_manifest.md",
                    "size": 120,
                    "relative_path": "pack/00_source_manifest.md",
                },
                {
                    "name": "01_policy.md",
                    "size": 80,
                    "relative_path": "pack/01_policy.md",
                },
            ],
            "input_fingerprint": "browser:pack",
            "persist": True,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"] == "run_1"
    assert body["input_mode"] == "source_pack"
    assert body["recommended_action"] == "compile_as_source_pack"
    assert body["input_fingerprint"] == "browser:pack"
    assert body["blocking_reasons"] == ["source_pack_staging_required"]
    assert db.rows[0]["input_fingerprint"] == "browser:pack"


def test_preflight_source_pack_can_persist_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CONTEXT_BUILD_ALLOWED_SOURCE_ROOTS", str(tmp_path))
    db = ContextBuildRunDB()
    client = _client(monkeypatch, db=db)
    source_dir = _source_pack_dir(tmp_path)

    response = client.post(
        "/workspaces/ws_1/context-build-runs/preflight",
        json={"source_dir": str(source_dir), "persist": True},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"] == "run_1"
    assert body["input_mode"] == "source_pack"
    assert body["recommended_action"] == "compile_as_source_pack"
    assert db.rows[0]["status"] == "preflighted"
    assert db.rows[0]["source_dir"] == str(source_dir)
    assert db.rows[0]["input_fingerprint"].startswith("source_dir:")
    assert db.rows[0]["input_hash"].startswith("sha256:")


def test_create_list_and_get_context_build_run(monkeypatch: pytest.MonkeyPatch) -> None:
    db = ContextBuildRunDB()
    client = _client(monkeypatch, db=db)

    created = client.post(
        "/workspaces/ws_1/context-build-runs",
        json={
            "input_mode": "single_document",
            "input_fingerprint": "files:policy.md:120",
            "input_hash": None,
            "recommended_action": "normal_ingest",
            "metadata": {"filename": "policy.md"},
        },
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]

    listed = client.get("/workspaces/ws_1/context-build-runs")
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [run_id]

    fetched = client.get(f"/workspaces/ws_1/context-build-runs/{run_id}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["input_mode"] == "single_document"
    assert fetched.json()["metadata"] == {"filename": "policy.md"}


def test_compile_source_pack_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CONTEXT_BUILD_ALLOWED_SOURCE_ROOTS", str(tmp_path))
    db = ContextBuildRunDB()
    client = _client(monkeypatch, db=db)
    source_dir = _source_pack_dir(tmp_path)
    preflight = client.post(
        "/workspaces/ws_1/context-build-runs/preflight",
        json={"source_dir": str(source_dir), "persist": True},
    )
    run_id = preflight.json()["run_id"]

    response = client.post(
        f"/workspaces/ws_1/context-build-runs/{run_id}/actions/compile",
        json={"confirmed": False},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "confirmation_required"


@dataclass(frozen=True)
class _FakeIntegrity:
    bundle_hash: str


@dataclass(frozen=True)
class _FakeReadiness:
    status: str
    score: int
    warnings: list[str]


@dataclass(frozen=True)
class _FakeBundle:
    context_version: str
    integrity: _FakeIntegrity
    readiness: _FakeReadiness


@dataclass(frozen=True)
class _FakeWriteResult:
    path: Path
    changed: bool
    checked: bool


def test_compile_source_pack_updates_run_with_bundle_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CONTEXT_BUILD_ALLOWED_SOURCE_ROOTS", str(tmp_path))
    db = ContextBuildRunDB()
    client = _client(monkeypatch, db=db)
    source_dir = _source_pack_dir(tmp_path)
    preflight = client.post(
        "/workspaces/ws_1/context-build-runs/preflight",
        json={"source_dir": str(source_dir), "persist": True},
    )
    run_id = preflight.json()["run_id"]
    calls: dict[str, Any] = {}

    def fake_compile(path: Path) -> _FakeBundle:
        calls["compiled_path"] = path
        return _FakeBundle(
            context_version="ctx_test",
            integrity=_FakeIntegrity(bundle_hash="sha256:bundle"),
            readiness=_FakeReadiness(status="warning", score=86, warnings=["synthetic"]),
        )

    def fake_write(bundle: _FakeBundle, output_path: Path) -> _FakeWriteResult:
        calls["written_bundle"] = bundle
        calls["output_path"] = output_path
        return _FakeWriteResult(path=output_path, changed=True, checked=False)

    monkeypatch.setattr(
        "context_builder.services.context_build_use_cases.compile_source_pack",
        fake_compile,
    )
    monkeypatch.setattr(
        "context_builder.services.context_build_use_cases.write_bundle",
        fake_write,
    )

    response = client.post(
        f"/workspaces/ws_1/context-build-runs/{run_id}/actions/compile",
        json={"confirmed": True},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert calls["compiled_path"] == source_dir
    assert calls["output_path"] == source_dir / "pack.context_bundle.v1.json"
    assert body["status"] == "compiled"
    assert body["bundle_hash"] == "sha256:bundle"
    assert body["context_version"] == "ctx_test"
    assert body["readiness_status"] == "warning"
    assert body["readiness_score"] == 86


def test_preflight_rejects_source_dir_outside_allowed_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    source_dir = _source_pack_dir(blocked)
    monkeypatch.setenv("CONTEXT_BUILD_ALLOWED_SOURCE_ROOTS", str(allowed))
    client = _client(monkeypatch, db=ContextBuildRunDB())

    response = client.post(
        "/workspaces/ws_1/context-build-runs/preflight",
        json={"source_dir": str(source_dir), "persist": True},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "source_dir_not_allowed"


def test_compile_rejects_non_source_pack_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    db = ContextBuildRunDB()
    client = _client(monkeypatch, db=db)
    created = client.post(
        "/workspaces/ws_1/context-build-runs",
        json={
            "input_mode": "single_document",
            "input_fingerprint": "files:policy.md:120",
            "recommended_action": "normal_ingest",
        },
    )
    run_id = created.json()["id"]

    response = client.post(
        f"/workspaces/ws_1/context-build-runs/{run_id}/actions/compile",
        json={"confirmed": True},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "compile_not_available_for_input_mode"
