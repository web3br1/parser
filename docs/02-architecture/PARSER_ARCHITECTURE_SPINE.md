# Parser Architecture Spine And Sequential Roadmap

Status: current architecture baseline
Date: 2026-06-07

## Purpose

The Parser has accumulated strong horizontal capabilities: industrial parsing,
fragility fixtures, benchmarks, ratchets, quality gates, ground-truth
diagnostics, domain models, context bundles, review packets and readiness
checks. Those mechanisms are useful, but the product needs a visible vertical
spine so every future slice can explain where it acts and what downstream
contract it unlocks.

The product sequence is:

```text
document enters
-> parser understands only what it is allowed to claim
-> truth is evaluated against evidence and ground truth where required
-> human review resolves uncertain or blocking findings
-> reviewed knowledge is published
-> context bundle is exported
-> runtime can trust or reject the bundle
```

No new parser capability should be added until it can be placed in this
sequence.

## Global Rule

Every future parser task must declare:

- Which contract it changes.
- Which later contract it unlocks.
- Which state transition it promotes or blocks.
- Which tests or gates prove the transition.
- Which claims remain candidates, diagnostics or review items rather than
  publishable truth.

If a feature cannot answer those points, it is not ready to implement.

## Contract 1 - Input Contract

The Input Contract defines what may enter the system and when a source is
eligible for parsing.

Allowed inputs:

- PDF with selectable text.
- DOCX.
- XLSX.
- CSV.
- TXT.
- Markdown through the source-pack path.

Input assertions:

- MIME, extension, size and abuse checks are acceptable security assertions.
- Raw text volume, extraction emptiness and layout fragmentation are acceptable
  quality assertions.
- OCR-required, macro-risk, zip-bomb and low-text-volume signals are input
  blockers or gaps, not parser truth.

Input output:

- Accepted source candidate.
- Rejected source candidate with reason.
- Source quality report.
- File hash and provenance metadata.

Promotion criterion:

```text
uploaded_raw -> input_accepted
```

Only accepted inputs may move to the Parse Contract. Rejected or OCR-required
inputs may create gaps/readiness blockers, but they must not produce active
knowledge.

## Contract 2 - Parse Contract

The Parse Contract defines what the parser is authorized to say before human or
ground-truth validation.

Allowed parser claims:

- Extracted text.
- Page, sheet and row references.
- Section paths and hierarchy candidates.
- Chunk boundaries.
- Table and figure risk signals.
- Metadata candidates.
- Semantic-unit candidates.
- Risk codes.
- Review packet candidates.

Parser non-claims:

- The parser does not publish facts.
- The parser does not decide controlled-document vigency as final truth.
- The parser does not infer graph relationships as active operational truth.
- The parser does not turn benchmark counts into readiness by itself.

Parse output:

- Structured parse artifact.
- Diagnostics.
- Candidate objects.
- Evidence spans.
- Review risks.

Promotion criterion:

```text
input_accepted -> parse_artifact_created
```

The parse artifact can promote only evidence-backed candidates. Unsupported
input, invalid spans, missing provenance, malformed sections or invariant
failures block promotion.

## Contract 3 - Truth Contract

The Truth Contract separates candidate extraction from trusted knowledge.

Truth sources:

- Explicit fixture expectations.
- Human-reviewed decisions.
- Published source and evidence records.
- Ground-truth labels tied to a known corpus.

Diagnostics, not truth:

- Dirty benchmark aggregate scores.
- Regression deltas without expected-output fixtures.
- Low-confidence candidates.
- Table or figure risk counts.
- Review packet counts.

Blocking truth failures:

- Candidate has no source provenance.
- Evidence quote is absent where required.
- Page, sheet or row span is invalid.
- Controlled-document required metadata is missing.
- Revision family has unresolved active conflict.
- Obsolete source is mixed into active operational knowledge.
- Relationship references a missing node.
- A feature promotes a diagnostic into truth without review.

Promotion criterion:

```text
parse_artifact_created -> truth_evaluated
```

After this transition, each finding must be classified as publishable after
review, review-required, diagnostic-only, or blocked.

## Contract 4 - Review Contract

The Review Contract defines what a human must resolve before publication.

Review inputs:

- Metadata ambiguity.
- Revision or vigency conflict.
- Low-confidence semantic unit.
- Section hierarchy ambiguity.
- Table or figure evidence risk.
- Missing source/evidence/provenance.
- Industrial relation uncertainty.
- Prompt injection or unsupported-content risk.

Review packet requirements:

- Stable packet ID.
- Reason code.
- Severity.
- Source and evidence references.
- Suggested human decision.
- Grouping that prevents duplicate noisy items.
- Publication impact.

Review output:

- Approved.
- Rejected.
- Needs more evidence.
- Accepted as warning.
- Blocking gap.

Promotion criterion:

```text
truth_evaluated -> review_resolved
```

Blocking review packets prevent publication. Non-blocking warnings may survive
only if the Publication Contract records them as warnings or gaps.

## Contract 5 - Publication Contract

The Publication Contract defines what becomes active knowledge and what enters
`context_bundle.v1`.

Publishable records:

- Reviewed facts.
- Reviewed rules.
- Reviewed industrial relationships represented as explicit fact or rule types.
- Referenced evidence spans.
- Gaps.
- Tests.
- Memory policy and tool recommendations when produced by the source-pack path.

Publication rules:

- Draft, extracted, rejected and unreviewed records are not active knowledge.
- Published facts/rules must reference published sources.
- Published records must carry evidence or an explicit warning reason.
- `context_bundle.v1` remains strict; no new top-level graph field is allowed.
- Industrial data uses existing bundle sections until a separate compatibility
  decision introduces a new bundle version.

Promotion criterion:

```text
review_resolved -> published_knowledge
```

Publication is blocked by open unknowns, blocking contradictions, missing
source, missing provenance, unresolved industrial blockers or failed
compatibility tests.

## Contract 6 - Release Gate

The Release Gate defines when the Parser is eligible for more capability work,
release hardening or runtime handoff.

Release inputs:

- Parser quality gate.
- Fragility catalog validation.
- Fixture validation.
- Negative and adversarial tests.
- Invariant tests.
- Regression ratchet.
- Dirty benchmark diagnostics.
- Context bundle compatibility tests.
- Smoke and readiness gates.
- Secret scan.

Release interpretation:

- A passing parser quality gate means the parser layers are healthy enough for
  the next agreed slice.
- A passing context bundle gate means publication/export compatibility holds.
- Pilot or readiness gates are end-to-end confidence signals, not substitutes
  for lower contract failures.

Promotion criterion:

```text
published_knowledge -> bundle_exportable -> runtime_importable
```

Any required lower-layer failure blocks release claims. Optional dirty-corpus
absence may be reported as skipped, but it cannot hide required test failures.

## Current Work Repositioning

| Work area | Primary contract | Role in the spine | Repositioning decision |
|-----------|------------------|-------------------|------------------------|
| File validation and source quality reports | Input | Reject unsafe or unusable sources before parsing | Keep as the first hard gate |
| Generic PDF/DOCX/XLSX/CSV/TXT parsers | Parse | Produce text and location references | Keep as parse artifact producers |
| Page profiling and parse diagnostics | Parse | Explain extraction quality and layout risk | Keep diagnostic, not truth |
| Industrial metadata and domain models | Parse, Truth | Produce candidates and validation vocabulary | Require review or fixture truth before publication |
| Section tree, chunking and semantic units | Parse | Shape evidence and candidate extraction | Keep candidate-only until truth/review |
| Table and figure understanding | Parse, Review | Surface evidence risk and review needs | Do not promote visual risk to truth |
| Human review packets | Review | Group uncertain findings into human decisions | Treat as the bridge from truth evaluation to publication |
| Fragility fixtures and adversarial tests | Truth, Release | Define expected behavior and unsafe overclaims | Keep below benchmark and quality gate layers |
| Regression ratchet | Release | Prevent accepted quality from silently drifting | Keep as release control, not product feature |
| Parser quality gate | Release | Orchestrate lower layers transparently | Run before new parser capability work |
| Context bundle export | Publication, Release | Deliver reviewed knowledge to runtime | Keep `context_bundle.v1` strict |
| Readiness and pilot gates | Release | Prove operational confidence | Do not bypass parser/publication contract failures |

TASK-038, if present in a branch, PR or external task tracker, must be mapped
to this table before merge, push or further capability work. If it cannot state
its contract, downstream unlock and promotion criterion, it should be paused or
rewritten.

## State Model

| State | Owner contract | May advance when | Blocks on |
|-------|----------------|------------------|-----------|
| `uploaded_raw` | Input | File is received with provenance | Abuse, missing file metadata |
| `input_accepted` | Input | Security and raw quality checks pass | OCR-required, low text, invalid format |
| `parse_artifact_created` | Parse | Parser emits valid spans and diagnostics | Invalid spans, unsupported extraction, overclaim |
| `truth_evaluated` | Truth | Findings are classified by truth status | Missing evidence, failed fixture, unresolved conflict |
| `review_resolved` | Review | Required packets have human decisions | Blocking packet, missing decision |
| `published_knowledge` | Publication | Reviewed records are active with provenance | Unknowns, contradictions, missing source |
| `bundle_exportable` | Publication, Release | Bundle schema, hash and readiness pass | Blocked readiness, schema drift, unsafe payload |
| `runtime_importable` | Release | Runtime importer can validate and activate | Failed import policy or blocked upstream readiness |

## Sequential Roadmap

### Segment 0 - Freeze And Inventory

Do not add new parser capability. Inventory TASK-023 through the pending
TASK-038 work and classify each item by contract.

Acceptance:

- Every recent parser feature has one primary contract.
- Every quality mechanism is marked as diagnostic, gate or promotion rule.
- No merge/push treats TASK-038 as the automatic next step before mapping.

### Segment 1 - Contract Declarations

Backfill future task templates so every parser task includes:

- Contract affected.
- Downstream contract unlocked.
- State transition.
- Promotion criterion.
- Blocking criterion.
- Verification gate.

Acceptance:

- New task docs cannot be considered ready without those declarations.
- Architecture docs and task docs use the same state names.

### Segment 2 - Promotion Criteria Audit

Audit existing gates against the state model.

Acceptance:

- Input gates prove only input eligibility.
- Parser tests prove only parse claims.
- Truth tests prove expected-output or reviewed claims.
- Review tests prove packet clarity and blocking behavior.
- Publication tests prove bundle compatibility.
- Release gates prove orchestration and readiness.

### Segment 3 - Reposition TASK-038

Map TASK-038 into the spine before merge/push.

Acceptance:

- TASK-038 has an explicit contract.
- TASK-038 explains which downstream contract it unlocks.
- TASK-038 does not combine unrelated contract work.
- Any useful implementation already done by TASK-038 is kept only if its place
  in the spine is clear.

### Segment 4 - Resume Vertical Capability Work

After the consolidation passes, new capability work should be vertical, even if
thin.

Required shape:

```text
input case
-> parse artifact
-> truth evaluation
-> review decision or explicit non-review reason
-> publication mapping
-> release gate
```

The slice may be small, but it must travel through the spine.

## Non-Goals

- No new parser extraction feature.
- No new benchmark metric.
- No new readiness script.
- No new UI.
- No bundle schema version change.
- No runtime importer change.
- No Hermes, Tri-Memory or agent memory dependency.

## Review Checklist

- The feature has one primary contract.
- The feature does not promote candidates into truth.
- The feature has a downstream unlock.
- The feature names the state transition it affects.
- The feature has a blocking criterion.
- The feature has a verification gate tied to the right contract.
- The feature preserves `context_bundle.v1` unless a separate compatibility
  decision changes it.
