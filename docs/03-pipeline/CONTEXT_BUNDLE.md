# CONTEXT_BUNDLE.md - Context Bundle Export Contract

This document defines the first export contract for sending compiled context
from the Context Compiler/local extractor to an external chatbot runtime.

The bundle is not a chat response and does not mutate the consumer runtime. It
packages reviewed and published workspace knowledge as a stable JSON artifact.

## Route

```http
GET /workspaces/{workspace_id}/context-bundle
```

Any active workspace member may fetch the current bundle. Future persisted
snapshot publishing remains restricted to owner/manager roles.

## Contract

```json
{
  "schema_version": "context_bundle.v1",
  "context_version": "ctx_d4f5a6b7c8e9",
  "workspace_id": "5f7c6e4d-0000-4000-9000-000000000001",
  "generated_at": "2026-05-24T12:00:00Z",
  "sources": [],
  "facts": [],
  "rules": [],
  "evidence": [],
  "readiness": {
    "status": "ready",
    "score": 100,
    "blocking_reasons": [],
    "warnings": []
  },
  "integrity": {
    "bundle_hash": "sha256 hex",
    "canonicalization": "json.sort_keys.compact.v1",
    "source_count": 0,
    "fact_count": 0,
    "rule_count": 0,
    "evidence_count": 0
  }
}
```

## Source Shape

Sources use the real `sources` schema:

```json
{
  "id": "uuid",
  "title": "Tabela de precos",
  "original_filename": "precos.pdf",
  "type": "upload",
  "source_reliability": "high",
  "authority_level": "official",
  "status": "published",
  "created_at": "2026-05-24T11:00:00Z",
  "updated_at": "2026-05-24T11:30:00Z"
}
```

## Data Rules

The bundle reads active knowledge only from:

- `published_sources`;
- `published_facts`;
- `published_rules`;
- evidence spans referenced by selected facts/rules.

The bundle uses `unknown_facts_queue` and `contradictions` only to compute
readiness. Draft records never become active bundle knowledge.

## Readiness

Statuses:

| Status | Import behavior |
|--------|-----------------|
| `ready` | Consumer may import as active context. |
| `warning` | Consumer may import but should surface warnings. |
| `blocked` | Consumer must not activate as active context. |

Blocking reasons:

- `no_published_sources`
- `no_published_records`
- `open_unknown_items`
- `blocking_contradictions`
- `published_record_missing_source`
- `published_record_missing_provenance`

Warnings:

- `published_record_missing_evidence`
- `low_confidence_record`

## Audit

Every successful export writes `audit_logs.action = 'context_bundle.export'`.
Because v1 has no persisted snapshot row, `audit_logs.resource_id` stays null
and `context_version` is stored in metadata.

## Security Exclusions

The bundle must not include secrets, bearer tokens, signed URLs, local file
paths, raw prompts, raw provider responses, stack traces, unpublished facts or
rules, deleted source content, or raw unknown queue content.

## Focused Gate

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_bundle.py tests\api\test_knowledge.py tests\integrity -q
uv run --cache-dir .uv-cache ruff check apps\api tests\api
```
