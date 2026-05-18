# TASK-011 Frontend Console Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the internal Next.js console foundation for workspace navigation, sources visibility, and operator upload flow.

**Architecture:** Keep the current App Router paths and existing `[workspaceId]` route parameter. Extract repeated workspace chrome and sources/upload UI from the current page into focused client components while preserving the FastAPI-backed multipart upload through `/workspaces/{workspaceId}/sources/upload`.

**Tech Stack:** Next.js App Router, React, TypeScript, Tailwind CSS, lucide-react, existing `apiFetch` and `useSession` helpers.

---

### Task 1: Workspace Shell

**Files:**
- Create: `apps/web/src/components/workspace-shell.tsx`
- Create: `apps/web/src/app/workspaces/[workspaceId]/layout.tsx`

- [ ] **Step 1: Add a reusable shell component**

Create `WorkspaceShell` as a client component. It must read the current path, use `useSession({ required: true })`, render sidebar links for Sources, Review Queue, Unknown Items, Knowledge Base, Query, and Settings, and expose a Sign Out button from the session hook.

- [ ] **Step 2: Add the workspace route layout**

Create `layout.tsx` under `[workspaceId]` that wraps all nested pages in `WorkspaceShell`.

- [ ] **Step 3: Remove page-local nav duplication**

Delete `ConsoleNav` usage from workspace child pages touched by this task. The shell owns navigation.

### Task 2: Sources Dashboard Components

**Files:**
- Create: `apps/web/src/components/sources-data-table.tsx`
- Modify: `apps/web/src/app/workspaces/[workspaceId]/sources/page.tsx`

- [ ] **Step 1: Extract table rendering**

Move source/job table rendering into `SourcesDataTable`, including empty, loading, status badge, file size, and created date display.

- [ ] **Step 2: Add status color mapping**

Use deterministic badge styles for `uploaded`, `processing`, `extracted`, `needs_review`, `published`, `failed`, and unknown statuses.

### Task 3: Upload Flow Component

**Files:**
- Create: `apps/web/src/components/file-uploader.tsx`
- Modify: `apps/web/src/app/workspaces/[workspaceId]/sources/page.tsx`

- [ ] **Step 1: Extract upload state machine**

Move drag/drop, file picker, multipart POST, and upload status messaging into `FileUploader`.

- [ ] **Step 2: Keep upload through FastAPI**

Call `POST /workspaces/${workspaceId}/sources/upload` with `FormData`. Do not upload directly to Supabase Storage from the browser.

- [ ] **Step 3: Refresh dashboard after success**

Accept an `onUploaded` callback and call it after accepted uploads so the page reloads sources/jobs.

### Task 4: Verification

**Files:**
- Modify only if checks fail: `apps/web/src/**/*`

- [ ] **Step 1: Typecheck**

Run `corepack pnpm --filter @context-builder/web typecheck`.

- [ ] **Step 2: Production build**

Run `corepack pnpm --filter @context-builder/web build`.

- [ ] **Step 3: Browser smoke**

Start the web app locally, open `/login` or `/workspaces`, and verify the shell/sources/upload route renders without console errors.
