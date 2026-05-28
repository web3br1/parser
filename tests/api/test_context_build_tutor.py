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


def test_compile_result_includes_bundle_and_readiness_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_compile(**kwargs: Any) -> TutorCompileResult:
        return TutorCompileResult(
            status="compiled",
            context_build_run_id="run_1",
            bundle_hash="sha256:abc",
            context_version="ctx-v1",
            output_path="/out/bundle.json",
            readiness_status="ready",
            readiness_score=95,
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
    result = response.json()["tool_calls"][0]["result"]
    assert result["status"] == "compiled"
    assert result["bundle_hash"] == "sha256:abc"
    assert result["output_path"] == "/out/bundle.json"
    assert result["readiness_status"] == "ready"
    assert result["readiness_score"] == 95


def test_compile_result_omits_none_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_compile(**kwargs: Any) -> TutorCompileResult:
        return TutorCompileResult(status="compiled", bundle_hash="sha256:abc")

    response = _client(monkeypatch, ContextBuildTutor(compile_executor=fake_compile)).post(
        "/workspaces/ws_1/tutorial/tool-confirmations",
        json={
            "tool_name": "compile_context_bundle_after_confirmation",
            "confirmation_token": "confirm-ws_1-None-compile_context_bundle_after_confirmation",
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()["tool_calls"][0]["result"]
    assert "output_path" not in result
    assert "readiness_status" not in result
    assert "readiness_score" not in result
    assert "error" not in result


def test_compile_executor_returns_failed_when_run_id_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Router compile_executor must return TutorCompileResult(failed) for missing run_id."""
    from context_builder.routers.tutorial import get_context_build_tutor

    tutor = get_context_build_tutor(db=None)
    result = tutor._compile_executor(  # type: ignore[union-attr]
        workspace_id="ws_1",
        actor_user_id="user_1",
        context_build_run_id=None,
    )

    assert result.status == "failed"
    assert result.error == "context_build_run_id_required"


def test_compile_executor_handles_http_exception_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Router compile_executor must catch HTTPException and return TutorCompileResult(failed)."""
    import context_builder.routers.tutorial as tutorial_mod
    from context_builder.routers.tutorial import get_context_build_tutor
    from fastapi import HTTPException as FastAPIHTTPException

    monkeypatch.setattr(
        tutorial_mod,
        "compile_context_build_run",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            FastAPIHTTPException(
                status_code=409,
                detail={"code": "context_build_run_not_compilable"},
            )
        ),
    )

    tutor = get_context_build_tutor(db=None)
    result = tutor._compile_executor(  # type: ignore[union-attr]
        workspace_id="ws_1",
        actor_user_id="user_1",
        context_build_run_id="run_1",
    )

    assert result.status == "failed"
    assert result.error == "context_build_run_not_compilable"


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


# ---------------------------------------------------------------------------
# CONTRACT GAP 1: token round-trip
# The token returned by requires_confirmation must be exactly the token
# accepted by tool-confirmations. Frontend must not hardcode it.
# ---------------------------------------------------------------------------

def test_confirmation_token_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Token emitted by requires_confirmation is valid for tool-confirmations."""
    compiled: list[bool] = []

    def fake_compile(**kwargs: Any) -> TutorCompileResult:
        compiled.append(True)
        return TutorCompileResult(
            status="compiled",
            context_build_run_id="run_42",
            bundle_hash="sha256:deadbeef",
        )

    client = _client(monkeypatch, ContextBuildTutor(compile_executor=fake_compile))

    # Step 1: message → requires_confirmation → extract token from response
    step1 = client.post(
        "/workspaces/ws_1/tutorial/messages",
        json={
            "message": "Compilar o bundle",
            "requested_tool": "compile_context_bundle_after_confirmation",
            "context_build_run_id": "run_42",
        },
    )
    assert step1.status_code == 200, step1.text
    step1_body = step1.json()
    assert step1_body["tool_calls"][0]["status"] == "requires_confirmation"
    token = step1_body["tool_calls"][0]["result"]["confirmation_token_hint"]
    assert isinstance(token, str) and len(token) > 0

    # Step 2: use that exact token in tool-confirmations
    step2 = client.post(
        "/workspaces/ws_1/tutorial/tool-confirmations",
        json={
            "tool_name": "compile_context_bundle_after_confirmation",
            "confirmation_token": token,
            "context_build_run_id": "run_42",
        },
    )
    assert step2.status_code == 200, step2.text
    step2_body = step2.json()
    assert step2_body["tool_calls"][0]["status"] == "completed"
    assert step2_body["tool_calls"][0]["result"]["bundle_hash"] == "sha256:deadbeef"
    assert compiled == [True], "compile_executor must be called exactly once"


# ---------------------------------------------------------------------------
# CONTRACT GAP 2: no executor → 409
# Frontend must handle 409 separately from 4xx auth errors.
# ---------------------------------------------------------------------------

def test_compile_without_executor_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tutor with no compile_executor returns 409 when compile is confirmed."""
    response = _client(monkeypatch, ContextBuildTutor(compile_executor=None)).post(
        "/workspaces/ws_1/tutorial/tool-confirmations",
        json={
            "tool_name": "compile_context_bundle_after_confirmation",
            "confirmation_token": "confirm-ws_1-run_1-compile_context_bundle_after_confirmation",
            "context_build_run_id": "run_1",
        },
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "context_build_compile_unavailable"


# ---------------------------------------------------------------------------
# CONTRACT GAP 3: failed executor error propagates
# Frontend must display error codes from executor failures.
# ---------------------------------------------------------------------------

def test_failed_executor_result_propagates_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_compile(**kwargs: Any) -> TutorCompileResult:
        return TutorCompileResult(status="failed", error="source_pack_not_ready")

    response = _client(monkeypatch, ContextBuildTutor(compile_executor=failing_compile)).post(
        "/workspaces/ws_1/tutorial/tool-confirmations",
        json={
            "tool_name": "compile_context_bundle_after_confirmation",
            "confirmation_token": "confirm-ws_1-run_1-compile_context_bundle_after_confirmation",
            "context_build_run_id": "run_1",
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()["tool_calls"][0]["result"]
    assert result["status"] == "failed"
    assert result["error"] == "source_pack_not_ready"


# ---------------------------------------------------------------------------
# CONTRACT GAP 4: RBAC — staff/reviewer cannot call tool-confirmations
# require_upload_permission allows only owner and manager.
# ---------------------------------------------------------------------------

def test_reviewer_cannot_call_tool_confirmations(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException as FastAPIHTTPException

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("TRUSTED_HOSTS", '["testserver"]')
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides.clear()
    app.dependency_overrides[get_current_user] = lambda: {"id": "reviewer_1"}
    app.dependency_overrides[get_supabase_anon] = lambda: None
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: None
    app.dependency_overrides[require_workspace_member] = lambda: {
        "workspace_id": "ws_1",
        "role": "reviewer",
        "user": {"id": "reviewer_1"},
    }

    async def _reviewer_upload_denied() -> None:
        raise FastAPIHTTPException(
            status_code=403,
            detail={
                "code": "insufficient_role",
                "required": sorted(["manager", "owner"]),
                "current": "reviewer",
            },
        )

    app.dependency_overrides[require_upload_permission] = _reviewer_upload_denied

    client = TestClient(app)
    response = client.post(
        "/workspaces/ws_1/tutorial/tool-confirmations",
        json={
            "tool_name": "compile_context_bundle_after_confirmation",
            "confirmation_token": "any-token",
            "context_build_run_id": "run_1",
        },
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "insufficient_role"


# ---------------------------------------------------------------------------
# CONTRACT GAP 5: natural language inference
# Frontend may send plain text; tutor must infer the right tool.
# ---------------------------------------------------------------------------

def test_natural_language_compile_message_infers_compile_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_compile(**kwargs: Any) -> TutorCompileResult:
        return TutorCompileResult(status="compiled", bundle_hash="sha256:abc")

    response = _client(monkeypatch, ContextBuildTutor(compile_executor=fake_compile)).post(
        "/workspaces/ws_1/tutorial/messages",
        json={
            "message": "Pode compilar agora?",
            "context_build_run_id": "run_1",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    call = body["tool_calls"][0]
    assert call["name"] == "compile_context_bundle_after_confirmation"
    assert call["status"] == "requires_confirmation"


def test_natural_language_blockers_message_infers_list_blockers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(monkeypatch).post(
        "/workspaces/ws_1/tutorial/messages",
        json={"message": "Quais são os bloqueios?", "context_build_run_id": "run_1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tool_calls"][0]["name"] == "list_blockers"
    assert body["tool_calls"][0]["status"] == "completed"


# ---------------------------------------------------------------------------
# CONTRACT GAP 6: detected_input passthrough in summarize
# Frontend sends preflight payload; tutor must echo it in result.
# ---------------------------------------------------------------------------

def test_detected_input_appears_in_summarize_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detected = {"input_mode": "source_pack", "file_count": 64, "has_manifest": True}

    response = _client(monkeypatch).post(
        "/workspaces/ws_1/tutorial/messages",
        json={
            "message": "Resuma a entrada detectada",
            "requested_tool": "summarize_detected_input",
            "detected_input": detected,
            "context_build_run_id": "run_1",
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()["tool_calls"][0]["result"]
    assert result["detected_input"] == detected


# ---------------------------------------------------------------------------
# CONTRACT GAP 7: request validation — message field
# Frontend must not send empty or oversized messages.
# ---------------------------------------------------------------------------

def test_empty_message_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(monkeypatch).post(
        "/workspaces/ws_1/tutorial/messages",
        json={"message": ""},
    )

    assert response.status_code == 422, response.text


def test_message_above_limit_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(monkeypatch).post(
        "/workspaces/ws_1/tutorial/messages",
        json={"message": "x" * 4001},
    )

    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# CONTRACT GAP 8: response shape guarantee
# Every response must carry message (str) and exactly one tool_call with
# the required fields. Frontend can always destructure safely.
# ---------------------------------------------------------------------------

def test_response_always_has_message_and_single_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structural contract: message str + tool_calls list with required keys."""
    response = _client(monkeypatch).post(
        "/workspaces/ws_1/tutorial/messages",
        json={"message": "Explique o passo atual", "current_step": "compile"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["message"], str) and len(body["message"]) > 0
    assert isinstance(body["tool_calls"], list) and len(body["tool_calls"]) == 1
    call = body["tool_calls"][0]
    assert isinstance(call["name"], str)
    assert call["status"] in {"completed", "refused", "requires_confirmation", "unavailable"}
    assert isinstance(call["requires_confirmation"], bool)
    assert isinstance(call["result"], dict)


# ---------------------------------------------------------------------------
# CONTRACT GAP 9: allowed_tools list in refused response
# Frontend can surface the allowed list for debugging.
# ---------------------------------------------------------------------------

def test_refused_tool_response_includes_allowed_tools_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from context_builder.services.context_build_tutor import ALLOWED_TOOLS

    response = _client(monkeypatch).post(
        "/workspaces/ws_1/tutorial/messages",
        json={"message": "Faça isso", "requested_tool": "drop_table"},
    )

    assert response.status_code == 200, response.text
    result = response.json()["tool_calls"][0]["result"]
    assert result["code"] == "tool_not_allowed"
    assert set(result["allowed_tools"]) == ALLOWED_TOOLS
