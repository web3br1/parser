# Unified Context Build Wizard With AI Tutor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one guided Context Build flow that accepts a single document, loose multi-document batch, or source pack, detects the input automatically, tracks generation of `context_bundle.v1`, and provides a safe AI tutorial sidecar with allowlisted tool calls.

**Architecture:** Use Clean Architecture boundaries. Domain owns `ContextBuildRun` and state transitions. Application use cases detect input, create runs, enqueue work, compile/export context and expose safe tutor tools. Backend detection/preflight is the source of truth. The frontend may render an optimistic preview, but it must always accept the backend decision before committing a build. Adapters implement Supabase persistence, storage, existing upload/ingest queues, source-pack preflight/compiler, and LLM/tool-calling. The frontend Wizard is deterministic; the AI tutor explains and invokes restricted tools but never publishes operational truth without human confirmation.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Supabase/Postgres migrations, existing worker/job pipeline, Next.js App Router, React/TypeScript, existing console primitives, pytest, ruff, mypy, frontend typecheck and smoke scripts.

---

## Product Decision

There must not be a separate "source pack wizard". The user should see one flow:

```text
New Context Build
  -> upload file(s), folder, or zip
  -> app detects input mode
  -> app chooses the correct pipeline
  -> operator reviews progress and blockers
  -> app exports or prepares context_bundle.v1
```

`source_pack` is an internal input mode, not a separate user journey.

## Review Fixes Incorporated

This plan explicitly incorporates the review findings from 2026-05-26:

- backend detection is authoritative; frontend detection is only a preview;
- `compile_context_bundle_after_confirmation` is either implemented and tested or removed from the MVP tool list. This plan implements and tests it;
- migration numbering must be verified before writing SQL. Current repository state has latest migration `046_source_pack_import_runs.sql`, so `047_context_build_runs.sql` is correct at plan time;
- `updated_at` requires `public.touch_updated_at()` trigger;
- indexes are specified in the SQL contract and integrity tests;
- `input_hash` is nullable until real content is staged/uploaded, while `input_fingerprint` is always present for pre-upload correlation;
- `context_build_runs` is the canonical lifecycle table for new flows; `source_pack_import_runs` remains compatibility-only;
- compile/complete/fail use cases are implemented before API/tutor compile actions;
- tasks touching `main.py` are sequenced and must not run in parallel.

## Clean Architecture Map

### Domain

Create stable domain vocabulary:

- `ContextBuildRun`
- `ContextBuildInput`
- `ContextBuildArtifact`
- `ContextBuildStep`
- `ContextBuildMode`
- `ContextBuildStatus`
- `ContextBuildRecommendedAction`
- `TutorToolCall`
- `TutorConfirmation`

The domain must not import FastAPI, Supabase, browser APIs, React, or concrete model gateways.

### Application / Use Cases

Use cases own orchestration:

- `DetectContextBuildInput`
- `PreflightContextBuildRun`
- `CreateContextBuildRun`
- `QueueContextBuildRun`
- `CompileContextBuildRun`
- `GetContextBuildRun`
- `ListContextBuildRuns`
- `CompleteContextBuildRun`
- `FailContextBuildRun`
- `ExportContextBundleForRun`
- `ExplainContextBuildState`
- `InvokeTutorTool`

### Adapters

Adapters connect to current infrastructure:

- Supabase repository for `context_build_runs`
- storage adapter using existing storage service
- upload adapter wrapping current `/sources/upload` behavior
- source-pack inspector using `inspect_source_pack_upload`
- source-pack compiler using `packages/source_pack`
- context bundle exporter using `context_bundle_service`
- tutorial LLM adapter with allowlisted tool registry

### Interface

Backend routes:

- `POST /workspaces/{workspace_id}/context-build-runs/preflight`
- `POST /workspaces/{workspace_id}/context-build-runs`
- `GET /workspaces/{workspace_id}/context-build-runs`
- `GET /workspaces/{workspace_id}/context-build-runs/{run_id}`
- `POST /workspaces/{workspace_id}/context-build-runs/{run_id}/actions/compile`
- `POST /workspaces/{workspace_id}/tutorial/messages`
- `POST /workspaces/{workspace_id}/tutorial/tool-confirmations`

Frontend route:

- `/workspaces/{workspaceId}/context-build`

## Data Model

Add migration `047_context_build_runs.sql`.

Before creating the migration, verify the current latest migration:

```powershell
Get-ChildItem supabase\migrations | Sort-Object Name | Select-Object -Last 1 -ExpandProperty Name
```

Expected at plan time:

```text
046_source_pack_import_runs.sql
```

If the latest migration is no longer `046`, stop and renumber this task before editing files.

Do not delete `source_pack_import_runs` in this task. Keep it as historical/specialized compatibility. `context_build_runs` is canonical for all new flows. The existing source-pack preflight route must remain compatible, but when it persists a run it should also create or link a canonical `context_build_runs` row. Later migration can backfill/deprecate `source_pack_import_runs`.

Minimum table:

```sql
create table public.context_build_runs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  actor_user_id uuid references auth.users(id) on delete set null,

  input_mode text not null check (input_mode in (
    'single_document',
    'multi_document_batch',
    'source_pack'
  )),
  status text not null check (status in (
    'created',
    'preflighted',
    'queued',
    'processing',
    'needs_review',
    'ready_to_export',
    'compiled',
    'rejected',
    'failed'
  )),
  recommended_action text not null check (recommended_action in (
    'normal_ingest',
    'batch_ingest',
    'compile_as_source_pack',
    'reject'
  )),

  input_fingerprint text not null,
  input_hash text,
  source_dir text,
  source_pack_id text,
  source_pack_version text,
  staged_upload_id text,

  source_count integer not null default 0 check (source_count >= 0),
  job_count integer not null default 0 check (job_count >= 0),

  bundle_hash text,
  context_version text,
  output_path text,
  readiness_status text check (
    readiness_status is null or readiness_status in ('ready', 'warning', 'blocked')
  ),
  readiness_score integer check (
    readiness_score is null or (readiness_score >= 0 and readiness_score <= 100)
  ),

  file_counts jsonb not null default '{}'::jsonb,
  missing_files jsonb not null default '[]'::jsonb,
  extra_files jsonb not null default '[]'::jsonb,
  steps jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  errors jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_context_build_runs_workspace_created_at
on public.context_build_runs(workspace_id, created_at desc);

create index idx_context_build_runs_workspace_status
on public.context_build_runs(workspace_id, status);

create index idx_context_build_runs_workspace_input_mode
on public.context_build_runs(workspace_id, input_mode);

create index idx_context_build_runs_workspace_input_fingerprint
on public.context_build_runs(workspace_id, input_fingerprint);

create index idx_context_build_runs_workspace_input_hash
on public.context_build_runs(workspace_id, input_hash);

create index idx_context_build_runs_source_pack
on public.context_build_runs(workspace_id, source_pack_id, source_pack_version);

create trigger trg_context_build_runs_updated_at
before update on public.context_build_runs
for each row execute function public.touch_updated_at();
```

`input_fingerprint` is a stable pre-upload correlation key computed from metadata such as relative paths, names, sizes and last-modified values. `input_hash` is the content hash and may be null until upload/staging completes. Source-dir server preflight may fill both when content is available.

Access model:

- backend-owned table;
- `alter table ... enable row level security`;
- `revoke all ... from anon, authenticated`;
- `grant all ... to service_role`;
- all access through API routes with membership checks.

Later, if the console needs direct Supabase reads, add explicit `grant select` and live RLS policies in a separate migration. Do not mix dead policies with backend-only grants.

## Wizard UX

Add `Context Build` to workspace navigation before `Sources`.

Wizard steps:

```text
Select input
-> Detect
-> Preflight
-> Build
-> Review / Publish
-> Generate Bundle
-> Ready / Warning / Blocked
```

Input modes:

| Mode | Detection | Pipeline |
|---|---|---|
| `single_document` | one supported file, no manifest | current upload/ingest/review/publish/export |
| `multi_document_batch` | multiple supported files, no manifest | repeated upload/ingest with one build run |
| `source_pack` | `00_source_manifest.md` or numbered manifest structure | source-pack preflight/compile/export |

The backend preflight response is authoritative. Frontend detection can only label the selected input as `single_file_preview`, `loose_batch_preview`, `source_pack_candidate_preview` or `invalid_preview`. The Wizard must replace preview labels with backend `input_mode` and `recommended_action` after preflight.

The Wizard must keep `Sources` as history/inventory. Do not turn `SourcesPage` into the Wizard.

## AI Tutor UX

The tutor is a sidecar, not the owner of the flow.

Allowed behavior:

- explain current step;
- summarize build state;
- call read-only tools;
- prepare mutating actions for confirmation;
- execute explicitly confirmed safe tools;
- navigate the operator to relevant screens.

Forbidden behavior:

- approve/reject facts;
- publish facts/rules;
- edit operational rules;
- delete sources/workspaces;
- change permissions;
- call shell commands;
- expose arbitrary API/MCP surface;
- claim production readiness beyond system readiness.

MVP tutor tools:

```text
explain_context_build_state
detect_input_mode
run_context_build_preflight
get_context_build_run_status
draft_compile_plan
request_compile_confirmation
compile_context_bundle_after_confirmation
open_relevant_screen
query_published_knowledge
```

`compile_context_bundle_after_confirmation` is an MVP tool in this plan. It must call the same backend use case as `POST /context-build-runs/{run_id}/actions/compile`; it cannot shell out directly and cannot compile without a stored confirmation token.

Mutating tools require confirmation with:

- target workspace;
- target run id;
- exact action;
- expected side effects;
- rollback/next step if available.

## Multi-Agent Execution Plan

Use SDD with separate agents:

| Agent | Owns | Write Scope |
|---|---|---|
| Domain Agent | domain models and state transitions | `packages/domain`, domain tests |
| DB Agent | migration and integrity tests | `supabase/migrations`, `tests/integrity` |
| API Agent | schemas, repository, use cases, router | `apps/api/src/context_builder`, `tests/api` |
| Frontend Agent | Wizard route/components/detection tests | `apps/web/src`, frontend smoke |
| Tutor Agent | tutorial schemas/tools/service, sidecar UI | `apps/api`, `apps/web/src/components/tutorial-*` |
| Security Reviewer | tool allowlist, confirmation gates, RLS/grants | read-only review, then targeted fixes |
| Controller | integration, gates, commits | full repo |

Do not dispatch two agents to edit the same files in parallel.

Sequencing constraints:

- Task 5 must finish before Task 9 because both register routers in `apps/api/src/context_builder/main.py`.
- Task 7 must finish before Task 10 because both touch `apps/web/src/components/workspace-shell.tsx`.
- Task 8 must finish before Task 9 if tutor tools call context-build API endpoints.

## Task 1: Domain Contract

**Files:**

- Modify: `packages/domain/src/domain/models.py`
- Test: `packages/domain/tests/test_context_build_models.py`

- [ ] **Step 1: Write failing domain tests**

Test:

```python
from domain.models import ContextBuildRun, ContextBuildStatus


def test_context_build_run_can_transition_to_preflighted() -> None:
    run = ContextBuildRun.create(
        id="run_1",
        workspace_id="ws_1",
        actor_user_id="user_1",
        input_mode="source_pack",
        input_fingerprint="fingerprint:abc",
    )

    updated = run.mark_preflighted(
        recommended_action=ContextBuildRecommendedAction.COMPILE_AS_SOURCE_PACK
    )

    assert updated.status == ContextBuildStatus.PREFLIGHTED
    assert updated.recommended_action == ContextBuildRecommendedAction.COMPILE_AS_SOURCE_PACK
```

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\domain\tests\test_context_build_models.py -q
```

Expected: FAIL because `ContextBuildRun` does not exist.

- [ ] **Step 2: Implement minimal domain model**

Add dataclass/enums only. No DB/FastAPI imports. Domain tests must use enums, not raw strings, for status and recommended action.

- [ ] **Step 3: Run GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\domain\tests\test_context_build_models.py -q
uv run --cache-dir .uv-cache ruff check packages\domain
```

Expected: PASS.

## Task 2: Migration 047

**Files:**

- Create: `supabase/migrations/047_context_build_runs.sql`
- Create: `tests/integrity/test_context_build_runs_migration.py`
- Modify: `docs/04-data/DATA_MODEL.md`

- [ ] **Step 1: Write failing integrity tests**

First verify migration numbering:

```powershell
Get-ChildItem supabase\migrations | Sort-Object Name | Select-Object -Last 1 -ExpandProperty Name
```

Expected: `046_source_pack_import_runs.sql`.

Then write tests that assert table exists, modes/statuses/actions are present, `input_fingerprint text not null` exists, `input_hash text` exists and is nullable, `public.touch_updated_at()` trigger exists, RLS is enabled, grants are backend-owned, all indexes named in this plan exist, and no dead `create policy` exists.

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\integrity\test_context_build_runs_migration.py -q
```

Expected: FAIL because migration does not exist.

- [ ] **Step 2: Add migration**

Use the SQL contract in this plan.

- [ ] **Step 3: Run GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\integrity\test_context_build_runs_migration.py -q
uv run --cache-dir .uv-cache ruff check tests\integrity\test_context_build_runs_migration.py
```

Expected: PASS.

## Task 3: API Schemas And Repository

**Files:**

- Create: `apps/api/src/context_builder/schemas/context_build_run.py`
- Create: `apps/api/src/context_builder/adapters/supabase_context_build_runs.py`
- Create: `tests/api/test_context_build_runs_repository.py`

- [ ] **Step 1: Write failing schema/repository tests**

Cover:

- create payload validates all three modes;
- invalid mode fails;
- `input_fingerprint` is required;
- `input_hash` may be null before upload/staging;
- repository creates row in `context_build_runs`;
- repository lists only workspace rows;
- repository gets by `id` and `workspace_id`;
- repository updates status by `id` and `workspace_id`.

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_build_runs_repository.py -q
```

Expected: FAIL because modules do not exist.

- [ ] **Step 2: Implement schemas and repository adapter**

Repository uses Supabase fluent API. Keep the adapter thin and testable with fake DB.

Fake DB tests prove API shape and workspace filters. They do not prove Postgres
RLS, jsonb behavior, grants or real Supabase query semantics. Real Supabase
verification remains a smoke/readiness gate after implementation:

```powershell
uv run --cache-dir .uv-cache python scripts\smoke\run_real_smoke.py --target local --full --json-report .run\smoke-local-full.json
```

- [ ] **Step 3: Run GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_build_runs_repository.py -q
uv run --cache-dir .uv-cache ruff check apps\api\src\context_builder\schemas\context_build_run.py apps\api\src\context_builder\adapters\supabase_context_build_runs.py tests\api\test_context_build_runs_repository.py
```

Expected: PASS.

## Task 4: Context Build Preflight Use Case

**Files:**

- Create: `apps/api/src/context_builder/use_cases/context_build_runs.py`
- Create: `tests/api/test_context_build_preflight.py`

- [ ] **Step 1: Write failing tests for detection**

Cases:

- one file -> `single_document`, `normal_ingest`;
- multiple files no manifest -> `multi_document_batch`, `batch_ingest`;
- manifest complete -> `source_pack`, `compile_as_source_pack`;
- manifest incomplete -> `source_pack`, `reject`;
- empty input -> `reject`.
- preview metadata without content creates `input_fingerprint` but leaves `input_hash` null.

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_build_preflight.py -q
```

Expected: FAIL because use case does not exist.

- [ ] **Step 2: Implement use case**

Use pure input metadata where possible. For local source-pack path support, call existing `inspect_source_pack_upload`. This backend use case is the only authoritative detector. Frontend preview must not be treated as final classification.

Also implement:

- `CompileContextBuildRun`
- `CompleteContextBuildRun`
- `FailContextBuildRun`
- `ExportContextBundleForRun`

`CompileContextBuildRun` may initially support only `source_pack` runs and must return a clear unsupported-mode error for `single_document` and `multi_document_batch`.

- [ ] **Step 3: Run GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_build_preflight.py -q
uv run --cache-dir .uv-cache ruff check apps\api\src\context_builder\use_cases\context_build_runs.py tests\api\test_context_build_preflight.py
```

Expected: PASS.

## Task 5: Context Build API Router

**Files:**

- Create: `apps/api/src/context_builder/routers/context_build_runs.py`
- Modify: `apps/api/src/context_builder/main.py`
- Test: `tests/api/test_context_build_runs_api.py`

- [ ] **Step 1: Write failing route tests**

Cover:

- protected by membership;
- `POST /preflight` returns mode/action;
- `POST /preflight` with `persist=true` creates `context_build_runs`;
- `GET /context-build-runs` lists workspace runs;
- `GET /context-build-runs/{run_id}` filters workspace;
- `POST /context-build-runs/{run_id}/actions/compile` calls `CompileContextBuildRun`;
- compile action requires manager/owner role and workspace-scoped run id;
- source-pack legacy endpoint still works.

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_build_runs_api.py tests\api\test_source_pack_preflight.py -q
```

Expected: FAIL for new route.

- [ ] **Step 2: Implement router and register**

Register in `main.py` with:

```python
app.include_router(
    context_build_runs.router,
    prefix="/workspaces/{workspace_id}/context-build-runs",
    tags=["context-build-runs"],
)
```

- [ ] **Step 3: Run GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_build_runs_api.py tests\api\test_source_pack_preflight.py -q
uv run --cache-dir .uv-cache ruff check apps\api\src\context_builder\routers\context_build_runs.py apps\api\src\context_builder\main.py tests\api\test_context_build_runs_api.py
```

Expected: PASS.

## Task 6: Frontend Detection Library

**Files:**

- Create: `apps/web/src/lib/context-build.ts`
- Create: `apps/web/src/lib/context-build.test.ts`
- Create: `apps/web/scripts/test-context-build.mjs`

- [ ] **Step 1: Write failing pure TypeScript tests**

Cases:

- empty files -> invalid;
- one supported file -> `single_file_preview`;
- multiple supported files -> `loose_batch_preview`;
- manifest file present -> `source_pack_candidate_preview`;
- blocked extension -> invalid.

Run:

```powershell
node apps\web\scripts\test-context-build.mjs
```

Expected: FAIL because library does not exist.

- [ ] **Step 2: Implement library and test runner**

Use no React in the detection library. The library returns preview labels only; it must not expose canonical `ContextBuildMode` values.

- [ ] **Step 3: Run GREEN**

Run:

```powershell
node apps\web\scripts\test-context-build.mjs
corepack pnpm --filter @context-builder/web typecheck
```

Expected: PASS.

## Task 7: Frontend Wizard Route

**Files:**

- Create: `apps/web/src/app/workspaces/[workspaceId]/context-build/page.tsx`
- Create: `apps/web/src/components/context-build-wizard.tsx`
- Create: `apps/web/src/components/context-build-dropzone.tsx`
- Create: `apps/web/src/components/context-build-summary.tsx`
- Modify: `apps/web/src/components/workspace-shell.tsx`
- Modify: `apps/web/src/lib/api.ts`
- Modify: `scripts/smoke/frontend_console_smoke.mjs`

- [ ] **Step 1: Write failing smoke/type expectations**

Add `/workspaces/demo/context-build` to frontend smoke route list.

Run:

```powershell
corepack pnpm --filter @context-builder/web typecheck
```

Expected: typecheck fails until route/components exist.

Smoke is not a gate in this step because it requires a running dev server. Only update `scripts/smoke/frontend_console_smoke.mjs` route coverage here; run the smoke later when a server is explicitly running.

- [ ] **Step 2: Implement static Wizard**

UI requirements:

- first screen is the usable Wizard, not a landing page;
- left panel: dropzone and detected mode;
- right panel: stable stepper;
- support file, multiple files and folder selection;
- use existing console primitives;
- do not nest cards inside cards;
- no marketing hero.

- [ ] **Step 3: Run GREEN**

Run:

```powershell
corepack pnpm --filter @context-builder/web typecheck
corepack pnpm --filter @context-builder/web build
```

Expected: PASS.

## Task 8: Wizard API Integration

**Files:**

- Modify: `apps/web/src/components/context-build-wizard.tsx`
- Modify: `apps/web/src/lib/api.ts`
- Test: frontend typecheck and backend route tests.

- [ ] **Step 1: Integrate deterministic actions**

Behaviors:

- single file calls current `/sources/upload`;
- loose batch uploads sequentially with per-file progress;
- source pack candidate calls `/context-build-runs/preflight` when backend route exists;
- frontend replaces preview mode with backend `input_mode` and `recommended_action`;
- if browser-native source-pack staging is not implemented yet, UI says it needs backend staging and does not fake completion.

- [ ] **Step 2: Verify**

Run:

```powershell
corepack pnpm --filter @context-builder/web typecheck
uv run --cache-dir .uv-cache pytest tests\api\test_context_build_runs_api.py -q
```

Expected: PASS.

## Task 9: AI Tutor Backend

**Files:**

- Create: `apps/api/src/context_builder/schemas/tutorial.py`
- Create: `apps/api/src/context_builder/services/tutorial_tools.py`
- Create: `apps/api/src/context_builder/services/tutorial_agent.py`
- Create: `apps/api/src/context_builder/routers/tutorial.py`
- Modify: `apps/api/src/context_builder/main.py`
- Test: `tests/api/test_tutorial_tools.py`

- [ ] **Step 1: Write failing security tests**

Cover:

- unknown tool rejected;
- mutating tool without confirmation rejected;
- publish/approve/delete tools are not registered;
- `compile_context_bundle_after_confirmation` is registered as mutating;
- `compile_context_bundle_after_confirmation` refuses to run without stored confirmation;
- confirmed compile delegates to `CompileContextBuildRun`, never shell;
- tool call requires workspace membership;
- response labels observation vs recommendation vs confirmed action.

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_tutorial_tools.py -q
```

Expected: FAIL because tutorial modules do not exist.

- [ ] **Step 2: Implement allowlisted tools**

Implement MVP tools:

- `explain_context_build_state`
- `detect_input_mode`
- `run_context_build_preflight`
- `get_context_build_run_status`
- `draft_compile_plan`
- `request_compile_confirmation`
- `compile_context_bundle_after_confirmation`
- `open_relevant_screen`
- optional `query_published_knowledge`

Do not implement arbitrary shell/API/MCP calls.

- [ ] **Step 3: Run GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_tutorial_tools.py -q
uv run --cache-dir .uv-cache ruff check apps\api\src\context_builder\schemas\tutorial.py apps\api\src\context_builder\services\tutorial_tools.py apps\api\src\context_builder\services\tutorial_agent.py apps\api\src\context_builder\routers\tutorial.py tests\api\test_tutorial_tools.py
```

Expected: PASS.

## Task 10: AI Tutor Sidecar UI

**Files:**

- Create: `apps/web/src/components/tutorial-sidecar.tsx`
- Modify: `apps/web/src/components/workspace-shell.tsx`
- Modify: `apps/web/src/lib/api.ts`
- Test: frontend typecheck/build.

- [ ] **Step 1: Add sidecar to shell**

Sidecar requirements:

- collapsible panel;
- visible as tutorial/copilot, not chatbot final;
- shows tool calls as pending/confirmed/executed/blocked;
- mutating action requires explicit button confirmation;
- never auto-publishes.

- [ ] **Step 2: Verify**

Run:

```powershell
corepack pnpm --filter @context-builder/web typecheck
corepack pnpm --filter @context-builder/web build
```

Expected: PASS.

## Task 11: Docs And Acceptance Criteria

**Files:**

- Create: `tasks/TASK-020-unified-context-build-wizard-ai-tutor.md`
- Modify: `docs/00-start-here/USER_GUIDE.md`
- Modify: `docs/01-product/USER_FLOWS.md`
- Modify: `docs/07-qa/ACCEPTANCE_CRITERIA.md`
- Modify: `docs/operations/frontend-console-runbook.md`

- [ ] **Step 1: Document operator flow**

Document:

- one Wizard;
- automatic detection;
- source pack as internal path;
- AI tutor boundaries;
- confirmation model;
- current limits.

- [ ] **Step 2: Verify docs**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors.

## Task 12: Final Verification And Commit

- [ ] **Step 1: Backend gates**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_build_runs_api.py tests\api\test_context_build_preflight.py tests\api\test_tutorial_tools.py tests\integrity\test_context_build_runs_migration.py -q
uv run --cache-dir .uv-cache ruff check .
npm run typecheck:python
npm run typecheck:python:strict-full
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Expected: PASS.

- [ ] **Step 2: Frontend gates**

Run:

```powershell
node apps\web\scripts\test-context-build.mjs
corepack pnpm --filter @context-builder/web typecheck
corepack pnpm --filter @context-builder/web build
```

Expected: PASS.

- [ ] **Step 3: Full suite**

Run:

```powershell
uv run --cache-dir .uv-cache pytest -q
```

Expected: PASS.

- [ ] **Step 4: Review and commit**

Run:

```powershell
git status --short --branch
git diff --stat
git diff --check
git add packages\domain apps\api apps\web scripts\smoke docs tasks supabase\migrations tests
git commit -m "feat: add unified context build wizard"
```

Expected: commit created.

## Acceptance Criteria

- One Wizard handles single document, loose batch and source pack.
- User does not need to know what a source pack is.
- Backend preflight is the authoritative detector.
- Frontend detection is preview-only and cannot commit a canonical mode by itself.
- Source pack remains an internal mode selected by backend detection/preflight.
- `context_build_runs` tracks every build lifecycle.
- `context_build_runs` is canonical for new build flows.
- `source_pack_import_runs` remains compatibility-only and is linked or mirrored from canonical runs when legacy preflight persists.
- `input_fingerprint` exists before content upload; `input_hash` is filled after content/staging is available.
- Legacy source-pack preflight remains compatible.
- AI tutor is sidecar/tutorial only.
- Tutor tools are allowlisted.
- Mutating tutor tools require explicit human confirmation.
- `compile_context_bundle_after_confirmation` is implemented, tested, and delegates to backend compile use case.
- Tutor cannot approve, reject, publish, delete, change permissions or call shell.
- Frontend route `/workspaces/{workspaceId}/context-build` exists and is in nav.
- `Sources` remains inventory/history.
- Full backend and frontend gates pass.

## Follow-Up Tasks

These are intentionally outside TASK-020 unless the implementation slice is split:

- Browser-native zip/folder staging service with storage-backed unpacking.
- Async source-pack compile worker.
- Backfill/deprecation of `source_pack_import_runs`.
- Direct runtime import/publish flow in the external chatbot project.
- Rich chat memory for tutorial sessions.
