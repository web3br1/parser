# Industrial Parser Domain Extension Design

Status: proposed
Date: 2026-06-03
Branch: `codex/industrial-parser-partials`

## Summary

Add an industrial/QMS domain layer to the existing Context Compiler. The system
already parses files, chunks content, extracts facts/rules, supports human
review, publishes validated knowledge and exports `context_bundle.v1`. This
extension fills the domain gaps needed for controlled industrial documents:
metadata, revision status, industrial tags, relationship extraction, review
gates, fixtures and readiness checks.

## Goals

- Define the industrial controlled-document contract.
- Add a gap register that tracks what is partial, missing or explicitly out of
  scope.
- Preserve existing `context_bundle.v1` compatibility.
- Plan implementation through SDD and multi-agent governance.
- Keep OCR and GED/QMS connectors out of the first implementation slice.
- Make every publishable industrial output evidence-backed and reviewable.

## Non-Goals

- No parser implementation in this documentation slice.
- No OCR worker.
- No SharePoint, SoftExpert, Qualiex or other external connector.
- No chatbot runtime behavior.
- No first-class top-level `graph` field in `context_bundle.v1`.
- No semantic contradiction detection via embeddings.

## Current Foundation

Already present:

- PDF, DOCX, XLSX, CSV and TXT parsers.
- Chunking with page, sheet, row and heading metadata.
- Quality gate.
- Prompt-injection detection.
- Classification and extraction workers.
- Human review, publication and rollback concepts.
- Unknown queue and contradiction handling.
- `context_bundle.v1` schema, API, fixtures and source-pack compiler.
- Context Build Wizard and staging path for folder/zip uploads.

Partially present:

- evidence citation, but not section-level industrial provenance;
- status/supersede, but not controlled-document revision resolution;
- gaps/readiness, but not industrial blockers;
- tests in bundle, but not industrial fixture-generated tests;
- source-pack facts/rules, but not industrial QMS taxonomy.

## Gap Register

| Gap | Impact | Required decision |
|-----|--------|-------------------|
| Industrial metadata | The app cannot know owner, revision, approver or validity | Add controlled-document schema |
| Vigent vs obsolete | Chatbot could activate old procedures | Add revision resolver and review blocker |
| QMS taxonomy | Generic facts miss procedure/requisition/responsibility semantics | Add industrial classifier tags |
| Structural extraction | Form fields/tables/annexes may be flattened | Improve parser metadata and fixtures |
| Graph | Relations are not explicit | Represent graph as typed facts/rules in v1 |
| Review UX | Reviewer cannot approve metadata/revision/relations | Add industrial review surfaces |
| Fixtures | No reproducible industrial dataset | Add fixture pack and expected manifest |
| Readiness | Current blockers are generic | Add industrial blockers/warnings |
| OCR | Scanned docs cannot be processed | Defer to future ADR and mark OCR-required |
| Connectors | External QMS imports unavailable | Defer to later connector roadmap |

## Architecture

The first implementation slice should add focused modules instead of expanding
generic parsers or bundle code blindly.

Proposed file boundaries:

- `packages/domain/src/domain/industrial.py`: domain enums and Pydantic models.
- `packages/parsers/src/parsers/industrial_metadata.py`: deterministic metadata
  candidates from filename/text.
- `packages/parsers/src/parsers/industrial_structure.py`: section, annex, table
  and form-field hints.
- `workers/classification`: add industrial tag allowlist and prompt coverage.
- `workers/extraction`: add industrial extraction prompts and validators.
- `apps/api/src/context_builder/services`: add industrial review/readiness
  helpers using existing publication concepts.
- `packages/source_pack`: support industrial fixture packs and generated tests.
- `docs/03-pipeline/INDUSTRIAL_DOCUMENTS.md`: operational contract.

## Data Flow

```text
upload/staged source
-> existing file validation
-> existing parser extraction
-> industrial metadata candidate extraction
-> quality gate
-> chunking with industrial structure hints
-> industrial classification tags
-> schema-bound extraction
-> evidence span creation
-> review metadata/facts/rules/relations
-> publish
-> context_bundle.v1 export
```

## Bundle Strategy

Keep `context_bundle.v1` strict and compatible.

Industrial documents export through:

- `facts` for metadata, relations and explicit obligations;
- `rules` for conditional requirements, approvals and workflows;
- `evidence` for quotes and locations;
- `gaps` for missing metadata and unresolved conflicts;
- `tests` for expected industrial behavior;
- `identity.attributes` for corpus-level industrial profile.

Graph relations are exported as `industrial_relation` facts or
`document_relationship` rules, not as a new top-level field.

## Review And Approval

Human review must approve:

- controlled-document metadata;
- revision family status;
- extracted industrial facts/rules;
- relationship records;
- generated tests;
- gap resolution.

The four-agent governance model is:

- Orchestrator: owns sequencing and scope.
- Task Worker: implements one task at a time with TDD.
- Reviewer: performs spec compliance and code quality review.
- Approval: performs final acceptance and PR readiness gate.

## Error Handling

Industrial processing should prefer safe blockers over guesses:

- missing revision -> gap and blocked activation;
- duplicate revision with different hash -> gap and blocked activation;
- obsolete source used in active rule -> blocker;
- relation points to missing node -> blocker;
- OCR-required file -> unsupported/OCR-required gap;
- low-confidence industrial tag -> unknown/review queue.

## Security

The extension inherits existing security rules:

- no raw prompts or provider responses in bundle;
- no local paths, bearer tokens, secrets or signed URLs;
- no unpublished facts/rules in bundle;
- no unreviewed industrial relationship published;
- RLS on every new workspace-scoped table;
- no hardcoded model names.

## Testing

Required test groups:

- metadata extraction unit tests;
- revision resolver unit tests;
- parser structure tests for sections/tables/forms;
- classifier allowlist tests;
- extraction validator tests;
- review/readiness tests;
- source-pack industrial fixture compiler tests;
- context bundle compatibility tests;
- secret scan and redaction tests.

## Acceptance

The documentation slice is complete when:

1. ADR exists.
2. Operational industrial pipeline doc exists.
3. SDD spec exists.
4. SDD implementation plan exists.
5. Task tracker exists.
6. PR body exists.
7. Gaps are classified as first-slice, follow-up or non-goal.
8. Multi-agent roles are defined.
9. `context_bundle.v1` compatibility is explicit.

## Open Follow-Ups

- Decide whether future graph support becomes `context_bundle.v2`.
- Decide whether OCR belongs to this repo or a separate worker service.
- Decide how external QMS connector credentials and permissions are governed.
