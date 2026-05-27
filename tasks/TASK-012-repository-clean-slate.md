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

1. **TASK-012A - Ignore/Artifact Hygiene**
   - Confirm `.gitignore` covers all generated local artifacts.
   - Add missing ignore entries only when a generated artifact is likely to recur.
   - Acceptance: `git status --short` shows no ambiguous untracked files after local runs.

2. **TASK-012B - Stash Triage**
   - Review `stash@{0}` file by file.
   - Keep only intentional future work that is not already represented in the clean branch.
   - Convert retained ideas into explicit tasks instead of applying the stash.
   - Acceptance: stash disposition is documented as `discard`, `converted_to_task`, or `already_integrated`.

3. **TASK-012C - Worktree Retirement**
   - Decide whether `C:/tmp/parser-context-bundle-export-v1` can be removed.
   - Keep `C:/tmp/parser-sdd-clean-integration` only if it still has comparison value after PR merge.
   - Acceptance: remaining worktrees have clear purpose.

4. **TASK-012D - Explicit Cleanup Execution**
   - Run only approved cleanup commands.
   - No `git reset`, `git restore`, recursive delete, or worktree removal without explicit approval.
   - Acceptance: root checkout has no ambiguous local state.
