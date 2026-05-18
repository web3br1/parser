# Multi-Agent Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first production-safe multi-agent observability layer by standardizing lifecycle event contracts and converting key API services to structured correlated logs.

**Architecture:** Keep the current FastAPI, Celery, and Supabase architecture. Add a focused `observability.events` module that defines agent/stage/action/outcome event names and builds safe JSON log fields consumed by the existing `JsonLogger`.

**Tech Stack:** Python 3.12+, FastAPI, Celery, Supabase client, pytest, existing `observability.logging.JsonLogger`.

---

## File Structure

- Create `packages/observability/src/observability/events.py`: shared event naming and field builder.
- Modify `packages/observability/src/observability/__init__.py`: export the event helper.
- Modify `packages/observability/tests/test_events.py`: contract tests for event names and correlation fields.
- Modify `apps/api/src/context_builder/services/ingest_queue.py`: structured enqueue success/failure logs.
- Modify `apps/api/src/context_builder/services/review_service.py`: replace string logs with structured review-agent events.
- Modify `apps/api/src/context_builder/services/unknown_service.py`: replace string logs with structured review-agent events.

## Task 1: Event Contract Module

**Files:**
- Create: `packages/observability/src/observability/events.py`
- Modify: `packages/observability/src/observability/__init__.py`
- Test: `packages/observability/tests/test_events.py`

- [ ] Write tests for `agent_event()` returning a dotted event name and stable correlation fields.
- [ ] Implement `agent_event()` with validation-free, low-risk string normalization.
- [ ] Export `agent_event` from `observability.__init__`.
- [ ] Run `uv run --cache-dir .uv-cache pytest packages/observability/tests/test_events.py`.

## Task 2: API Enqueue Correlation

**Files:**
- Modify: `apps/api/src/context_builder/services/ingest_queue.py`
- Test: `tests/api/test_ingest_queue_decoupling.py`

- [ ] Add a test proving enqueue failure is logged through `JsonLogger` with `request_id`, `workflow_id`, `job_id`, `workspace_id`, and `source_id`.
- [ ] Replace `logging.getLogger("api").warning(...)` with structured `get_logger("api").warning(...)`.
- [ ] Add a success/queued event after the enqueue attempt returns.
- [ ] Run `uv run --cache-dir .uv-cache pytest tests/api/test_ingest_queue_decoupling.py`.

## Task 3: Review/Unknown Structured Events

**Files:**
- Modify: `apps/api/src/context_builder/services/review_service.py`
- Modify: `apps/api/src/context_builder/services/unknown_service.py`
- Test: `tests/api/test_review.py`
- Test: `tests/api/test_unknown.py`

- [ ] Replace module loggers with `get_logger("api")`.
- [ ] Convert approve/reject/edit/publish logs to structured `review-agent` lifecycle events.
- [ ] Convert unknown reclassify/ignore/dispatch-failed logs to structured `review-agent` lifecycle events.
- [ ] Preserve existing business behavior and exceptions.
- [ ] Run `uv run --cache-dir .uv-cache pytest tests/api/test_review.py tests/api/test_unknown.py`.

## Task 4: Integration Gates

**Files:**
- No production files unless previous tasks reveal a small integration gap.

- [ ] Run `uv run --cache-dir .uv-cache pytest packages/observability/tests tests/api/test_ingest_queue_decoupling.py tests/api/test_review.py tests/api/test_unknown.py`.
- [ ] Run `uv run --cache-dir .uv-cache pytest`.
- [ ] Run `uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p observability -p context_builder`.
- [ ] Run `npm run typecheck`.
- [ ] Report any pre-existing lint issue separately from this implementation.

## SDD Agent Ownership

- Agent A owns `packages/observability/src/observability/events.py`, `packages/observability/src/observability/__init__.py`, and `packages/observability/tests/test_events.py`.
- Agent B owns `apps/api/src/context_builder/services/ingest_queue.py` and `tests/api/test_ingest_queue_decoupling.py`.
- Agent C owns `apps/api/src/context_builder/services/review_service.py`, `apps/api/src/context_builder/services/unknown_service.py`, `tests/api/test_review.py`, and `tests/api/test_unknown.py`.
- Controller owns integration, final gates, and conflict resolution.
