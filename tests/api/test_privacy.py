from typing import Any

from context_builder.dependencies import (
    get_supabase_service_for_backend_only,
    require_workspace_member,
)
from context_builder.routers import privacy
from fastapi import FastAPI
from fastapi.testclient import TestClient


class Result:
    def __init__(self, data: Any, count: int | None = None) -> None:
        self.data = data
        self.count = count


class Query:
    def __init__(self, db: "PrivacyDB", table: str) -> None:
        self.db = db
        self.table = table
        self.payload: dict[str, Any] = {}
        self.update_payload: dict[str, Any] = {}
        self.filters: dict[str, Any] = {}

    def select(self, query: str, **_kwargs: Any) -> "Query":
        return self

    def insert(self, payload: dict[str, Any]) -> "Query":
        self.payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "Query":
        self.update_payload = payload
        return self

    def eq(self, field: str, value: Any) -> "Query":
        self.filters[field] = value
        return self

    def maybe_single(self) -> "Query":
        return self

    def execute(self) -> Result:
        if self.payload:
            row = {"id": f"{self.table}_{len(self.db.tables[self.table]) + 1}", **self.payload}
            self.db.tables[self.table].append(row)
            return Result([row])
        rows = self._matching_rows()
        if self.update_payload:
            for row in rows:
                row.update(self.update_payload)
            return Result(rows)
        if "id" in self.filters:
            return Result(rows[0] if rows else None)
        return Result(rows, count=len(rows))

    def _matching_rows(self) -> list[dict[str, Any]]:
        rows = self.db.tables[self.table]
        for field, value in self.filters.items():
            rows = [row for row in rows if row.get(field) == value]
        return rows


class PrivacyDB:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "privacy_requests": [],
            "sources": [],
            "extracted_facts": [],
            "business_rules": [],
            "query_audits": [],
            "audit_logs": [],
        }

    @property
    def rows(self) -> list[dict[str, Any]]:
        return self.tables["privacy_requests"]

    def table(self, name: str) -> Query:
        return Query(self, name)


def _client(db: PrivacyDB, role: str = "owner") -> TestClient:
    app = FastAPI()
    app.include_router(privacy.router, prefix="/workspaces/{workspace_id}/privacy")
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: db
    app.dependency_overrides[require_workspace_member] = lambda: {
        "user": {"id": "user_1"},
        "role": role,
        "workspace_id": "ws_1",
    }
    return TestClient(app)


def test_export_creates_auditable_owner_request() -> None:
    db = PrivacyDB()
    db.tables["sources"].append(
        {
            "id": "source_1",
            "workspace_id": "ws_1",
            "deleted_at": None,
            "storage_bucket": "source-files",
            "storage_path": "ws_1/source_1.pdf",
        }
    )
    db.tables["extracted_facts"].append({"id": "fact_1", "workspace_id": "ws_1"})

    response = _client(db).post("/workspaces/ws_1/privacy/export")

    assert response.status_code == 202
    body = response.json()
    assert body["request_id"] == "privacy_requests_1"
    assert body["status"] == "completed"
    assert body["dry_run"] is False
    assert body["report"]["sources_exported"] == 1
    assert body["report"]["facts_exported"] == 1
    assert db.rows[0]["request_type"] == "export"
    assert db.rows[0]["requested_by"] == "user_1"
    assert db.rows[0]["confirmation_required"] is False
    assert db.rows[0]["metadata"]["report"]["facts_exported"] == 1
    assert db.tables["audit_logs"][0]["action"] == "privacy.export.completed"


def test_delete_request_requires_owner_role() -> None:
    response = _client(PrivacyDB(), role="manager").post("/workspaces/ws_1/privacy/delete-request")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_role"


def test_delete_request_without_confirmation_is_dry_run() -> None:
    db = PrivacyDB()
    db.tables["sources"].append(
        {
            "id": "source_1",
            "workspace_id": "ws_1",
            "deleted_at": None,
            "storage_bucket": "source-files",
            "storage_path": "ws_1/source_1.pdf",
        }
    )
    db.tables["business_rules"].append({"id": "rule_1", "workspace_id": "ws_1"})
    db.tables["query_audits"].append({"id": "query_1", "workspace_id": "ws_1"})

    response = _client(db).post("/workspaces/ws_1/privacy/delete-request", json={})

    assert response.status_code == 202
    body = response.json()
    assert body["request_type"] == "delete"
    assert body["status"] == "dry_run"
    assert body["dry_run"] is True
    assert body["deletion_plan"]["sources_to_delete"] == 1
    assert body["deletion_plan"]["rules_to_delete"] == 1
    assert body["deletion_plan"]["query_audits_to_anonymize"] == 1
    assert body["deletion_plan"]["pending_storage_delete"] is True
    assert db.rows[0]["confirmation_required"] is True
    assert db.rows[0]["metadata"]["confirmed"] is False
    assert db.tables["audit_logs"][0]["action"] == "privacy.delete.dry_run"


def test_confirmed_delete_executes_metadata_only_and_audits_report() -> None:
    db = PrivacyDB()
    db.tables["sources"].append(
        {
            "id": "source_1",
            "workspace_id": "ws_1",
            "metadata": {"filename": "terms.pdf"},
            "storage_bucket": "source-files",
            "storage_path": "ws_1/source_1.pdf",
            "deleted_at": None,
        }
    )
    db.tables["sources"].append(
        {
            "id": "source_2",
            "workspace_id": "ws_2",
            "metadata": {},
            "deleted_at": None,
        }
    )
    db.tables["query_audits"].append(
        {
            "id": "query_1",
            "workspace_id": "ws_1",
            "user_id": "user_1",
            "question": "What did Alice sign?",
            "answer": "Alice signed the terms.",
        }
    )
    client = _client(db)
    created = client.post("/workspaces/ws_1/privacy/delete-request", json={}).json()

    response = client.post(
        f"/workspaces/ws_1/privacy/delete-request/{created['request_id']}/confirm",
        json={"confirmation": "DELETE_WORKSPACE_METADATA"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "processing"
    assert body["dry_run"] is False
    assert body["report"]["sources_metadata_deleted"] == 1
    assert body["report"]["query_audits_anonymized"] == 1
    assert body["report"]["pending_storage_delete"] is True
    assert db.tables["sources"][0]["deleted_at"] is not None
    assert db.tables["sources"][0]["metadata"]["privacy_deleted_by_request_id"] == "privacy_requests_1"
    assert db.tables["sources"][1]["deleted_at"] is None
    assert db.tables["query_audits"][0]["user_id"] is None
    assert db.tables["query_audits"][0]["question"] == "[privacy_deleted]"
    assert db.tables["query_audits"][0]["answer"] == "[privacy_deleted]"
    assert db.tables["audit_logs"][-1]["action"] == "privacy.delete.pending_storage"


def test_confirmed_delete_completes_when_no_storage_is_pending() -> None:
    db = PrivacyDB()
    db.tables["sources"].append(
        {
            "id": "source_1",
            "workspace_id": "ws_1",
            "metadata": {},
            "deleted_at": None,
        }
    )
    client = _client(db)
    created = client.post("/workspaces/ws_1/privacy/delete-request", json={}).json()

    response = client.post(
        f"/workspaces/ws_1/privacy/delete-request/{created['request_id']}/confirm",
        json={"confirmation": "DELETE_WORKSPACE_METADATA"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "completed"
    assert body["report"]["pending_storage_delete"] is False
    assert db.tables["audit_logs"][-1]["action"] == "privacy.delete.completed"


def test_delete_confirmation_requires_explicit_phrase() -> None:
    db = PrivacyDB()
    client = _client(db)
    created = client.post("/workspaces/ws_1/privacy/delete-request", json={}).json()

    response = client.post(
        f"/workspaces/ws_1/privacy/delete-request/{created['request_id']}/confirm",
        json={"confirmation": "delete"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_delete_confirmation"


def test_get_delete_request_returns_workspace_scoped_request() -> None:
    db = PrivacyDB()
    created = _client(db).post("/workspaces/ws_1/privacy/delete-request", json={}).json()

    response = _client(db).get(
        f"/workspaces/ws_1/privacy/delete-request/{created['request_id']}",
    )

    assert response.status_code == 200
    assert response.json()["request_id"] == created["request_id"]
