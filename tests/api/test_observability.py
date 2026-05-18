from fastapi import FastAPI
from fastapi.testclient import TestClient
from observability.middleware import RequestIdMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_request_id_is_generated() -> None:
    client = TestClient(_app())

    response = client.get("/ok")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_request_id_header_is_preserved() -> None:
    client = TestClient(_app())

    response = client.get("/ok", headers={"X-Request-ID": "req-123"})

    assert response.headers["X-Request-ID"] == "req-123"
