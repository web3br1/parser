# TASK-014 to TASK-023 Console Expansion Batch Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the internal operator console beyond Sources, Review, and Unknown into a usable MVP console covering query, workspace operations, source monitoring, privacy controls, shared UX primitives, role/permission clarity, and release documentation.

**Architecture:** Preserve the current workflow-driven FastAPI API and Next.js App Router. Prefer read-only or workflow surfaces over CRUD/admin screens unless a backend endpoint already exists. Keep browser access through operator JWT only; never expose service-role credentials.

**Tech Stack:** Next.js App Router, React, TypeScript, Tailwind CSS, lucide-react, existing FastAPI endpoints, existing `apiFetch` and `useSession`.

---

### TASK-014: Query Console Polish

**Files:**
- Create: `apps/web/src/components/query-console.tsx`
- Modify: `apps/web/src/app/workspaces/[workspaceId]/query/page.tsx`
- Modify as needed: `apps/web/src/lib/api.ts`

- [ ] Extract query UI into `QueryConsole`.
- [ ] Add controls for `include_evidence` and `max_output_tokens`.
- [ ] Add result summary for answer state, confidence, audit id, token usage, warnings, missing data, facts/rules/sources used.
- [ ] Add local query history for the current session.
- [ ] Run web typecheck/build.

### TASK-015: Workspace Operations Dashboard

**Files:**
- Create: `apps/web/src/app/workspaces/[workspaceId]/page.tsx`
- Create: `apps/web/src/components/workspace-dashboard.tsx`
- Modify as needed: `apps/web/src/components/workspace-shell.tsx`

- [ ] Add workspace landing page under `/workspaces/[workspaceId]`.
- [ ] Summarize sources, review, unknown, and query entry points from existing endpoints.
- [ ] Update shell brand/links so workspace root is reachable.
- [ ] Run web typecheck/build.

### TASK-016: Source Detail And Job Monitor

**Files:**
- Create: `apps/web/src/app/workspaces/[workspaceId]/sources/[sourceId]/page.tsx`
- Create: `apps/web/src/components/source-detail.tsx`
- Modify: `apps/web/src/components/sources-data-table.tsx`

- [ ] Link sources table rows to source detail.
- [ ] Show source metadata plus latest ingest job status.
- [ ] Provide refresh and clear error states.
- [ ] Run web typecheck/build.

### TASK-017: Privacy Settings Console

**Files:**
- Create: `apps/web/src/app/workspaces/[workspaceId]/settings/page.tsx`
- Create: `apps/web/src/components/privacy-console.tsx`
- Modify: `apps/web/src/components/workspace-shell.tsx`
- Modify: `apps/web/src/lib/api.ts`

- [ ] Enable Settings nav.
- [ ] Add owner-facing LGPD export request and delete dry-run request forms.
- [ ] Show returned deletion plan/request id.
- [ ] Do not implement destructive confirmed delete UI beyond explicit API support.
- [ ] Run web typecheck/build.

### TASK-018: Shared Console UX Primitives

**Files:**
- Create: `apps/web/src/components/console-primitives.tsx`
- Modify: `apps/web/src/components/*-console.tsx`

- [ ] Extract shared Alert, Pill/StatusBadge, LoadingRow, EmptyState, and ActionButton primitives.
- [ ] Replace duplicated local versions in Review/Unknown/Query where safe.
- [ ] Keep styles dense and operational, not marketing-like.
- [ ] Run web typecheck/build.

### TASK-019: Knowledge Base Read-Only Placeholder

**Files:**
- Create: `apps/web/src/app/workspaces/[workspaceId]/knowledge/page.tsx`
- Create: `apps/web/src/components/knowledge-console.tsx`
- Modify: `apps/web/src/components/workspace-shell.tsx`

- [ ] Enable Knowledge nav as read-only MVP placeholder.
- [ ] Do not invent backend data; explain that published facts/rules browsing needs a dedicated endpoint.
- [ ] Provide links to Query and Review.
- [ ] Run web typecheck/build.

### TASK-020: Permission And Role Feedback

**Files:**
- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/web/src/components/workspace-shell.tsx`
- Modify as needed: console pages/components

- [ ] Improve `insufficient_role` API messages.
- [ ] Render permission errors as actionable operator messages.
- [ ] Avoid showing service-role or backend secret language.
- [ ] Run web typecheck/build.

### TASK-021: Workspace List Polish

**Files:**
- Create: `apps/web/src/components/workspaces-console.tsx`
- Modify: `apps/web/src/app/workspaces/page.tsx`

- [ ] Extract workspace list/create flow into component.
- [ ] Add empty/loading/error states consistent with workspace shell.
- [ ] Keep create workspace workflow explicit and authenticated.
- [ ] Run web typecheck/build.

### TASK-022: Frontend Runbook And Acceptance Docs

**Files:**
- Modify: `docs/07-operations/PILOT_LOCAL_RUNBOOK.md`
- Modify: `docs/07-qa/ACCEPTANCE_CRITERIA.md`
- Create: `docs/07-operations/FRONTEND_CONSOLE_RUNBOOK.md`

- [ ] Document login token flow, workspace selection, upload, review, unknown, query, settings.
- [ ] Add frontend typecheck/build/smoke commands to acceptance docs.
- [ ] Document what is intentionally placeholder until backend endpoints exist.

### TASK-023: Console Verification Sweep

**Files:**
- Modify only if checks fail: `apps/web/src/**/*`

- [ ] Run `corepack pnpm --filter @context-builder/web typecheck`.
- [ ] Run `corepack pnpm --filter @context-builder/web build`.
- [ ] Smoke `/workspaces/demo/sources`, `/review`, `/unknown`, `/query`, `/settings`, and `/knowledge`.
- [ ] Record any blocked backend-dependent items in the final report.
