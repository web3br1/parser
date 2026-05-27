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

2. **TASK-012B - Stash Triage** — analysis complete, disposition pending user approval
   - Stash: `stash@{0}` — "archive real checkout before SDD clean integration" (35 files, ~89 KB diff)
   - Created on branch `codex-real-test-readiness` (pre-SDD); integration branch rebuilt from scratch via multi-agent SDD.

   **Category: already_integrated** — clean branch already has equal or newer version; safe to discard:
   - `scripts/dev/*` (6 files: apply_migration_039.py, check_local_stack.ps1, setup_redis_windows.ps1, start_local_stack.ps1, stop_local_stack.ps1, test_pooler.py) — stash was DELETING these; `scripts/dev/` doesn't exist in integration branch at all
   - `scripts/smoke/run_real_smoke.py` — integration branch has TASK-022 version (much newer)
   - `docs/operations/smoke-runbook.md` — integration branch has TASK-022 update
   - `tests/smoke/test_real_readiness.py`, `test_real_smoke_orchestrator.py`, `test_task010_smoke_scripts.py` — already tracked in integration branch
   - `scripts/smoke/real_readiness.py` — 2-line removal; current version is authoritative
   - `scripts/smoke/frontend_console_smoke.mjs` — 1-line change; trivial
   - `tasks/TASK-001-monorepo-scaffold.md`, `TASK-007-integrity-hardening.md`, `TASK-010-supabase-real-environment.md` — task status edits; integration branch has current state
   - `docs/superpowers/plans/2026-05-20-real-smoke-readiness.md`, `2026-05-21-real-smoke-orchestrator.md` — plan files exist in integration branch; stash edits minor status changes
   - `docs/superpowers/specs/2026-05-20-real-smoke-readiness-design.md`, `2026-05-21-real-smoke-orchestrator-design.md` — spec edits; current versions are authoritative

   **Category: needs diff review before discard** — doc files with added content that may have new material:
   - `docs/00-start-here/MVP_DECISIONS.md` — 19 lines added (stash added decisions not yet in integration)
   - `docs/00-start-here/SYSTEM_OVERVIEW.md` — 24 lines added
   - `docs/07-qa/ACCEPTANCE_CRITERIA.md` — 6 lines added
   - `docs/07-qa/REGRESSION_GATES.md` — 26 lines added
   - `docs/07-operations/DECISOES_PENDENTES.md` — 16 lines edited (pending decisions log)
   - `README.md` — 15 lines edited
   - `docs/00-start-here/CLAUDE.md` — 64 lines edited (old CLAUDE.md; root CLAUDE.md is authoritative)
   - `docs/07-operations/PILOT_LOCAL_RUNBOOK.md`, `SMOKE_TEST_SUPABASE.md`, `SUPABASE_REAL_ENVIRONMENT.md` — ops runbook edits from pre-Docker era

   **Recommendation:** discard entire stash after user reviews the 5 "needs diff review" doc files listed above. No test or code content is worth recovering. The doc additions are likely superseded by SDD-era docs.
   - Acceptance: stash disposition is documented as `discard`, `converted_to_task`, or `already_integrated`.

3. **TASK-012C - Worktree Retirement**
   - Decide whether `C:/tmp/parser-context-bundle-export-v1` can be removed.
   - Keep `C:/tmp/parser-sdd-clean-integration` only if it still has comparison value after PR merge.
   - Acceptance: remaining worktrees have clear purpose.

4. **TASK-012D - Explicit Cleanup Execution**
   - Run only approved cleanup commands.
   - No `git reset`, `git restore`, recursive delete, or worktree removal without explicit approval.
   - Acceptance: root checkout has no ambiguous local state.
