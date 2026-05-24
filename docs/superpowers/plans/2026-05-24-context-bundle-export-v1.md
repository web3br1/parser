# Context Bundle Export v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade `context_bundle.v1` API that exports published workspace context for the separate chatbot project.

**Architecture:** Add focused Pydantic schemas, a service that reads only published views and readiness metadata, and a thin FastAPI router. Keep hashing and auditing deterministic, reuse existing Supabase dependency and audit helpers, and avoid a database migration in v1.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Supabase Python client, pytest, ruff, mypy, existing Context Builder monorepo.

---

## Completed Tasks

- [x] Create isolated branch/worktree.
- [x] Verify clean baseline with `tests/api/test_knowledge.py`.
- [x] Write failing tests for schema, service, readiness, route, audit, and isolation.
- [x] Implement `context_builder.schemas.context_bundle`.
- [x] Implement `context_builder.services.context_bundle_service`.
- [x] Implement `context_builder.routers.context_bundle`.
- [x] Register route in `context_builder.main`.
- [x] Add focused contract documentation.

## Required Verification

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_bundle.py tests\api\test_knowledge.py tests\integrity -q
uv run --cache-dir .uv-cache ruff check apps\api tests\api
npm run typecheck:python
npm run typecheck:python:strict-full
```

## Release Requirements

- `context_bundle.v1` returns only published active knowledge.
- Readiness blocks unknowns and blocking contradictions.
- Hash is deterministic.
- Successful export creates `audit_logs.action = 'context_bundle.export'`.
- No secrets, raw prompts, local paths, signed URLs, stack traces, or draft
  content appear in the bundle.
