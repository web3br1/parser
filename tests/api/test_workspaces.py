from typing import Any

from context_builder.config import get_settings
from context_builder.dependencies import get_current_user, get_supabase_service_for_backend_only
from context_builder.main import create_app
from fastapi.testclient import TestClient


class Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class WorkspaceTable:
    def __init__(self, db: "WorkspaceDB", name: str) -> None:
        self.db = db
        self.name = name
        self.payload: dict[str, Any] = {}

    def insert(self, payload: dict[str, Any]) -> "WorkspaceTable":
        self.payload = payload
        return self

    def select(self, query: str) -> "WorkspaceTable":
        return self

    def eq(self, field: str, value: str) -> "WorkspaceTable":
        self.db.filters.append((self.name, field, value))
        return self

    def maybe_single(self) -> "WorkspaceTable":
        return self

    def execute(self) -> Result:
        if self.name == "workspaces":
            if not self.payload:
                return Result(
                    {
                        "id": self.db.created_workspace_id,
                        "name": "Acme",
                        "slug": "acme",
                        "status": "active",
                        "created_at": "2026-05-06T00:00:00+00:00",
                    }
                )
            workspace = {
                "id": "ws_1",
                "name": self.payload["name"],
                "slug": self.payload["slug"],
                "status": "active",
                "created_at": "2026-05-06T00:00:00+00:00",
            }
            self.db.workspaces.append(workspace)
            return Result([workspace])

        self.db.memberships.append(self.payload)
        return Result(
            [
                {
                    "workspace_id": "ws_1",
                    "workspaces": {
                        "id": "ws_1",
                        "name": "Acme",
                        "slug": "acme",
                        "status": "active",
                        "created_at": "2026-05-06T00:00:00+00:00",
                    },
                }
            ]
        )


class WorkspaceDB:
    def __init__(self) -> None:
        self.workspaces: list[dict[str, Any]] = []
        self.memberships: list[dict[str, Any]] = []
        self.filters: list[tuple[str, str, str]] = []
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.created_workspace_id = "ws_1"

    def table(self, name: str) -> WorkspaceTable:
        return WorkspaceTable(self, name)

    def rpc(self, name: str, payload: dict[str, Any]) -> "WorkspaceDB":
        self.rpc_calls.append((name, payload))
        return self

    def execute(self) -> Result:
        return Result(self.created_workspace_id)


def _client(db: WorkspaceDB) -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"id": "user_1", "email": "u@test.com"}
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: db
    return TestClient(app)


def test_post_workspaces_without_bearer_returns_401(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    get_settings.cache_clear()

    client = TestClient(create_app())

    response = client.post("/workspaces", json={"name": "Acme"})

    assert response.status_code == 401


def test_create_workspace_uses_rpc(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    db = WorkspaceDB()
    client = _client(db)

    response = client.post("/workspaces", json={"name": "Acme", "slug": "acme"})

    assert response.status_code == 201
    assert response.json()["id"] == "ws_1"
    assert db.rpc_calls == [
        (
            "create_workspace_with_owner",
            {
                "workspace_name": "Acme",
                "workspace_slug": "acme",
                "workspace_settings": {},
                "actor_user_id": "user_1",
            },
        )
    ]


def test_list_workspaces_returns_user_workspaces(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    client = _client(WorkspaceDB())

    response = client.get("/workspaces")

    assert response.status_code == 200
    assert response.json()[0]["id"] == "ws_1"
