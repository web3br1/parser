# Query Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `POST /workspaces/{workspace_id}/query` as an auditable API endpoint that answers only from published data and records audit/usage metadata.

**Architecture:** Add a small FastAPI router, Pydantic schemas, and a focused `query_service` that retrieves published facts/rules, builds a bounded deterministic context pack, decides `answer_state`, and persists `query_audits` plus `audit_logs`. The MVP implementation uses deterministic answering and token estimation; LLM answer/condensation hooks remain explicit but disabled by default.

**Tech Stack:** FastAPI, Pydantic v2, Supabase Python client query builder, pytest with existing fake DB patterns.

---

### Task 1: Router Contract And Auth

**Files:**
- Create: `apps/api/src/context_builder/schemas/query.py`
- Create: `apps/api/src/context_builder/routers/query.py`
- Modify: `apps/api/src/context_builder/main.py`
- Test: `tests/api/test_query.py`

- [ ] **Step 1: Write failing router tests**

Add tests that prove:

```python
def test_query_without_bearer_returns_401(monkeypatch):
    _env(monkeypatch)
    response = TestClient(create_app()).post(
        f"/workspaces/{WORKSPACE_ID}/query",
        json={"question": "Qual o preco do corte?"},
    )
    assert response.status_code == 401


def test_query_with_member_calls_service_and_returns_audit_payload(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr(
        query_service,
        "answer_query",
        lambda db, **kw: {
            "audit_id": str(uuid4()),
            "answer_state": "not_found",
            "answer": "Nao encontrei essa informacao nas fontes validadas.",
            "confidence": 0.0,
            "used_unvalidated_data": False,
            "facts_used": [],
            "rules_used": [],
            "sources_used": [],
            "evidence": [],
            "missing_data": ["published_data"],
            "warnings": [],
            "usage": {
                "model_provider": None,
                "model_name": None,
                "model_context_limit_tokens": None,
                "context_budget_tokens": 6000,
                "context_pack_tokens_estimated": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost": 0.0,
            },
        },
    )
    response = _client_member(QueryDB()).post(
        f"/workspaces/{WORKSPACE_ID}/query",
        json={"question": "Qual o preco do corte?"},
    )
    assert response.status_code == 200
    assert response.json()["answer_state"] == "not_found"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\api\test_query.py -q`

Expected: fails because `context_builder.routers.query` or route does not exist.

- [ ] **Step 3: Implement schemas and router**

Create `QueryRequest`, `QueryResponse`, `QueryUsage`, `QueryEvidence`, route `POST ""`, and include it at `/workspaces/{workspace_id}/query`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests\api\test_query.py -q`

Expected: router tests pass.

### Task 2: Deterministic Query Service

**Files:**
- Create: `apps/api/src/context_builder/services/query_service.py`
- Test: `tests/api/test_query.py`

- [ ] **Step 1: Write failing service tests**

Add tests for:

```python
def test_query_returns_not_found_and_audits_when_no_published_data():
    db = QueryDB()
    result = query_service.answer_query(
        db,
        workspace_id=WORKSPACE_ID,
        user_id=USER_ID,
        user_role="staff",
        question="Qual o preco do corte?",
        max_output_tokens=700,
        include_evidence=True,
    )
    assert result["answer_state"] == "not_found"
    assert result["used_unvalidated_data"] is False
    assert db.inserted["query_audits"][0]["answer_state"] == "not_found"
    assert db.inserted["audit_logs"][0]["action"] == "query.answer"
```

```python
def test_query_uses_only_published_views_for_answer():
    db = QueryDB()
    db.published_facts.append(_published_price_fact())
    result = query_service.answer_query(...)
    assert result["answer_state"] == "valid_answer"
    assert db.selected_tables_for_answer == ["published_facts", "published_rules"]
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\api\test_query.py -q`

Expected: fails because `query_service.answer_query` is missing.

- [ ] **Step 3: Implement service**

Implement candidate retrieval, answer state decision, deterministic answer generation, query audit insert, audit log insert, and evidence shaping.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests\api\test_query.py -q`

Expected: query tests pass.

### Task 3: Token Budget And Sensitive Filtering

**Files:**
- Modify: `apps/api/src/context_builder/config.py`
- Modify: `apps/api/src/context_builder/services/query_service.py`
- Test: `tests/api/test_query.py`

- [ ] **Step 1: Write failing tests**

Add tests proving:

```python
def test_context_pack_estimate_respects_budget():
    db = QueryDB()
    db.published_facts.extend([_published_price_fact(content_suffix=str(i)) for i in range(50)])
    result = query_service.answer_query(...)
    assert result["usage"]["context_pack_tokens_estimated"] <= result["usage"]["context_budget_tokens"]
```

```python
def test_staff_context_filters_sensitive_fields():
    db = QueryDB()
    db.published_facts.append(_published_price_fact(extra={"cost": 10, "margin": 40}))
    result = query_service.answer_query(..., user_role="staff")
    assert "cost" not in str(result)
    assert "margin" not in str(result)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\api\test_query.py -q`

Expected: fails until budget and filtering are implemented.

- [ ] **Step 3: Implement budget and filtering**

Add query settings and conservative token estimator. Build context by rank and stop before budget. Recursively remove sensitive keys for `staff`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests\api\test_query.py -q`

Expected: query tests pass.

### Task 4: Regression Run

**Files:**
- Test only

- [ ] **Step 1: Run focused API suite**

Run: `.venv\Scripts\python.exe -m pytest tests\api -q`

Expected: all API tests pass.

- [ ] **Step 2: Run query test in verbose mode**

Run: `.venv\Scripts\python.exe -m pytest tests\api\test_query.py -q`

Expected: all query tests pass.

