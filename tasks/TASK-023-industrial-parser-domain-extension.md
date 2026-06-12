# TASK-023 - Industrial Parser Domain Extension

Status: proposed

## Goal

Plan and implement the first industrial/QMS extension for the Context Compiler:
controlled-document metadata, revision/vigency handling, industrial taxonomy,
relationship extraction and industrial readiness gates.

## Background

The repository already has a generic Context Compiler MVP. It can parse common
formats, chunk text, classify/extract facts and rules, route unknowns to human
review, publish validated knowledge and export `context_bundle.v1`.

The industrial parser plan requires additional semantics that are not fully
implemented: POP/IT/Form/Register taxonomy, revision status, QMS metadata,
document relationships and industrial blockers.

## References

- `docs/02-architecture/ADR-024-industrial-parser-domain-extension.md`
- `docs/03-pipeline/INDUSTRIAL_DOCUMENTS.md`
- `docs/superpowers/specs/2026-06-03-industrial-parser-domain-extension-design.md`
- `docs/superpowers/plans/2026-06-03-industrial-parser-domain-extension-sdd.md`

## Scope

- Controlled-document metadata contract.
- Deterministic metadata candidates.
- Revision family resolver.
- Industrial taxonomy and schema registry entries.
- Industrial relationship extraction.
- Industrial review/readiness gates.
- Industrial fixture corpus.
- PR and runbook documentation.

## Out Of Scope

- OCR implementation.
- GED/QMS connectors.
- Chatbot runtime behavior.
- `context_bundle.v2`.
- First-class graph top-level field in `context_bundle.v1`.
- Semantic contradiction detection via embeddings.

## Multi-Agent SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Owns the task sequence, context handoff and blocker resolution |
| Task Worker | Implements one task at a time with tests first |
| Reviewer | Reviews spec compliance and code quality after each task |
| Approval | Runs final acceptance and PR readiness gates |

## Acceptance

- ADR/spec/plan/task/PR docs exist.
- Gaps are classified and traceable.
- Implementation plan uses SDD task steps.
- Industrial bundle strategy preserves `context_bundle.v1`.
- Review and approval roles are explicit.
- Follow-up work is not confused with first-slice scope.

## Verification Target

Documentation-only verification:

```powershell
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Implementation verification is defined in the SDD plan.
