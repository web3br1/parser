# TASK-012 - Repository Clean Slate

Status: planned

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
