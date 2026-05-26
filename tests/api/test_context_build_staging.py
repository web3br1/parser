from __future__ import annotations

import io
import json
import zipfile
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


def _manifest() -> bytes:
    return b"""---
source_pack_id: staged-pack
source_pack_version: v1
language: pt-BR
publication_status: source_seed
---

## Document Roles

| file | document_type | expected_extraction |
|---|---|---|
| 01_policy.md | policy | rules |
"""


def _stage_folder(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/workspaces/ws_1/context-build-runs/staged-uploads",
        files=[
            ("files", ("00_source_manifest.md", _manifest(), "text/markdown")),
            ("files", ("01_policy.md", b"# Policy\nhello\n", "text/markdown")),
        ],
        data={
            "relative_paths": json.dumps(
                ["source-pack/00_source_manifest.md", "source-pack/01_policy.md"]
            )
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_folder_upload_stages_and_preflight_persists_source_pack_without_source_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CONTEXT_BUILD_STAGING_ROOT", str(tmp_path / "staging"))
    db = ContextBuildRunDB()
    client = _client(monkeypatch, db=db)

    staged = _stage_folder(client)

    assert staged["staged_upload_id"]
    assert staged["input_hash"].startswith("sha256:")
    assert staged["input_fingerprint"].startswith("staged_upload:")
    assert [item["relative_path"] for item in staged["files"]] == [
        "source-pack/00_source_manifest.md",
        "source-pack/01_policy.md",
    ]
    assert "source_dir" not in staged

    preflight = client.post(
        "/workspaces/ws_1/context-build-runs/preflight",
        json={"staged_upload_id": staged["staged_upload_id"], "persist": True},
    )

    assert preflight.status_code == 200, preflight.text
    body = preflight.json()
    assert body["run_id"] == "run_1"
    assert body["input_mode"] == "source_pack"
    assert body["recommended_action"] == "compile_as_source_pack"
    assert body["blocking_reasons"] == []
    assert body["input_hash"] == staged["input_hash"]
    assert body["metadata"]["staged_upload_id"] == staged["staged_upload_id"]
    assert "source_dir" not in body
    assert db.rows[0]["staged_upload_id"] == staged["staged_upload_id"]
    assert db.rows[0]["source_dir"] is None


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


def test_compile_source_pack_uses_staged_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    staging_root = tmp_path / "staging"
    monkeypatch.setenv("CONTEXT_BUILD_STAGING_ROOT", str(staging_root))
    db = ContextBuildRunDB()
    client = _client(monkeypatch, db=db)
    staged = _stage_folder(client)
    preflight = client.post(
        "/workspaces/ws_1/context-build-runs/preflight",
        json={"staged_upload_id": staged["staged_upload_id"], "persist": True},
    )
    run_id = preflight.json()["run_id"]
    calls: dict[str, Any] = {}

    def fake_compile(path: Path) -> _FakeBundle:
        calls["compiled_path"] = path
        return _FakeBundle(
            context_version="ctx_test",
            integrity=_FakeIntegrity(bundle_hash="sha256:bundle"),
            readiness=_FakeReadiness(status="ready", score=95, warnings=[]),
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
    compiled_path = calls["compiled_path"]
    assert compiled_path.is_relative_to(staging_root)
    assert compiled_path.name == "source-pack"
    assert calls["output_path"] == compiled_path / "source-pack.context_bundle.v1.json"
    assert response.json()["status"] == "compiled"
    assert not response.json()["output_path"].startswith(str(staging_root))


def test_zip_upload_stages_and_preflights_as_source_pack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CONTEXT_BUILD_STAGING_ROOT", str(tmp_path / "staging"))
    db = ContextBuildRunDB()
    client = _client(monkeypatch, db=db)

    stage = client.post(
        "/workspaces/ws_1/context-build-runs/staged-uploads",
        files=[
            (
                "files",
                (
                    "source-pack.zip",
                    _zip_bytes(
                        {
                            "source-pack/00_source_manifest.md": _manifest(),
                            "source-pack/01_policy.md": b"# Policy\nhello\n",
                        }
                    ),
                    "application/zip",
                ),
            )
        ],
    )
    assert stage.status_code == 201, stage.text

    preflight = client.post(
        "/workspaces/ws_1/context-build-runs/preflight",
        json={"staged_upload_id": stage.json()["staged_upload_id"], "persist": True},
    )

    assert preflight.status_code == 200, preflight.text
    body = preflight.json()
    assert body["input_mode"] == "source_pack"
    assert body["blocking_reasons"] == []
    assert body["metadata"]["staged_upload_id"] == stage.json()["staged_upload_id"]


def test_zip_slip_upload_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CONTEXT_BUILD_STAGING_ROOT", str(tmp_path / "staging"))
    client = _client(monkeypatch, db=ContextBuildRunDB())

    response = client.post(
        "/workspaces/ws_1/context-build-runs/staged-uploads",
        files=[
            (
                "files",
                ("bad.zip", _zip_bytes({"../00_source_manifest.md": _manifest()}), "application/zip"),
            )
        ],
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_relative_path"


def test_duplicate_zip_entry_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CONTEXT_BUILD_STAGING_ROOT", str(tmp_path / "staging"))
    client = _client(monkeypatch, db=ContextBuildRunDB())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("source-pack/01_policy.md", b"# First\n")
        archive.writestr("source-pack/01_POLICY.md", b"# Duplicate\n")

    response = client.post(
        "/workspaces/ws_1/context-build-runs/staged-uploads",
        files=[("files", ("dupe.zip", buffer.getvalue(), "application/zip"))],
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "duplicate_relative_path"


def test_zip_entry_read_error_is_rejected_as_invalid_zip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CONTEXT_BUILD_STAGING_ROOT", str(tmp_path / "staging"))
    client = _client(monkeypatch, db=ContextBuildRunDB())

    original_read = zipfile.ZipFile.read

    def broken_read(self: zipfile.ZipFile, name: object, pwd: bytes | None = None) -> bytes:
        raise RuntimeError("encrypted or unreadable zip entry")

    monkeypatch.setattr(zipfile.ZipFile, "read", broken_read)
    response = client.post(
        "/workspaces/ws_1/context-build-runs/staged-uploads",
        files=[
            (
                "files",
                (
                    "bad.zip",
                    _zip_bytes({"source-pack/00_source_manifest.md": _manifest()}),
                    "application/zip",
                ),
            )
        ],
    )
    monkeypatch.setattr(zipfile.ZipFile, "read", original_read)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_zip"


def test_staging_root_uses_default_namespace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    staging_root = tmp_path / "staging"
    monkeypatch.setenv("CONTEXT_BUILD_STAGING_ROOT", str(staging_root))
    client = _client(monkeypatch, db=ContextBuildRunDB())

    staged = _stage_folder(client)

    assert (staging_root / "default").exists()
    assert any((staging_root / "default").rglob(staged["staged_upload_id"]))


def test_single_oversized_file_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CONTEXT_BUILD_STAGING_ROOT", str(tmp_path / "staging"))
    monkeypatch.setattr(
        "context_builder.services.context_build_staging.MAX_STAGED_BYTES",
        4,
    )
    client = _client(monkeypatch, db=ContextBuildRunDB())

    response = client.post(
        "/workspaces/ws_1/context-build-runs/staged-uploads",
        files=[("files", ("policy.md", b"12345", "text/markdown"))],
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "staged_upload_too_large"


def test_too_many_multipart_files_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CONTEXT_BUILD_STAGING_ROOT", str(tmp_path / "staging"))
    monkeypatch.setattr(
        "context_builder.services.context_build_staging.MAX_STAGED_FILES",
        1,
    )
    client = _client(monkeypatch, db=ContextBuildRunDB())

    response = client.post(
        "/workspaces/ws_1/context-build-runs/staged-uploads",
        files=[
            ("files", ("a.md", b"# A", "text/markdown")),
            ("files", ("b.md", b"# B", "text/markdown")),
        ],
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "too_many_files"


def test_rejected_staged_source_pack_blocks_compile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CONTEXT_BUILD_STAGING_ROOT", str(tmp_path / "staging"))
    db = ContextBuildRunDB()
    client = _client(monkeypatch, db=db)

    stage = client.post(
        "/workspaces/ws_1/context-build-runs/staged-uploads",
        files=[("files", ("00_source_manifest.md", _manifest(), "text/markdown"))],
    )
    assert stage.status_code == 201, stage.text
    preflight = client.post(
        "/workspaces/ws_1/context-build-runs/preflight",
        json={"staged_upload_id": stage.json()["staged_upload_id"], "persist": True},
    )
    assert preflight.status_code == 200, preflight.text
    body = preflight.json()
    assert body["status"] == "rejected"
    assert body["blocking_reasons"]

    response = client.post(
        f"/workspaces/ws_1/context-build-runs/{body['run_id']}/actions/compile",
        json={"confirmed": True},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "context_build_run_not_compilable"


def test_relative_path_traversal_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CONTEXT_BUILD_STAGING_ROOT", str(tmp_path / "staging"))
    client = _client(monkeypatch, db=ContextBuildRunDB())

    response = client.post(
        "/workspaces/ws_1/context-build-runs/staged-uploads",
        files=[("files", ("policy.md", b"# Policy\n", "text/markdown"))],
        data={"relative_paths": json.dumps(["../policy.md"])},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_relative_path"


@pytest.mark.parametrize("filename", ["malware.exe", ".env", "secret.pem", "script.ps1"])
def test_blocked_extension_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    filename: str,
) -> None:
    monkeypatch.setenv("CONTEXT_BUILD_STAGING_ROOT", str(tmp_path / "staging"))
    client = _client(monkeypatch, db=ContextBuildRunDB())

    response = client.post(
        "/workspaces/ws_1/context-build-runs/staged-uploads",
        files=[("files", (filename, b"blocked", "application/octet-stream"))],
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "blocked_file_type"
