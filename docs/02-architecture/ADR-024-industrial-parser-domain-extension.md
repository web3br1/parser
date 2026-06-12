# ADR-024 - Industrial Parser Domain Extension

Status: proposed
Date: 2026-06-03
Branch: `codex/industrial-parser-partials`

## Context

The repository already has a working Context Compiler surface:

- parsers for PDF, DOCX, XLSX, CSV and TXT;
- chunking with page, sheet, row and section hints;
- classification/extraction workers;
- human review and publication state;
- `context_bundle.v1` export with readiness, evidence, gaps and tests;
- source-pack staging and compilation.

The industrial/QMS parser plan adds requirements that are only partially
covered today. It needs controlled-document semantics: document code, revision,
effective status, owner area, approval metadata, process relationships, forms,
records, CAPA/deviation/audit/training concepts, and explicit handling of
obsolete versions.

## Decision

Add an industrial domain layer as an additive extension on top of the existing
Context Compiler. The first implementation slice must not break
`context_bundle.v1` or the existing generic business fact types.

The industrial layer will introduce:

1. A domain contract for controlled documents and QMS concepts.
2. Deterministic document metadata extraction.
3. Revision/vigency resolution for controlled document families.
4. Industrial classification tags and extraction schemas.
5. Relationship extraction represented as graph-shaped facts/rules inside the
   current bundle contract.
6. Human review gates for metadata, revision status, relationships and
   industrial conflicts.
7. Industrial fixtures and regression gates.

## Compatibility Rule

`context_bundle.v1` remains strict. The first industrial slice will export
industrial data through existing safe sections:

- `sources`: published source identity and authority.
- `facts`: industrial metadata, document status, obligations and relations.
- `rules`: requirements, responsibilities, approvals and conditional flows.
- `evidence`: quotes with page/sheet/row references.
- `gaps`: missing metadata, unresolved revisions and unsupported extraction.
- `tests`: generated or seeded industrial validation prompts.
- `identity.attributes`: corpus-level industrial profile.

No new top-level `graph` field is allowed in `context_bundle.v1`. Graph RAG
importers may reconstruct nodes and edges from published facts/rules whose
types are explicit, such as `industrial_relation` or `document_relationship`.
A future `context_bundle.v2` can add a first-class graph section only after the
consumer runtime validates the migration.

## Non-Negotiable Rules

- No free-form LLM output may be stored as structured truth.
- No unreviewed industrial fact, rule or relationship may be published.
- OCR is out of the first implementation slice and remains a separate ADR.
- Connectors for QMS/GED systems are out of the first implementation slice.
- Existing generic fact types must keep working.
- Every new multi-tenant table must include `workspace_id` and RLS.
- Every published industrial item must carry source and evidence provenance.
- Obsolete documents must not silently become active bundle knowledge.

## Gap Register

| Gap | Current state | Target state | First-slice decision |
|-----|---------------|--------------|----------------------|
| Industrial metadata | Generic source fields only | document code, type, revision, dates, owner, approver, plant, confidentiality | Add internal schema and extract/review flow |
| Vigent vs obsolete | Generic `status` and supersede fields | deterministic revision family resolution | Add revision resolver and review conflicts |
| Document taxonomy | Generic business fact types | POP, IT, Manual, Policy, Form, Record, Specification | Add industrial enums and schema registry entries |
| Structural extraction | Basic headings/tables | sections, annexes, tables, form fields, numbered lists | Improve deterministic parser metadata before LLM |
| Industrial tags | Generic classification | procedure, requirement, definition, responsibility, CAPA, audit, calibration, training | Add classifier allowlist and prompts |
| Knowledge graph | No first-class graph | document/process/form/role relationships | Export graph as typed facts/rules in v1 |
| Review UX | Reviews facts/rules | reviews metadata, revision status and relations | Extend review detail and approval states |
| Fixtures | Semi-real business docs | controlled-document fixture pack | Add industrial fixture corpus |
| Gates | Generic readiness | QMS blockers and warnings | Add industrial readiness issues |
| OCR | Rejected in MVP | future OCR worker | Keep out of this slice |
| Connectors | Out of MVP/V2 | GED/QMS connectors | Keep out of this slice |

## Domain Contract

The industrial layer should normalize documents into a controlled-document
metadata object:

```json
{
  "document_code": "POP-QA-014",
  "document_type": "POP",
  "title": "Controle de Nao Conformidades",
  "revision": "04",
  "status": "vigent",
  "issue_date": "2026-01-10",
  "approval_date": "2026-01-15",
  "review_due_date": "2027-01-15",
  "owner_area": "Qualidade",
  "process": "Nao Conformidade",
  "plant": "SP-01",
  "approvers": ["Gerente da Qualidade"],
  "confidentiality": "internal",
  "allowed_audience": ["quality", "production"]
}
```

Relationships should be normalized as evidence-backed records:

```json
{
  "from_id": "POP-QA-014",
  "to_id": "FOR-QA-002",
  "relationship_type": "uses_form",
  "source_document_code": "POP-QA-014",
  "evidence_quote": "Registrar a NC no formulario FOR-QA-002."
}
```

## Multi-Agent Governance

This work uses SDD with four roles:

| Role | Responsibility | May approve? |
|------|----------------|--------------|
| Orchestrator | Maintains ADR/spec/plan, sequences tasks, resolves blockers | No final approval |
| Task Worker | Implements one SDD task at a time with TDD | No |
| Reviewer | Reviews spec compliance and code quality after every task | Can recommend |
| Approval | Performs final acceptance gate across docs, tests, security and PR readiness | Yes |

The Orchestrator must not allow the Task Worker to implement beyond the current
checked task. The Reviewer must reject scope drift. The Approval role must block
publication if any non-negotiable rule is violated.

## Consequences

Positive:

- Industrial functionality becomes testable without rewriting the current MVP.
- Existing chatbot/importer compatibility is preserved.
- Review and publication remain the source of truth.
- Graph behavior can be introduced without breaking `context_bundle.v1`.

Trade-offs:

- The first bundle export will not have a dedicated `graph` top-level section.
- Review UX will need explicit industrial states before production use.
- OCR and external QMS connectors remain deferred work.

## Acceptance

This ADR is accepted only when the matching spec, SDD plan, task tracker and PR
body exist and all open gaps are classified as first-slice, follow-up or
explicit non-goal.
