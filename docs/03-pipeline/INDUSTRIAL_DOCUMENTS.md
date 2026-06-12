# Industrial Documents Pipeline

Status: proposed
Date: 2026-06-03

## Purpose

This document describes how the Context Compiler should evolve from generic
business knowledge extraction into an industrial/QMS parser while preserving
the existing MVP boundary: validated context in, reviewed/published knowledge
out, `context_bundle.v1` exported to an external runtime.

## Scope

First implementation slice:

- controlled-document metadata;
- revision and vigency detection;
- industrial document taxonomy;
- industrial tags and extraction schemas;
- evidence-backed relationship extraction;
- industrial gaps and readiness blockers;
- fixtures and tests.

Out of first slice:

- OCR for scanned documents;
- GED/QMS connectors such as SharePoint, SoftExpert and Qualiex;
- first-class `graph` top-level field in `context_bundle.v1`;
- chatbot runtime behavior;
- semantic contradiction detection via embedding.

## Input Formats

Supported by current parser foundation:

- PDF with selectable text;
- DOCX;
- XLSX;
- CSV;
- TXT.

Markdown is supported in the source-pack path. HTML and scanned-image OCR are
not first-slice requirements.

## Controlled Document Metadata

Each document should attempt to produce:

| Field | Required for publish | Notes |
|-------|----------------------|-------|
| `document_code` | Yes | Example: `POP-QA-014` |
| `document_type` | Yes | POP, IT, Manual, Policy, Form, Record, Specification |
| `title` | Yes | Human-readable title |
| `revision` | Yes | Normalized revision string |
| `status` | Yes | `vigent`, `obsolete`, `draft`, `approved`, `unknown` |
| `issue_date` | No | ISO date if present |
| `approval_date` | No | ISO date if present |
| `review_due_date` | No | ISO date if present |
| `owner_area` | Yes | Quality, Production, Maintenance, Lab, etc. |
| `process` | No | Related process name |
| `plant` | No | Unit/site/planta |
| `approvers` | No | Names or roles |
| `confidentiality` | No | public, internal, restricted |
| `allowed_audience` | No | Roles/groups allowed to use it |

Missing required publish metadata should create a gap and block industrial
activation until reviewed.

## Revision Resolution

Documents belong to a revision family:

```text
family_key = normalized(document_code)
revision_key = normalized(revision)
```

Rules:

1. If exactly one approved revision exists for a family, it may be marked
   `vigent` after review.
2. If multiple approved revisions exist, the highest revision candidate is
   suggested as `vigent`, but the family requires review unless the source
   explicitly marks the older revision as obsolete.
3. If a document has no revision, it is not publishable as controlled-document
   truth.
4. Obsolete revisions may remain in the corpus as historical evidence but must
   not be exported as active operational rules.
5. Two documents with same family and same revision but different content hash
   create a duplicate/conflict gap.

## Industrial Tags

Chunks can receive zero or more industrial tags:

- `procedure`;
- `requirement`;
- `definition`;
- `responsibility`;
- `deadline`;
- `acceptance_criteria`;
- `exception`;
- `risk`;
- `related_form`;
- `mandatory_record`;
- `process_step`;
- `corrective_action`;
- `preventive_action`;
- `audit`;
- `calibration`;
- `training`;
- `faq`.

Tags are classification hints. They are not publishable truth until extracted,
schema-validated and reviewed.

## Relationship Model

The first-slice graph is represented through bundle-compatible facts/rules:

```json
{
  "fact_type": "industrial_relation",
  "normalized_content": {
    "from_id": "POP-QA-014",
    "from_type": "Document",
    "to_id": "FOR-QA-002",
    "to_type": "Form",
    "relationship_type": "uses_form"
  }
}
```

Allowed relationship types:

- `defines_process`;
- `uses_form`;
- `requires_record`;
- `assigns_responsibility`;
- `requires_approval`;
- `references_document`;
- `supersedes`;
- `is_revision_of`;
- `triggers_action`;
- `requires_training`.

## Readiness

Industrial bundle readiness should block when:

- no published controlled document exists;
- published industrial record lacks source;
- published industrial record lacks evidence;
- required metadata is missing;
- revision conflict is unresolved;
- obsolete document is mixed into active rules;
- duplicate same-revision document has conflicting hash;
- relation references a missing node;
- document failed quality gate;
- document is OCR-required but OCR is disabled.

Warnings should include:

- optional metadata missing;
- low confidence extraction;
- table extraction warning;
- document has no owner role but was manually approved;
- relationship was inferred from weak language and needs monitoring.

## Review Requirements

Human review must cover:

1. document metadata;
2. revision/vigency decision;
3. industrial facts and rules;
4. relations;
5. gaps and blockers;
6. generated test prompts.

A reviewer can approve extracted content. A manager/owner or Approval role must
publish final industrial context.

## Fixture Pack

Minimum fixture corpus:

- `POP-QA-014 Rev 03` obsolete;
- `POP-QA-014 Rev 04` vigent;
- `IT-PRD-002` work instruction;
- `FOR-QA-002` form;
- one registration/log document;
- one FAQ document;
- one XLSX table;
- one document missing revision;
- one same-revision duplicate with different hash;
- one prompt-injection document;
- one scanned/empty PDF fixture that becomes OCR-required.

## Export

`context_bundle.v1` export remains the integration product. Industrial data is
exported as published facts/rules/evidence/gaps/tests using explicit type
names. A future bundle version may add a first-class graph only through a
separate compatibility decision.
