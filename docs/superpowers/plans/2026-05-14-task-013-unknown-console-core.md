# TASK-013 Unknown Queue Console Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the internal Unknown Queue console usable for resolving unclassified chunks during the MVP operator workflow.

**Architecture:** Preserve the current workflow-driven FastAPI API. Use the existing endpoints under `/workspaces/{workspaceId}/unknown` and the review chunk detail endpoint for context. Do not add schema creation or admin CRUD in this phase; "create new type" remains outside MVP until a backend schema draft endpoint exists.

**Docs source:** `docs/01-product/USER_FLOWS.md`, `docs/01-product/VALIDATION_UX.md`, `docs/07-operations/DECISOES_PENDENTES.md#D-011`, and the current backend contract in `apps/api/src/context_builder/routers/unknown.py`.

**Tech Stack:** Next.js App Router, React client components, TypeScript, Tailwind CSS, lucide-react, existing `apiFetch` and `useSession`.

---

### Task 1: Unknown Component Extraction

**Files:**
- Create: `apps/web/src/components/unknown-console.tsx`
- Modify: `apps/web/src/app/workspaces/[workspaceId]/unknown/page.tsx`

- [ ] **Step 1: Move unknown UI into a focused component**

Extract queue list, selected context, and resolution form into `UnknownConsole`.

- [ ] **Step 2: Keep source context visible**

Show raw unknown text and full chunk context side by side.

### Task 2: Queue Filters And Selection

**Files:**
- Modify: `apps/web/src/components/unknown-console.tsx`

- [ ] **Step 1: Add status filter**

Use the existing `status` query param with options `open`, `mapped`, `ignored`, and all.

- [ ] **Step 2: Add client-side source/type filters**

Since the backend currently exposes only `status`, filter visible rows by `source_id` and suggested type in the client.

### Task 3: Reclassify And Ignore Flow

**Files:**
- Modify: `apps/web/src/components/unknown-console.tsx`

- [ ] **Step 1: Use MVP type selector**

Use the known MVP types: `service_price`, `business_hours`, `payment_method`, `contact_info`, `faq_item`, `discount_rule`, and `cancellation_policy`.

- [ ] **Step 2: Derive destination automatically**

Map fact types to `extracted_facts` and rule types `discount_rule`/`cancellation_policy` to `business_rules`.

- [ ] **Step 3: Add per-item feedback**

Show per-action busy state and success/error messages for reclassify and ignore.

### Task 4: Verification

**Files:**
- Modify only if checks fail: `apps/web/src/**/*`

- [ ] **Step 1: Typecheck**

Run `corepack pnpm --filter @context-builder/web typecheck`.

- [ ] **Step 2: Production build**

Run `corepack pnpm --filter @context-builder/web build`.

- [ ] **Step 3: HTTP smoke**

Start or reuse the local web server and verify `/workspaces/demo/unknown` responds with HTTP 200.
