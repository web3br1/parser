# TASK-012 Review Console Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the internal Review Queue console usable for the MVP operator flow: review by chunk, always show source context, approve in one click, edit+approve safely, reject, publish approved records, and surface progress.

**Architecture:** Preserve the current workflow-driven FastAPI API and Next.js workspace shell. Do not add a separate CRUD/admin surface. Use the existing review endpoints under `/workspaces/{workspaceId}/review`. The current backend does not expose a dedicated "send extracted item to unknown queue" endpoint, so this phase records that action as a rejection reason from the UI instead of pretending an unknown queue row was created.

**Docs source:** `docs/07-operations/DECISOES_PENDENTES.md#D-011`, `docs/01-product/VALIDATION_UX.md`, `docs/01-product/USER_FLOWS.md`, and `docs/00-start-here/MVP_DECISIONS.md`.

**Tech Stack:** Next.js App Router, React client components, TypeScript, Tailwind CSS, lucide-react, existing `apiFetch` and `useSession`.

---

### Task 1: Review Component Extraction

**Files:**
- Create: `apps/web/src/components/review-console.tsx`
- Modify: `apps/web/src/app/workspaces/[workspaceId]/review/page.tsx`

- [ ] **Step 1: Move review UI into a focused component**

Extract the chunk queue, detail panel, and record cards into `ReviewConsole` so the route page remains a thin authenticated container.

- [ ] **Step 2: Keep chunk context visible**

Show selected chunk text alongside extracted records. Operators must not approve without source context visible.

### Task 2: Filtering And Progress

**Files:**
- Modify: `apps/web/src/components/review-console.tsx`

- [ ] **Step 1: Add MVP filters**

Add `fact_type` and `source_id` filters backed by the existing queue endpoint query params.

- [ ] **Step 2: Show progress**

For the selected chunk, show counts for total records, pending records, published records, and unknown items.

### Task 3: Status-Aware Review Actions

**Files:**
- Modify: `apps/web/src/components/review-console.tsx`

- [ ] **Step 1: Approve and publish by status**

Approve should be available for pending extracted/needs_review records. Publish should be available only for approved or already published records.

- [ ] **Step 2: Add edit+approve**

Editing should validate local JSON first, call the edit endpoint, then approve the returned resource id when the backend returns a superseded/new version response.

- [ ] **Step 3: Add reject and mark unknown**

Reject should send `operator_rejected`. Mark unknown should use the existing reject endpoint with reason `send_to_unknown_queue` until a dedicated backend endpoint exists.

### Task 4: Operator Feedback

**Files:**
- Modify: `apps/web/src/components/review-console.tsx`
- Modify as needed: `apps/web/src/lib/api.ts`

- [ ] **Step 1: Per-item busy and result states**

Show per-action busy state and a short result message after successful actions.

- [ ] **Step 2: Improve structured error display if needed**

Surface backend validation/transition errors as readable messages.

### Task 5: Verification

**Files:**
- Modify only if checks fail: `apps/web/src/**/*`

- [ ] **Step 1: Typecheck**

Run `corepack pnpm --filter @context-builder/web typecheck`.

- [ ] **Step 2: Production build**

Run `corepack pnpm --filter @context-builder/web build`.

- [ ] **Step 3: HTTP smoke**

Start or reuse the local web server and verify `/workspaces/demo/review` responds with HTTP 200.
