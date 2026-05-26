from __future__ import annotations

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
from context_builder.routers import tutorial
from context_builder.services.context_build_tutor import (
    ContextBuildTutor,
    TutorCompileResult,
)
from fastapi.testclient import TestClient


def _client(monkeypatch: pytest.MonkeyPatch, tutor_service: ContextBuildTutor | None = None) -> TestClient:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("TRUSTED_HOSTS", '["testserver"]')
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides.clear()
    app.dependency_overrides[get_current_user] = lambda: {"id": "user_1"}
    app.dependency_overrides[get_supabase_anon] = lambda: None
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: None
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
    if tutor_service is not None:
        app.dependency_overrides[tutorial.get_context_build_tutor] = lambda: tutor_service
    return TestClient(app)


def test_tutor_explains_current_context_build_step(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(monkeypatch).post(
        "/workspaces/ws_1/tutorial/messages",
        json={
            "message": "Explique a etapa atual",
            "current_step": "preflight",
            "context_build_run_id": "run_1",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tool_calls"][0]["name"] == "explain_current_step"
    assert body["tool_calls"][0]["status"] == "completed"
    assert "preflight" in body["tool_calls"][0]["result"]["step"]
    assert body["tool_calls"][0]["requires_confirmation"] is False


def test_tutor_refuses_unknown_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(monkeypatch).post(
        "/workspaces/ws_1/tutorial/messages",
        json={"message": "Execute isso", "requested_tool": "delete_workspace"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tool_calls"][0]["name"] == "delete_workspace"
    assert body["tool_calls"][0]["status"] == "refused"
    assert body["tool_calls"][0]["result"]["code"] == "tool_not_allowed"


def test_compile_tool_without_confirmation_requests_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[dict[str, Any]] = []

    def fake_compile(**kwargs: Any) -> TutorCompileResult:
        called.append(kwargs)
        return TutorCompileResult(status="compiled", bundle_hash="sha256:abc")

    response = _client(monkeypatch, ContextBuildTutor(compile_executor=fake_compile)).post(
        "/workspaces/ws_1/tutorial/messages",
        json={
            "message": "Pode compilar o context bundle",
            "requested_tool": "compile_context_bundle_after_confirmation",
            "context_build_run_id": "run_1",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tool_calls"][0]["name"] == "compile_context_bundle_after_confirmation"
    assert body["tool_calls"][0]["status"] == "requires_confirmation"
    assert body["tool_calls"][0]["requires_confirmation"] is True
    assert called == []


def test_compile_tool_with_confirmation_calls_injected_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[dict[str, Any]] = []

    def fake_compile(**kwargs: Any) -> TutorCompileResult:
        called.append(kwargs)
        return TutorCompileResult(
            status="compiled",
            context_build_run_id=kwargs["context_build_run_id"],
            bundle_hash="sha256:abc",
            context_version="ctx-v1",
        )

    response = _client(monkeypatch, ContextBuildTutor(compile_executor=fake_compile)).post(
        "/workspaces/ws_1/tutorial/tool-confirmations",
        json={
            "tool_name": "compile_context_bundle_after_confirmation",
            "confirmation_token": "confirm-ws_1-run_1-compile_context_bundle_after_confirmation",
            "context_build_run_id": "run_1",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tool_calls"][0]["status"] == "completed"
    assert body["tool_calls"][0]["result"]["bundle_hash"] == "sha256:abc"
    assert called == [
        {
            "workspace_id": "ws_1",
            "actor_user_id": "user_1",
            "context_build_run_id": "run_1",
        }
    ]


def test_compile_tool_refuses_invalid_confirmation_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[dict[str, Any]] = []

    def fake_compile(**kwargs: Any) -> TutorCompileResult:
        called.append(kwargs)
        return TutorCompileResult(status="compiled", bundle_hash="sha256:abc")

    response = _client(monkeypatch, ContextBuildTutor(compile_executor=fake_compile)).post(
        "/workspaces/ws_1/tutorial/tool-confirmations",
        json={
            "tool_name": "compile_context_bundle_after_confirmation",
            "confirmation_token": "confirm-run_1",
            "context_build_run_id": "run_1",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tool_calls"][0]["status"] == "refused"
    assert body["tool_calls"][0]["result"]["code"] == "invalid_confirmation_token"
    assert called == []
