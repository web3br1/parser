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

## Source Pack Compiler

The filesystem compiler is the upstream path for normalized upload packages.
It is separate from the Supabase-backed route above and compiles a source pack
folder directly into the same `ContextBundleResponse` contract.

Canonical command:

```powershell
uv run --cache-dir .uv-cache python scripts\source_pack\compile_context_bundle.py C:\tmp\context-builder-sources\compounding-pharmacy-gold
```

The compiler first identifies a complete source pack by reading
`00_source_manifest.md`. It then registers numbered files as published sources,
extracts CSV row and Markdown section evidence, builds facts, rules, gaps,
tests, memory policy and tool recommendations, sanitizes forbidden payloads and
computes the same `integrity.bundle_hash` format used by the API exporter.

For the current gold pack, the compiler reports 64 numbered source files plus
manifest and README. `README.md` is package documentation, not active bundle
knowledge.

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
  "identity": {
    "workspace_name": null,
    "summary": null,
    "attributes": {}
  },
  "gaps": [],
  "tests": [],
  "memory_policy": {
    "retention": null,
    "allowed": [],
    "denied": [],
    "notes": null
  },
  "tool_recommendations": [],
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
    "evidence_count": 0,
    "gap_count": 0,
    "test_count": 0,
    "tool_recommendation_count": 0
  }
}
```

## Hash And Versioning

`integrity.bundle_hash` is a SHA-256 hex digest computed with
`json.sort_keys.compact.v1`. The hash payload is the public bundle payload that
an importer receives, except `generated_at` is replaced by
`stable-for-hash`.

The hash includes:

- `schema_version`
- `workspace_id`
- `sources`
- `facts`
- `rules`
- `evidence`
- `identity`
- `gaps`
- `tests`
- `memory_policy`
- `tool_recommendations`
- `readiness`

It does not include `integrity` or `context_version`. `context_version` is
derived from the hash as `ctx_{first_12_hex_chars}`.

This means a consumer runtime can validate bundle integrity from the exported
JSON alone, without access to internal database rows.

## Upstream Sections

The v1 contract also carries optional upstream sections:

- `identity`: workspace identity and public operating attributes.
- `gaps`: known missing or unresolved context items.
- `tests`: contract/runtime checks produced upstream.
- `memory_policy`: import guidance for what memory may retain or deny.
- `tool_recommendations`: tools the consumer runtime may consider.

When upstream data is unavailable, these fields serialize as safe empty
defaults. They are included in `bundle_hash` and `context_version` after the
same sanitization pass used for bundle payloads.

The envelope and upstream sections are contract-shaped, not arbitrary extension
bags. Extra top-level fields and extra fields inside these objects are rejected
by the schema. Extensibility belongs in explicit safe maps such as
`identity.attributes`, `gap.details`, `test.assertion`, `test.details`, or
`tool_recommendation.inputs`. Those maps still pass through recursive key and
value sanitization before export and hash.

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

## Compatibility Fixtures

The canonical fixtures live in:

- `examples/context_bundle/context-bundle.v1.schema.json`
- `examples/context_bundle/golden-context-bundle.v1.json`
- `examples/context_bundle/blocked-context-bundle.v1.json`
- `examples/context_bundle/context-bundle-contract.v1.manifest.json`

They are generated and checked by:

```powershell
uv run --cache-dir .uv-cache python scripts\context_bundle\export_json_schema.py --check
uv run --cache-dir .uv-cache python scripts\context_bundle\export_golden_bundle.py --check
uv run --cache-dir .uv-cache python scripts\context_bundle\export_contract_manifest.py --check
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

The golden fixture is a ready bundle that should pass importer validation and
can be used for runtime handoff tests. The blocked fixture contains an open gap
and `readiness.status = "blocked"`, so a consumer may preview it but must not
activate it.

The contract manifest is an index of the schema and fixture artifacts. It is
outside the bundle payload and is not included in `integrity.bundle_hash`. It
records normalized artifact hashes, required top-level fields, activation
policy and the compatibility commands a runtime should mirror. The manifest
proves artifact consistency only when it comes from a trusted commit, tag,
pinned digest or signed release; it is not a standalone root of trust.

Manifest `checks.command` values are documentation for allowlisted CI jobs. A
consumer must not execute arbitrary commands from a received manifest.

Consumer projects should validate at least:

- manifest hashes before copying schema or fixture artifacts;
- schema version and strict envelope fields;
- `integrity.bundle_hash` from the public payload;
- `context_version` prefix from the hash;
- integrity counts against actual array lengths;
- readiness activation rules;
- absence of secrets, local paths, raw prompts, provider responses, and stack
  traces.

## Security Exclusions

The bundle must not include secrets, bearer tokens, signed URLs, local file
paths, raw prompts, raw provider responses, stack traces, unpublished facts or
rules, deleted source content, or raw unknown queue content.

## Focused Gate

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_bundle.py tests\compat\test_context_bundle_golden.py tests\compat\test_context_bundle_manifest_export.py tests\api\test_knowledge.py tests\integrity -q
uv run --cache-dir .uv-cache python scripts\context_bundle\export_json_schema.py --check
uv run --cache-dir .uv-cache python scripts\context_bundle\export_golden_bundle.py --check
uv run --cache-dir .uv-cache python scripts\context_bundle\export_contract_manifest.py --check
uv run --cache-dir .uv-cache ruff check apps\api tests\api tests\compat
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```
