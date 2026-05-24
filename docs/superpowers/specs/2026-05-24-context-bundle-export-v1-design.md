# Context Bundle Export v1 Design

Status: implemented in branch `codex-context-bundle-export-v1`.
Date: 2026-05-24

## Summary

Add a production-grade `context_bundle.v1` export surface for the separate
chatbot project. Context Builder remains responsible for parsing, validating,
reviewing, publishing, readiness checks, hashing, and auditability. The chatbot
project remains responsible for wizard UI, runtime activation, and end-user
conversations.

## Goals

- Export a stable JSON artifact for one workspace.
- Use only published sources, facts, rules, and linked evidence.
- Block readiness for open unknowns and blocking contradictions.
- Warn for missing evidence and low confidence.
- Generate deterministic `bundle_hash` and `context_version`.
- Audit successful exports with `context_bundle.export`.

## Non-Goals

- No chatbot runtime in this repository.
- No raw source text export.
- No vector database.
- No entity graph in v1.
- No persisted snapshots in v1.
- No external deployment work.

## Architecture

Files:

- `schemas/context_bundle.py`: Pydantic response contract.
- `services/context_bundle_service.py`: data loading, readiness, hashing, audit.
- `routers/context_bundle.py`: thin FastAPI endpoint.
- `main.py`: route registration.
- `tests/api/test_context_bundle.py`: TDD coverage.

The service reads `published_sources`, `published_facts`, `published_rules`,
and referenced `evidence_spans`. It counts `unknown_facts_queue.status='open'`
and `contradictions.status in ('open', 'needs_review')` for readiness.

## Security

The bundle excludes secrets, bearer tokens, signed URLs, local paths, raw
prompts, provider responses, stack traces, draft facts/rules, deleted source
content, and unknown queue raw text.

## Acceptance

- Empty workspace returns blocked bundle.
- Published records appear.
- Cross-workspace records are filtered.
- Missing evidence warns.
- Low confidence warns.
- Unknowns and contradictions block.
- Hash is deterministic for identical content.
- Export writes an audit log row.
