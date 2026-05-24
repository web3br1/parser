# Context Bundle Cross-Repo Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split responsibility cleanly: the upstream Parser project produces trusted `context_bundle.v1`; the runtime chatbot app imports, validates, indexes, tests and publishes that context.

**Architecture:** Contract-first integration. Parser owns raw document processing, human validation, facts/rules/evidence/readiness and deterministic export. The runtime app owns schema/hash validation, secure import, RAG/Graph population, context tests, publish/rollback and chat usage. A shared golden bundle proves compatibility between both repos.

**Tech Stack:** Upstream Parser uses Python/FastAPI/Pydantic/Supabase-style contracts. Runtime app uses TypeScript/Fastify/SQLite/sqlite-vec/Kuzu/Ollama/console UI. Shared artifacts are JSON Schema, golden JSON fixtures and compatibility tests.

---

## Ownership Boundary

| Capability | Upstream Parser | Runtime App |
|------------|-----------------|-------------|
| Raw PDFs, DOCX, XLSX, CSV, TXT parsing | Owns | Does not own |
| OCR and heavy extraction | Owns later | Does not own |
| Facts, rules, evidence spans | Produces | Imports and uses |
| Human review and approval | Owns | Shows imported status only |
| Unknowns, gaps, contradictions | Detects and exports summaries | Blocks/warns publish based on readiness |
| `context_bundle.v1` hash | Produces | Verifies |
| RAG and Graph RAG runtime | Does not own | Owns |
| Tool calling and chat | Does not own | Owns |
| Context tests | Generates expected tests | Executes in runtime |
| Console publish to active bot | Does not own | Owns |

## Canonical Flow

```text
Parser upstream
  raw docs -> quality gate -> extraction -> human review
  -> facts/rules/evidence/gaps/tests/readiness
  -> context_bundle.v1

Runtime app
  context_bundle.v1 -> schema/hash/security/readiness validation
  -> RAG import -> Graph import -> context tests
  -> human publish -> active chatbot context
```

## Contract Shape

The shared `context_bundle.v1` profile must include:

- `schema_version`
- `context_version`
- `workspace_id`
- `generated_at`
- `identity`
- `sources`
- `facts`
- `rules`
- `evidence`
- `gaps`
- `tests`
- `memory_policy`
- `tool_recommendations`
- `readiness`
- `integrity.bundle_hash`

Security exclusions are non-negotiable:

- no provider secrets;
- no bearer tokens;
- no signed URLs;
- no private local filesystem paths;
- no raw prompts;
- no raw provider responses;
- no stack traces;
- no unpublished facts/rules;
- no raw unknown queue content.

## Planned File Map

### Upstream Parser Repo

- Modify: `apps/api/src/context_builder/schemas/context_bundle.py`
  Adds the complete export schema for `identity`, `gaps`, `tests`,
  `memory_policy` and `tool_recommendations`.
- Modify: `apps/api/src/context_builder/services/context_bundle.py`
  Populates the new fields from reviewed/published state and keeps redaction.
- Modify: `docs/03-pipeline/CONTEXT_BUNDLE.md`
  Documents the complete contract and import expectations.
- Create: `examples/context_bundle/golden-context-bundle.v1.json`
  Golden fixture shared with the runtime app.
- Create: `examples/context_bundle/blocked-context-bundle.v1.json`
  Fixture with `readiness.status = "blocked"`.
- Modify: `tests/api/test_context_bundle.py`
  Covers the complete payload, redaction and deterministic hash.
- Create: `tests/compat/test_context_bundle_golden.py`
  Ensures fixture and live schema stay compatible.

### Runtime App Repo

Use the runtime repo's existing folder conventions. If names differ, preserve the
responsibilities below and keep the same test coverage.

- Create: `src/domain/context-bundle/context-bundle.schema.ts`
  Runtime JSON Schema/type definitions for `context_bundle.v1`.
- Create: `src/domain/context-bundle/context-bundle-security.ts`
  Secret/path/prompt/stack-trace detection for imported bundles.
- Create: `src/application/context/import-context-bundle.ts`
  Main `ImportContextBundle` use case.
- Create: `src/application/context/publish-context-version.ts`
  Applies an approved import to the active bot config.
- Create: `src/application/context/run-context-tests.ts`
  Executes imported context tests against the runtime chat/RAG stack.
- Create: `src/adapters/context-bundle/context-bundle-file-adapter.ts`
  Reads uploaded/local bundle JSON safely.
- Create: `src/adapters/rag/context-bundle-rag-importer.ts`
  Converts sources/evidence into citeable RAG chunks.
- Create: `src/adapters/graph/context-bundle-graph-importer.ts`
  Converts facts/rules into Kuzu nodes/edges.
- Create: `src/http/routes/context-bundle-routes.ts`
  Adds validate/import/publish endpoints.
- Create: `src/console/context-import/ContextImportTab.tsx`
  Console import, preview, readiness, tests and publish UI.
- Create: `tests/fixtures/context-bundle/golden-context-bundle.v1.json`
  Copy of the upstream golden fixture.
- Create: `tests/context-bundle/*.test.ts`
  Unit and integration tests for validation/import/publish.

---

## Epic A: Contract `context_bundle.v1`

**Objective:** Both repos agree on the complete JSON contract before runtime import mutates anything.

### Task A1: Upstream complete schema

**Files:**
- Modify: `apps/api/src/context_builder/schemas/context_bundle.py`
- Test: `tests/api/test_context_bundle.py`

- [ ] Add schema models for `identity`, `gaps`, `tests`, `memory_policy` and `tool_recommendations`.
- [ ] Require `schema_version = "context_bundle.v1"`.
- [ ] Keep `integrity.bundle_hash` deterministic over canonical JSON excluding the hash field itself.
- [ ] Add tests proving a bundle with the complete profile validates.
- [ ] Add tests proving sensitive fields are rejected or redacted before hashing.
- [ ] Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_bundle.py -q
uv run --cache-dir .uv-cache ruff check apps\api\src\context_builder tests\api\test_context_bundle.py
```

### Task A2: Shared golden fixtures

**Files:**
- Create: `examples/context_bundle/golden-context-bundle.v1.json`
- Create: `examples/context_bundle/blocked-context-bundle.v1.json`
- Create: `tests/compat/test_context_bundle_golden.py`

- [ ] Create a ready golden bundle with one source, one fact, one rule, one evidence span, one passing context test and one tool recommendation.
- [ ] Create a blocked bundle with `open_unknown_items` in `readiness.blocking_reasons`.
- [ ] Test both fixtures against the upstream schema.
- [ ] Test the ready fixture's `bundle_hash` against the canonicalization function.
- [ ] Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\compat\test_context_bundle_golden.py tests\api\test_context_bundle.py -q
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

### Task A3: Runtime validator-only slice

**Files:**
- Create: `src/domain/context-bundle/context-bundle.schema.ts`
- Create: `src/domain/context-bundle/context-bundle-validator.ts`
- Test: `tests/context-bundle/context-bundle-validator.test.ts`

- [ ] Implement schema validation for the shared fixture without writing to repositories.
- [ ] Accept the ready golden fixture.
- [ ] Reject unsupported `schema_version`.
- [ ] Reject missing `integrity.bundle_hash`.
- [ ] Reject malformed readiness status.
- [ ] Run:

```bash
npm run typecheck
npm run test -- tests/context-bundle/context-bundle-validator.test.ts
```

## Epic B: Secure Importer

**Objective:** Invalid or unsafe bundles never enter the runtime.

### Task B1: Runtime hash verification

**Files:**
- Create: `src/domain/context-bundle/context-bundle-hash.ts`
- Modify: `src/domain/context-bundle/context-bundle-validator.ts`
- Test: `tests/context-bundle/context-bundle-hash.test.ts`

- [ ] Implement canonical JSON hashing compatible with the upstream Parser.
- [ ] Verify the golden fixture hash.
- [ ] Fail when a fact payload changes after export.
- [ ] Fail when evidence text changes after export.
- [ ] Run:

```bash
npm run test -- tests/context-bundle/context-bundle-hash.test.ts
```

### Task B2: Runtime security scanner

**Files:**
- Create: `src/domain/context-bundle/context-bundle-security.ts`
- Test: `tests/context-bundle/context-bundle-security.test.ts`

- [ ] Detect bearer tokens.
- [ ] Detect common API secret assignments.
- [ ] Detect signed URL query fields.
- [ ] Detect Windows and Unix private local paths.
- [ ] Detect `raw_prompt`, `provider_response` and stack-trace markers.
- [ ] Return safe findings without echoing the secret value.
- [ ] Run:

```bash
npm run test -- tests/context-bundle/context-bundle-security.test.ts
```

### Task B3: Import report without mutation

**Files:**
- Create: `src/application/context/import-context-bundle.ts`
- Test: `tests/context-bundle/import-context-bundle.test.ts`

- [ ] Add `dryRun: true` behavior as the default path.
- [ ] Return counts for sources, facts, rules, evidence, gaps and tests.
- [ ] Return readiness status and blocking reasons.
- [ ] Reject `readiness.status = "blocked"` unless caller explicitly requests diagnostic import.
- [ ] Prove no repository write occurs during dry run.
- [ ] Run:

```bash
npm run test -- tests/context-bundle/import-context-bundle.test.ts
```

## Epic C: Import To RAG

**Objective:** Imported evidence becomes citeable runtime knowledge.

### Task C1: Evidence chunk mapping

**Files:**
- Create: `src/adapters/rag/context-bundle-rag-importer.ts`
- Test: `tests/context-bundle/context-bundle-rag-importer.test.ts`

- [ ] Convert each evidence span into a chunk with source id, evidence id, context version and authority metadata.
- [ ] Preserve source title and original filename when safe.
- [ ] Do not index unpublished or unreferenced evidence.
- [ ] Return imported chunk ids in the import report.
- [ ] Run:

```bash
npm run test -- tests/context-bundle/context-bundle-rag-importer.test.ts
```

### Task C2: Chat citation path

**Files:**
- Modify: existing RAG search result mapper.
- Modify: chat preview response mapping.
- Test: `tests/context-bundle/context-bundle-chat-citations.test.ts`

- [ ] Ensure `search_knowledge` can return evidence/source metadata from imported chunks.
- [ ] Ensure chat preview can display source/evidence references.
- [ ] Add a test where a question retrieves the imported golden evidence.
- [ ] Run:

```bash
npm run test -- tests/context-bundle/context-bundle-chat-citations.test.ts
```

## Epic D: Import To Graph RAG

**Objective:** Facts and rules populate Kuzu with traceable nodes and edges.

### Task D1: Fact and rule graph mapping

**Files:**
- Create: `src/adapters/graph/context-bundle-graph-importer.ts`
- Test: `tests/context-bundle/context-bundle-graph-importer.test.ts`

- [ ] Map facts into typed nodes with `context_version`, `source_id` and `evidence_span_id`.
- [ ] Map rules into policy/condition/action structures.
- [ ] Preserve enough metadata for `query_graph` to return provenance.
- [ ] Skip unsupported fact types with warning, not crash.
- [ ] Run:

```bash
npm run test -- tests/context-bundle/context-bundle-graph-importer.test.ts
```

### Task D2: Graph query smoke

**Files:**
- Test: `tests/context-bundle/context-bundle-query-graph.test.ts`

- [ ] Import the golden bundle into an isolated graph store.
- [ ] Query the imported service, policy or price fact.
- [ ] Assert the result includes source/evidence refs.
- [ ] Run:

```bash
npm run test -- tests/context-bundle/context-bundle-query-graph.test.ts
```

## Epic E: Readiness And Context Tests

**Objective:** The runtime proves the imported context works before publish.

### Task E1: Context test runner

**Files:**
- Create: `src/application/context/run-context-tests.ts`
- Test: `tests/context-bundle/run-context-tests.test.ts`

- [ ] Execute imported tests against the runtime chat/RAG path.
- [ ] Compare expected behavior, required sources and forbidden behavior.
- [ ] Mark each test as `passed`, `failed` or `blocked`.
- [ ] Fail publish when any critical test fails.
- [ ] Run:

```bash
npm run test -- tests/context-bundle/run-context-tests.test.ts
```

### Task E2: Readiness scorecard

**Files:**
- Create: `src/application/context/context-readiness-scorecard.ts`
- Test: `tests/context-bundle/context-readiness-scorecard.test.ts`

- [ ] Combine upstream readiness with runtime import status.
- [ ] Include RAG import, graph import and context test results.
- [ ] Return a safe UI-facing summary.
- [ ] Run:

```bash
npm run test -- tests/context-bundle/context-readiness-scorecard.test.ts
```

## Epic F: Console Import UI

**Objective:** Operators import and review a bundle without touching raw JSON.

### Task F1: Import tab skeleton

**Files:**
- Create: `src/console/context-import/ContextImportTab.tsx`
- Modify: existing console tab registration.
- Test: `tests/e2e/context-import-tab.e2e.ts`

- [ ] Add a `Context Import` tab.
- [ ] Add bundle file selection or paste area.
- [ ] Show schema version, context version, readiness and counts after dry run.
- [ ] Hide raw JSON by default.
- [ ] Run:

```bash
npm run test:e2e -- tests/e2e/context-import-tab.e2e.ts
```

### Task F2: Preview facts, rules, gaps and tests

**Files:**
- Modify: `src/console/context-import/ContextImportTab.tsx`
- Test: `tests/e2e/context-import-preview.e2e.ts`

- [ ] Show sources, facts, rules, gaps and tests in separate review surfaces.
- [ ] Show evidence refs without exposing private paths or signed URLs.
- [ ] Show blocking reasons before publish controls.
- [ ] Run:

```bash
npm run test:e2e -- tests/e2e/context-import-preview.e2e.ts
```

## Epic G: Publish To Runtime

**Objective:** Approved context becomes the active bot context with rollback.

### Task G1: Publish context version

**Files:**
- Create: `src/application/context/publish-context-version.ts`
- Modify: bot config repository as needed.
- Test: `tests/context-bundle/publish-context-version.test.ts`

- [ ] Apply identity to bot config.
- [ ] Apply memory policy.
- [ ] Enable recommended tools only after local policy accepts them.
- [ ] Mark imported RAG and graph records as active for this context version.
- [ ] Record previous active context version for rollback.
- [ ] Run:

```bash
npm run test -- tests/context-bundle/publish-context-version.test.ts
```

### Task G2: Rollback context version

**Files:**
- Create: `src/application/context/rollback-context-version.ts`
- Test: `tests/context-bundle/rollback-context-version.test.ts`

- [ ] Restore previous active context version.
- [ ] Ensure chat uses the restored RAG/Graph records.
- [ ] Ensure imported inactive records remain stored but not active.
- [ ] Run:

```bash
npm run test -- tests/context-bundle/rollback-context-version.test.ts
```

## Epic H: Cross-Repo Compatibility

**Objective:** A bundle exported by Parser imports into the runtime app without manual edits.

### Task H1: Fixture synchronization

**Files:**
- Upstream: `examples/context_bundle/golden-context-bundle.v1.json`
- Runtime: `tests/fixtures/context-bundle/golden-context-bundle.v1.json`
- Runtime test: `tests/context-bundle/upstream-golden-compat.test.ts`

- [ ] Copy the upstream golden fixture into the runtime app.
- [ ] Validate schema/hash/security.
- [ ] Dry-run import.
- [ ] Import to RAG and Graph in an isolated test database.
- [ ] Run imported context tests.
- [ ] Run:

```bash
npm run test -- tests/context-bundle/upstream-golden-compat.test.ts
```

### Task H2: End-to-end handoff script

**Files:**
- Upstream: `scripts/context_bundle/export_golden_bundle.py`
- Runtime: `scripts/context-bundle/import-golden-bundle.mjs`
- Docs: `docs/integration/context-bundle-cross-repo.md`

- [ ] Add an upstream script that exports a deterministic golden bundle.
- [ ] Add a runtime script that imports that bundle in dry-run mode.
- [ ] Document the handoff command sequence.
- [ ] Run both repos' compatibility commands in order.
- [ ] Expected result: no manual JSON edits between export and import.

## Recommended SDD Execution Order

1. Epic A: Contract and fixtures.
2. Epic B: Validator, hash and security.
3. Epic C: RAG import with citations.
4. Epic D: Graph import.
5. Epic E: Context tests and readiness.
6. Epic F: Console import UI.
7. Epic G: Publish and rollback.
8. Epic H: Cross-repo compatibility.

## Release Gates

### Upstream Parser

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_bundle.py tests\compat -q
uv run --cache-dir .uv-cache python scripts\context_bundle\export_golden_bundle.py --check
uv run --cache-dir .uv-cache ruff check apps\api tests\api tests\compat
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

### Runtime App

```bash
npm run typecheck
npm run test
npm run test:e2e
npm run gate:generic-release
```

### Cross-Repo

```text
1. Upstream exports golden `context_bundle.v1`.
2. Runtime validates schema/hash/security.
3. Runtime dry-run import returns safe report.
4. Runtime imports to RAG and Graph.
5. Runtime context tests pass.
6. Runtime publishes the context version.
7. Runtime chat preview cites imported evidence.
```

## Definition Of Done

- Parser can export a complete, deterministic, sanitized `context_bundle.v1`.
- Runtime app rejects malformed, tampered, blocked or unsafe bundles.
- Runtime app imports a ready bundle into RAG with visible citations.
- Runtime app imports facts/rules into Graph RAG with provenance.
- Runtime app executes imported context tests before publish.
- Console shows readiness, gaps, facts, rules, tests and publish status.
- Active bot config records the active `context_version`.
- Rollback restores the previous active context version.
- A Parser-generated golden bundle imports into the runtime app without manual adjustment.
