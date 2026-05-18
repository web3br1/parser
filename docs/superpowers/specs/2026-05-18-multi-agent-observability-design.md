# Multi-Agent Observability Design

## Goal

Make the existing pipeline behave like a set of traceable operational agents. Each agent keeps its current business responsibility, but emits consistent lifecycle events that can be correlated across API requests, Celery jobs, database audit rows, source IDs, chunk IDs, and model usage.

## Scope

This first slice is the foundation for deeper multi-agent behavior. It does not introduce autonomous planning, new model calls, or a new orchestration service. It standardizes observability so future agents can be trusted, debugged, and audited.

## Agent Boundaries

- `api-agent`: accepts user actions, validates permissions, starts workflows.
- `ingest-agent`: validates files, parses content, creates chunks, dispatches classification.
- `classification-agent`: detects injection, classifies chunks, routes unknowns or extraction jobs.
- `extraction-agent`: extracts structured records, validates schemas, creates evidence spans.
- `review-agent`: approves, rejects, edits, publishes, and reclassifies.
- `query-agent`: answers from published context and records query audit.
- `sync-agent`: re-enqueues stuck jobs and performs storage cleanup.
- `observability-agent`: provides shared event contracts and timeline reconstruction primitives.

## Event Contract

Every structured event uses a stable event name and consistent correlation fields:

- `agent`: logical agent name.
- `stage`: pipeline stage.
- `action`: lifecycle action.
- `outcome`: `started`, `succeeded`, `failed`, `skipped`, or `queued`.
- `workspace_id`, `source_id`, `chunk_id`, `job_id`, `request_id`, `workflow_id` when known.
- `resource_type`, `resource_id`, `reason`, and count fields when relevant.

`workflow_id` defaults to `source_id` for source pipelines. Query-only flows use the query audit ID as their durable audit correlation point.

## Implementation Strategy

Add a small observability contract module, then use it in the least invasive places first:

- API enqueue flow.
- Review and unknown services, replacing string-formatted logs with JSON logs.
- Worker lifecycle logs where event names already exist.
- Tests that assert event shape, redaction, and request ID propagation.

## Non-Goals

- No OpenTelemetry export in this slice.
- No dashboard UI in this slice.
- No new database migration unless tests prove the current tables cannot carry the needed correlation.
- No broad refactor of worker business logic.

## Success Criteria

- New event helper is covered by tests.
- Review and unknown service logs are structured JSON events.
- Enqueue failure logs preserve `request_id`, `workflow_id`, `job_id`, `workspace_id`, and `source_id`.
- Existing Python and frontend gates still pass.
