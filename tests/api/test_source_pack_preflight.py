from __future__ import annotations

import shutil
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

GOLD_DIR = Path(r"C:\tmp\context-builder-sources\compounding-pharmacy-gold")


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
    def __init__(self, db: PreflightPersistDB, table: str) -> None:
        self.db = db
        self.table = table
        self.payload: dict[str, Any] = {}

    def insert(self, payload: dict[str, Any]) -> Query:
        self.payload = payload
        return self

    def execute(self) -> Result:
        assert self.table == "source_pack_import_runs"
        row = {
            "id": "run_1",
            "created_at": "2026-05-25T00:00:00+00:00",
            "updated_at": "2026-05-25T00:00:00+00:00",
            **self.payload,
        }
        self.db.rows.append(row)
        return Result([row])


class PreflightPersistDB:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def table(self, name: str) -> Query:
        return Query(self, name)


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
def test_source_pack_preflight_detects_complete_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(monkeypatch).post(
        "/workspaces/ws_1/sources/source-pack/preflight",
        json={"source_dir": str(GOLD_DIR)},
    )

    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert body["is_source_pack"] is True
    assert body["status"] == "complete"
    assert body["recommended_action"] == "compile_as_source_pack"
    assert body["source_pack_id"] == "compounding-pharmacy-gold-source-pack"
    assert body["source_pack_version"] == "2026-05-25.v4"
    assert body["numbered_source_count"] == 64
    assert body["csv_count"] == 39
    assert body["markdown_count"] == 25
    assert body["missing_files"] == []
    assert body["extra_files"] == []


def test_source_pack_preflight_without_manifest_falls_back_to_normal_ingest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    upload_dir = tmp_path / "loose-upload"
    upload_dir.mkdir()
    (upload_dir / "catalog.csv").write_text("id,name\n1,A\n", encoding="utf-8")

    response = _client(monkeypatch).post(
        "/workspaces/ws_1/sources/source-pack/preflight",
        json={"source_dir": str(upload_dir)},
    )

    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert body["is_source_pack"] is False
    assert body["status"] == "not_source_pack"
    assert body["recommended_action"] == "normal_ingest"
    assert body["source_pack_id"] is None


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
def test_source_pack_preflight_rejects_incomplete_pack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    broken_dir = tmp_path / "broken-pack"
    shutil.copytree(GOLD_DIR, broken_dir)
    (broken_dir / "40_quote_rules_matrix.csv").unlink()

    response = _client(monkeypatch).post(
        "/workspaces/ws_1/sources/source-pack/preflight",
        json={"source_dir": str(broken_dir)},
    )

    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert body["is_source_pack"] is True
    assert body["status"] == "incomplete"
    assert body["recommended_action"] == "reject"
    assert body["missing_files"] == ["40_quote_rules_matrix.csv"]


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
def test_source_pack_preflight_can_persist_import_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = PreflightPersistDB()
    client = _client(monkeypatch, db=db)

    response = client.post(
        "/workspaces/ws_1/sources/source-pack/preflight",
        json={"source_dir": str(GOLD_DIR), "persist": True},
    )

    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert body["import_run_id"] == "run_1"
    assert db.rows[0]["status"] == "preflighted"
    assert db.rows[0]["recommended_action"] == "compile_as_source_pack"
    assert db.rows[0]["input_hash"].startswith("sha256:")
