# Parser-Wide Quality Closure Design

Date: 2026-06-12
Status: approved for implementation

## Purpose

Close the remaining quality gap in the Parser product by turning parser outputs
into calibrated claims across all parser families. The Parser must distinguish
between extracted evidence, candidates, diagnostics, review-required findings
and publishable knowledge. Industrial/QMS PDFs remain the richest proof case,
but the contract applies to PDF, DOCX, XLSX, CSV, TXT and source-pack inputs
where the same concepts are available.

## Product Quality Problem

The current benchmark stack can count parser behavior and prevent many
regressions. It does not yet fully prove that every parser family follows a
common vertical quality path:

```text
input accepted
-> parse artifact created
-> truth evaluated
-> review need decided
-> publication readiness blocked or allowed
-> release gate passes
```

The risky failure mode is not just missing extraction. The risky failure mode is
an unsafe promotion: a parser treats a local section code, table artifact,
formula row, heading, file name or low-confidence candidate as document-level
truth without evidence, ground truth or review.

## Scope

This slice creates a parser-wide quality closure layer with industrial document
family handling as the most demanding fixture.

In scope:

- Add a generic parser quality profile that classifies parse artifacts into
  stable quality signals.
- Detect document-family or collection-like artifacts without promoting nested
  identifiers as file-level metadata.
- Preserve internal identifiers as evidence-backed candidates.
- Add parser-wide ground truth fixture coverage for positive and negative
  expectations.
- Add review packets for parser-wide quality risks that block unsafe
  publication.
- Add publication/readiness tests proving unresolved parser quality risks block
  `context_bundle.v1` readiness without changing the bundle schema.
- Keep industrial-specific logic behind industrial modules while exposing
  shared quality decisions through generic names.

Out of scope:

- OCR, vision model calls or image captioning.
- LLM adjudication.
- `context_bundle.v2`.
- Database migrations.
- Review UI.
- Runtime importer changes.
- Committing real dirty PDFs or `.run` artifacts.

## Contracts

### Input Contract

Each parser input remains eligible only after existing security and quality
checks. This task does not change MIME, size, abuse, macro or low-text gates.

### Parse Contract

Parser outputs may claim:

- extracted text, rows, pages or sheets;
- normalized parser quality signals;
- nested identifier candidates;
- document-family or collection candidates;
- section or table/row diagnostics;
- review packet candidates.

Parser outputs must not claim:

- final controlled-document identity for a collection;
- publishable facts from nested identifiers;
- visual truth from uncaptioned images;
- row/table semantics without evidence.

### Truth Contract

Truth is evaluated through committed sanitized fixtures. Positive expectations
must be predicted. Negative expectations are critical if predicted, especially
file-level metadata that came from nested content.

### Review Contract

Unresolved parser-wide risks produce review packets with stable reason codes,
evidence and publication impact. Review packet grouping should reduce repeated
noise while preserving representative evidence.

### Publication Contract

`context_bundle.v1` stays strict. If unresolved parser quality risks would make
metadata, evidence or source identity unsafe, readiness must block through
existing facts/gaps/readiness mechanisms rather than adding top-level fields.

### Release Gate

The existing Parser quality gate remains the top orchestrator. This task extends
its required evidence through ground truth, regression and targeted tests. The
dirty real benchmark remains optional/diagnostic when the local corpus is absent.

## Parser-Wide Quality Signals

Introduce a generic quality profile shape for benchmark/reporting and tests:

- `document_family_candidate`: input appears to contain multiple internal
  documents or document-like records.
- `nested_identifier_count`: number of internal identifiers detected with
  evidence.
- `unsafe_file_metadata_blocked`: parser intentionally refused file-level
  metadata promotion.
- `review_required`: unresolved quality risk requires human decision before
  publication.
- `publication_blocking_risk`: unresolved risk should block bundle readiness.

Industrial may produce richer evidence such as internal POP codes and section
paths. Non-industrial parsers may produce simpler evidence: sheet names, CSV
headers, DOCX headings, TXT headings or file-level parse warnings.

## Industrial Proof Case

The PMPR-like collection case should prove:

- multiple nested POP-like identifiers are recognized;
- no nested POP code becomes file-level `document_code`;
- the artifact is classified as a document-family candidate;
- internal identifiers are preserved with evidence;
- a `document_family_requires_review` packet is generated;
- unresolved publication from that artifact is represented as a blocking gap;
- ground truth includes both positive and negative expectations.

## Parser-Wide Fixture Cases

Add sanitized committed fixtures:

- `document_family_collection.txt`: multiple nested controlled document codes.
- `toc_nested_identifier_noise.txt`: table-of-contents identifiers that must not
  become file-level metadata.
- `generic_docx_like_headings.txt`: heading-like input with no unsafe metadata
  promotion.
- `csv_register_like_rows.csv`: row identifiers remain row evidence, not file
  identity.

The fixtures are text/CSV so they remain small, committed and private-safe.
They exercise parser-wide quality behavior without requiring real PDFs in CI.

## Review Reason Codes

Add or preserve stable review reason codes:

- `document_family_requires_review`
- `nested_identifier_file_metadata_blocked`
- `ambiguous_section_hierarchy`
- `visual_table_figure_risk`
- `missing_metadata`

The first two are parser-wide quality closure additions. Existing industrial
reason codes continue to work.

## Success Criteria

- Parser-wide fixture tests prove no unsafe file-level metadata promotion.
- Ground truth evaluator supports quality-profile and nested-identifier items.
- Review packet tests prove document-family risks are grouped with evidence.
- Context bundle tests prove unresolved parser quality gaps block readiness.
- Parser quality gate passes after the changes.
- No real PDF, `.run` report or private absolute path is committed.

## Non-Goals And Guardrails

- Do not make every parser industrial-aware.
- Do not move parser candidates into published facts automatically.
- Do not add a schema-breaking top-level bundle field.
- Do not treat higher benchmark counts as quality unless ground truth and review
  behavior improve.
- Do not weaken existing metadata false-positive protections.

