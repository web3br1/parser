# TASK-039 - Parser Architecture Spine And Sequential Roadmap

Status: completed

## Goal

Consolidate the Parser product architecture into an explicit sequential spine
with contracts, states and promotion criteria before adding more capability
work.

## Background

The recent parser slices are individually useful: industrial parsing, fixtures,
benchmarks, ratchets, quality gates, ground-truth diagnostics, domain models,
context bundles, review packets and readiness gates. The problem is that they
now sit at different architectural layers without a single product sequence
that explains how they compose.

The product spine must stay visible:

```text
document enters
-> parser understands
-> human reviews
-> knowledge publishes
-> bundle exits
-> runtime trusts
```

TASK-039 is a consolidation task. It does not implement product behavior.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Owns the spine, contract boundaries and sequencing discipline |
| Task Worker | Produces documentation only and avoids runtime/product changes |
| Reviewer | Checks that every mechanism is placed in the correct contract layer |
| Approval | Confirms no new feature work was introduced and verification evidence exists |

## Scope

- Define six sequential contracts:
  - Input Contract.
  - Parse Contract.
  - Truth Contract.
  - Review Contract.
  - Publication Contract.
  - Release Gate.
- Define state transitions and promotion criteria.
- Reposition current work areas into the spine.
- Make TASK-038 a pause/reposition decision before merge or push.
- Define the intake rule for future parser tasks:
  - contract affected;
  - downstream contract unlocked;
  - state transition;
  - promotion criterion;
  - blocking criterion;
  - verification gate.

## Out Of Scope

- New parser behavior.
- New tests.
- New benchmark metrics.
- New readiness scripts.
- New UI.
- New database migrations.
- New `context_bundle.v2` work.
- Runtime importer changes.
- Hermes, Tri-Memory or agent memory work.

## Proposed Files

- Create: `docs/02-architecture/PARSER_ARCHITECTURE_SPINE.md`
- Create: `tasks/TASK-039-parser-architecture-spine-and-sequential-roadmap.md`

## Acceptance

- The architecture document contains the six contracts in sequence.
- Each contract declares what it may assert and what it must not assert.
- The state model names promotion points from raw input to runtime-importable
  bundle.
- Existing parser, benchmark, review, publication and readiness mechanisms are
  mapped to the contract they primarily serve.
- TASK-038 is explicitly paused or repositioned until it declares its contract
  and downstream unlock.
- Future parser tasks have an explicit intake rule.
- No product code, runtime code, schema, worker, API or UI file is modified.

## Verification Target

Documentation-only verification:

```powershell
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Manual verification:

```powershell
git status --short docs\02-architecture\PARSER_ARCHITECTURE_SPINE.md tasks\TASK-039-parser-architecture-spine-and-sequential-roadmap.md
```

## Execution Checklist

- [x] Create the architecture spine document.
- [x] Define the six contracts.
- [x] Define state transitions and promotion criteria.
- [x] Map existing work areas to the spine.
- [x] Add TASK-038 pause/reposition rule.
- [x] Define future parser task intake rule.
- [x] Run documentation verification.
- [x] Record execution evidence in this task file.

## Execution Evidence

Completed on 2026-06-07.

- Created `docs/02-architecture/PARSER_ARCHITECTURE_SPINE.md`.
- Created this TASK-039 tracker.
- Kept the change documentation-only: no product code, runtime code, schema,
  worker, API or UI files were modified by this task.

Secret scan:

```powershell
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Result: exit `0`. The command printed environment certificate warnings from
`uv`, but the repository secret scan completed successfully.

Placeholder scan:

```powershell
rg -n "TB[D]|TO[D]O|implemen[t] later|fill in detail[s]|FIXM[E]" docs\02-architecture\PARSER_ARCHITECTURE_SPINE.md tasks\TASK-039-parser-architecture-spine-and-sequential-roadmap.md
```

Result: exit `1`, meaning no matches were found.

Scoped status check:

```powershell
git status --short docs\02-architecture\PARSER_ARCHITECTURE_SPINE.md tasks\TASK-039-parser-architecture-spine-and-sequential-roadmap.md
```

Result: only the two TASK-039 documentation files were listed as untracked.
