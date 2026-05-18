import pytest
from context_builder.config import get_settings
from context_builder.main import create_app
from fastapi.testclient import TestClient
from observability.security_middleware import enforce_request_body_limit, reset_rate_limit_state
from starlette.requests import Request
from starlette.responses import JSONResponse


def _env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def test_health_has_production_security_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch, APP_ENV="production", TRUSTED_HOSTS='["testserver"]')

    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert "Strict-Transport-Security" in response.headers


def test_production_rejects_wildcard_trusted_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch, APP_ENV="production", TRUSTED_HOSTS='["*"]')

    with pytest.raises(RuntimeError, match="TRUSTED_HOSTS"):
        create_app()


def test_hsts_is_not_set_outside_production(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch, APP_ENV="development")

    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert "Strict-Transport-Security" not in response.headers


def test_oversized_query_body_is_rejected_before_route(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch, MAX_REQUEST_BODY_BYTES="64")

    response = TestClient(create_app()).post(
        "/workspaces/ws_1/query",
        json={"question": "x" * 256},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "request_body_too_large"


def test_query_route_is_rate_limited_per_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_rate_limit_state()
    _env(
        monkeypatch,
        RATE_LIMIT_QUERY_REQUESTS="1",
        RATE_LIMIT_WINDOW_SECONDS="60",
    )

    client = TestClient(create_app())
    headers = {"Authorization": "Bearer invalid-but-stable"}
    first = client.post("/workspaces/ws_1/query", json={"question": "hello"}, headers=headers)
    second = client.post("/workspaces/ws_1/query", json={"question": "hello"}, headers=headers)

    assert first.status_code == 401
    assert second.status_code == 429
    assert second.json()["detail"] == "rate_limited"
    assert second.headers["Retry-After"]
    reset_rate_limit_state()


def test_trusted_host_rejects_unconfigured_host(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch, TRUSTED_HOSTS='["api.example.test"]')

    response = TestClient(create_app()).get("/health", headers={"host": "evil.example.test"})

    assert response.status_code == 400


@pytest.mark.anyio
async def test_request_body_limit_counts_streamed_body_without_content_length() -> None:
    messages = [
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.request", "body": b"def", "more_body": False},
    ]

    async def receive() -> dict[str, object]:
        return messages.pop(0)

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
            "scheme": "http",
        },
        receive,
    )

    async def call_next(limited_request: Request) -> JSONResponse:
        await limited_request.body()
        return JSONResponse({"ok": True})

    response = await enforce_request_body_limit(request, call_next, max_body_bytes=4)

    assert response.status_code == 413
