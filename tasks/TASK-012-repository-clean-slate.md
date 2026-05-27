# TASK-012 - Repository Clean Slate

Status: in_progress

## Objective

Clean the original checkout after the integration branch is verified, without
losing intentional user work or experimental findings.

## Scope

- Preserve the clean integration worktree as the source of truth.
- Compare dirty files in the original checkout against committed integration
  changes.
- Keep only files that represent intentional future work.
- Remove duplicate or superseded experimental artifacts from the original
  checkout after explicit review.
- Categorize remaining future work into TASK-013 through TASK-016 or newer
  tasks.

## Constraints

- Do not run destructive commands in the original checkout without explicit
  approval.
- Do not reset or restore user-created changes silently.
- Prefer git worktrees for future implementation slices.

## Acceptance

- Original checkout has no ambiguous dirty files.
- Every remaining uncommitted change has an owner, purpose and task reference.
- Integration branch remains clean and reproducible.

## Inventory - 2026-05-27

Canonical branch/worktree:

- `C:/Users/Katz/OneDrive/Desktop/Meus projetos/Parser`
- branch: `codex/source-pack-context-bundle-compiler`
- HEAD: `0511ae2`
- remote: synchronized with `origin/codex/source-pack-context-bundle-compiler`
- working tree: clean before TASK-012 documentation update

Existing worktrees:

- `C:/Users/Katz/OneDrive/Desktop/Meus projetos/Parser` -> `codex/source-pack-context-bundle-compiler`
- `C:/tmp/parser-sdd-clean-integration` -> `codex-sdd-clean-integration`
- `C:/tmp/parser-context-bundle-export-v1` -> `codex-context-bundle-export-v1`

Preserved stash:

- `stash@{0}`: `On codex-real-test-readiness: archive real checkout before SDD clean integration`
- Contains old dirty-checkout edits around docs, smoke/readiness scripts, review console shell link and removal of legacy `scripts/dev` PowerShell helpers.
- Treat as triage material only. Do not apply wholesale.

Dry-run cleanup candidates:

- Safe generated/local artifacts: `.mypy_cache/`, `.pytest_cache/`, `.pytest-tmp/`, `.ruff_cache/`, `.run/`, `.uv-cache/`, `.uv-tools/`, `.venv/`, `node_modules/`, `apps/web/.next/`, `apps/web/node_modules/`, `*.tsbuildinfo`, `__pycache__/`.
- Local runtime artifacts: `control/*.exchange`, `supabase/.branches/`, `supabase/.temp/`.
- Local agent config: `.claude/settings.local.json`.
- Empty/local scratch candidates: `codex-smoke-basetemp/`, `supabase/snippets/`.

No destructive cleanup has been executed.

## Proposed Cleanup Slices

1. **TASK-012A - Ignore/Artifact Hygiene** ✅ complete — 2026-05-27
   - `git ls-files --others --exclude-standard` → zero results. No ambiguous untracked files.
   - `git status --short` → clean. All generated artifacts are already covered by `.gitignore`.
   - Coverage verified:
     - Caches: `.mypy_cache/`, `.pytest_cache/`, `.pytest-tmp/`, `.ruff_cache/` ✓
     - Runtime: `.run/`, `.venv/`, `.uv-cache/`, `.uv-tools/` ✓
     - Build: `node_modules/`, `apps/web/.next/`, `*.tsbuildinfo`, `__pycache__/` ✓
     - Local config: `.env`, `.claude/settings.local.json` ✓
     - Supabase: `supabase/.branches/`, `supabase/.temp/` ✓
     - Workers: `control/*.exchange` ✓
     - Smoke: `codex-smoke-basetemp/` ✓
   - No `.gitignore` changes needed.
   - Observation: `backend/` and `prototype/` are **tracked** (initial commit only, never touched again).
     Not a `.gitignore` issue — candidates for deletion in TASK-012D.

2. **TASK-012B - Stash Triage** ✅ complete — 2026-05-27
   - Stash: `stash@{0}` — "archive real checkout before SDD clean integration" (35 files, ~89 KB diff)
   - Created on branch `codex-real-test-readiness` (pre-SDD); integration branch rebuilt from scratch via multi-agent SDD.

   **Final disposition — all 35 files:**

   `already_integrated` (30 files):
   - `scripts/dev/*` (6 files) — stash was DELETING these; `scripts/dev/` already absent from integration branch
   - `scripts/smoke/run_real_smoke.py` — integration branch has TASK-022 version (much newer)
   - `docs/operations/smoke-runbook.md` — integration branch has TASK-022 update
   - `tests/smoke/test_real_readiness.py`, `test_real_smoke_orchestrator.py`, `test_task010_smoke_scripts.py` — already tracked
   - `scripts/smoke/real_readiness.py`, `frontend_console_smoke.mjs` — trivial changes; current versions authoritative
   - `tasks/TASK-001/007/010*.md` — task status edits; current state is authoritative
   - `docs/superpowers/plans/2026-05-20-*.md`, `2026-05-21-*.md` — plan files; integration has current versions
   - `docs/superpowers/specs/2026-05-20-*.md`, `2026-05-21-*.md` — spec files; current versions authoritative
   - `docs/00-start-here/MVP_DECISIONS.md` — Context Compiler/bundle already more complete in current doc
   - `docs/00-start-here/SYSTEM_OVERVIEW.md` — current doc already covers Parser != chatbot and `context_bundle.v1`
   - `docs/07-qa/ACCEPTANCE_CRITERIA.md` — Context Bundle criteria already more detailed in current version
   - `docs/07-qa/REGRESSION_GATES.md` — Context Bundle gate already exists in current version
   - `apps/web/src/components/workspace-shell.tsx` — trivial 2-line change
   - `README.md` — minor edits; current version authoritative

   `discard` (5 files):
   - `docs/07-operations/DECISOES_PENDENTES.md` — old pending-decisions log; useful decisions already migrated to current runbooks
   - `docs/00-start-here/CLAUDE.md` — old CLAUDE.md location; root `CLAUDE.md` is the authoritative copy
   - `docs/07-operations/PILOT_LOCAL_RUNBOOK.md` — pre-Docker era edits; superseded
   - `docs/07-operations/SMOKE_TEST_SUPABASE.md` — superseded by `docs/operations/smoke-runbook.md`
   - `docs/07-qa/SEMIREAL_PILOT_V2_TECHNICAL_RESULTS.md` — minor edit; current version authoritative

   **Conclusion:** nothing in the stash was worth applying or converting to a task.
   **Action executed:** `git stash drop stash@{0}` after explicit user approval.
   **Result:** `git stash list` is empty.

3. **TASK-012C - Worktree Retirement** ✅ complete — 2026-05-27

   Analysis:
   - `codex-sdd-clean-integration` (`5372e17`): 0 unique commits — pure ancestor of integration branch (merge-base = HEAD of sdd-clean). No remote tracking ref.
   - `codex-context-bundle-export-v1` (`be89225`): 1 unique commit (`feat: add context bundle export`, +1093 lines). All 5 key files already present in integration branch (`context_bundle.py` router/schema/service, `CONTEXT_BUNDLE.md`, `tests/api/test_context_bundle.py`). No remote tracking ref.

   Actions executed (user-approved):
   - `git worktree remove C:/tmp/parser-sdd-clean-integration` — deregistered from git (dir removed via `rm -rf` after Windows long-path error)
   - `git worktree remove C:/tmp/parser-context-bundle-export-v1` — removed
   - `git branch -d codex-sdd-clean-integration` — deleted
   - `git branch -D codex-context-bundle-export-v1` — force-deleted (1 non-merged commit, content confirmed in integration)

   Result: `git worktree list` shows only main checkout. `/c/tmp/parser-sdd-*` dirs gone.
   Note: `/c/tmp/parser-sdd-schema-review-pytest` is a pytest temp dir (no `.git`), unrelated.

4. **TASK-012D - Explicit Cleanup Execution**
   - Run only approved cleanup commands.
   - No `git reset`, `git restore`, recursive delete, or worktree removal without explicit approval.
   - Acceptance: root checkout has no ambiguous local state.
