# Grounding Worker Design

Status: proposed
Date: 2026-06-15

## Purpose

Grounding closes the current gap between structured extraction and trusted
truth evaluation. The extraction worker may produce valid JSON with valid
schema fields, but that does not prove the extracted claim is literally
supported by the source chunk. This design adds a grounding stage before
confidence calibration and before any extracted item is treated as a reliable
candidate for publication.

Grounding belongs to the Truth Contract from
`docs/02-architecture/PARSER_ARCHITECTURE_SPINE.md`. It promotes or blocks the
transition:

```text
parse_artifact_created -> truth_evaluated
```

It does not publish knowledge, replace human review, or calibrate confidence.

## Core Rule

Grounding has two checks, always in this order:

1. Deterministic evidence check.
2. Independent entailment check.

The deterministic check is mandatory because `evidence_quote` can be generated
by the extraction model. The system must prove that the quoted evidence is
literal source text before asking any model whether the source supports the
claim.

Check A proves the evidence text exists in the source. Check B proves the
source supports the claim. A narrow quote is not enough to prove support, because
negation, scope, exceptions, and conditions may live outside the selected words.

## Check A - Deterministic Evidence

Input:

- `chunk_text`
- `evidence_quote`
- `evidence_char_start`
- `evidence_char_end`

Behavior:

- The comparison normalizes both sides before matching:
  - Unicode NFC.
  - canonical quote characters.
  - non-breaking spaces converted to regular spaces.
  - repeated whitespace collapsed to one space.
  - leading and trailing whitespace removed.
- If offsets are present, `chunk_text[char_start:char_end]` must match
  `evidence_quote` after the comparison normalization above.
- If offsets are absent, `evidence_quote` must match a substring of
  `chunk_text` after the comparison normalization above.
- Empty evidence fails.
- Invalid offset ordering fails.
- Out-of-range offsets fail.
- Ambiguous repeated substrings may pass when offsets are absent, but the
  result records `offset_status = "substring_without_offsets"` so later
  hardening can require offsets for high-stakes types.
- The result records `match_mode = "exact"` when raw text matches without
  normalization and `match_mode = "normalized"` when the normalized comparison
  passes. `match_mode = "fuzzy"` is reserved for future OCR/WhatsApp modality
  support and is not implemented in this slice.

Output:

- `deterministic_status`: `passed` or `failed`
- `deterministic_reason`
- `match_mode`: `exact`, `normalized`, or future `fuzzy`
- `offset_status`
- canonical `verified_quote`
- canonical offsets when available or recoverable

Check A is deterministic code and has no model dependency.

## Check B - Independent Entailment

Input:

- structured claim payload
- `fact_type` or `rule_type`
- `chunk_text`
- `verified_quote`
- source location metadata

The entailment verdict is judged against the entire `chunk_text`. The verified
quote is a highlighted locus, not the full evidence universe. The verifier must
honor negation, local scope, exceptions, temporal qualifiers, and conditional
language in the surrounding chunk. For example, a quote such as
`"desconto de 20%"` must not ground a claim that a 20 percent discount is
allowed when the chunk says the discount is not offered.

The entailment verifier must not receive:

- extraction chain-of-thought
- extraction rationale
- extraction prompt internals
- model self-reported confidence as an instruction

The verifier asks whether the source text semantically supports the structured
claim. It must not require normalized strings to appear literally in the source.
For example, if deterministic normalization converted "junho" into an ISO date,
grounding checks whether the source supports the month-level meaning; the
normalizer's own tests are responsible for proving that the ISO conversion is
correct. The verifier is adversarial to the extractor, not a helper trying to
justify it.

Output:

- `entailment_status`: `passed`, `failed`, or `abstained`
- `entailment_reason`
- `grounding_model`
- `grounding_prompt_version`
- `latency_ms`
- token and cost metadata

`abstained` is treated as not grounded for required-grounding types.

## Stakes Config

The list of types requiring hard grounding is configuration, not worker logic.
This preserves the core/adapter boundary.

Initial default config:

```json
{
  "default": {
    "required_grounding_types": [
      "business_rules",
      "service_price"
    ],
    "warn_only_grounding_types": [
      "business_hours",
      "payment_method",
      "contact_info",
      "faq_item"
    ]
  },
  "industrial": {
    "required_grounding_types": [
      "business_rules",
      "service_price",
      "controlled_document_metadata",
      "industrial_requirement"
    ],
    "warn_only_grounding_types": [
      "industrial_responsibility",
      "industrial_relation"
    ]
  }
}
```

The implementation may start with a Python module config or JSON file. It must
be loaded through a small interface so tenant or vertical adapters can replace
it later without changing worker code.

## Persistence

The grounding result must be persisted separately from extraction content.
The first implementation should prefer additive fields or a side table instead
of changing published bundle contracts.

Required persisted fields:

- `grounding_status`: `not_required`, `passed`, `failed`, or `abstained`
- `grounding_required`: boolean
- `grounding_reason`
- `deterministic_status`
- `deterministic_reason`
- `match_mode`
- `offset_status`
- `entailment_status`
- `entailment_reason`
- `grounding_model`
- `grounding_prompt_version`
- `grounding_checked_at`

Facts and rules should remain compatible with `context_bundle.v1`; grounding
metadata is a review and publication safety signal, not a new bundle top-level
contract.

## Failure Routing

For required-grounding types:

- Check A failure routes to review/unknown with reason
  `grounding_evidence_not_literal`.
- Check B failure routes to review/unknown with reason
  `grounding_entailment_failed`.
- Check B abstention routes to review/unknown with reason
  `grounding_abstained`.
- Failed or abstained items must not be treated as reliable extracted records.

For warn-only types:

- The item may remain extracted, but the grounding result must be visible to
  review and publication gates.
- Publication can later decide whether warnings block export.

## Gold Slice Before Hard Gate

Before hard grounding blocks production flow, create a labeled grounding gold
slice with 50 to 100 judgments.

Each case contains:

- `case_id`
- `fact_type` or `rule_type`
- structured claim
- `chunk_text`
- evidence quote and offsets
- expected deterministic verdict
- expected entailment verdict
- human label reason

Metrics:

- deterministic check false pass count must be zero on the gold slice
- deterministic check false fail rate
- entailment precision by required type
- entailment recall by required type
- abstention rate

The verifier should not become a hard gate until the gold slice shows acceptable
precision and review agrees the failure modes are understandable.

The gold slice must also set an explicit abstention-rate ceiling before hard
gating. A verifier that abstains on most difficult cases is not production-useful
even if it looks safe. The initial target is:

- deterministic false pass count: `0`
- deterministic false fail rate: `<= 2%`
- entailment precision for required-grounding types: `>= 95%`
- entailment recall for required-grounding types: `>= 90%`
- abstention rate: `<= 10%`

These thresholds may be adjusted only through a documented Truth Contract
decision after reviewing labeled failures.

## Pipeline Placement

The grounding stage runs after extraction schema validation and deterministic
normalization, and before records are promoted as reliable candidates for review
or publication.

Sequence:

```text
classification
-> extraction
-> schema validation
-> normalization
-> grounding Check A
-> grounding Check B when Check A passes and type requires or requests it
-> persist extraction plus grounding result
-> route to extracted or needs_review
```

This design does not require moving classification or extraction. It adds a
truth-evaluation gate to the existing worker flow.

## Re-Grounding And Caching

A grounding result is valid only for the claim payload, evidence text,
`grounding_prompt_version`, grounding model, and stakes config version that
produced it. When the verifier prompt, model, or required-grounding config
changes, affected records must be eligible for re-grounding just as prompt
changes make records eligible for re-extraction.

Before calling the entailment model, the worker should deduplicate by a stable
hash of:

```text
fact_or_rule_type + normalized_claim_payload + verified_quote + grounding_prompt_version + grounding_model
```

This avoids repeated B-check calls for identical claims and evidence. The cache
must not skip Check A, because Check A also validates offsets and source-local
evidence integrity for the current chunk.

## Structured Output Timing

Native provider structured output is valuable, but it does not replace
grounding. It can reduce parse failures and malformed responses, while
grounding catches well-formed JSON with unsupported content.

Structured output may proceed in parallel after the grounding design is accepted,
but confidence calibration must wait until grounding exists because grounding is
a primary confidence feature.

## Entity Registry Timing

Canonical entity registry work is not part of this slice. It becomes urgent
when conflict detection expands beyond exact numeric matching, because entity
normalization failures create false contradictions.

This grounding slice should avoid introducing a new entity registry dependency.

## Metrics Interpretation

Until OCR and WhatsApp-like inputs exist in the pipeline, precision and recall
numbers describe the current clean-document subset. They are optimistic upper
bounds, not production-wide quality claims.

Grounding metrics must report the input modality or corpus slice they came from.

## Non-Goals

- Confidence calibration or ECE.
- Entity registry implementation.
- OCR or WhatsApp ingestion.
- Context bundle schema version changes.
- Automatic publication.
- Replacing human review.
- Full provider-native structured outputs.

## Acceptance Criteria

- Grounding is documented as Truth Contract work.
- The deterministic evidence check is mandatory and runs before entailment.
- The deterministic evidence check uses defined typographic normalization and
  records `match_mode`.
- The grounding gold slice measures deterministic false fails as well as false
  passes.
- Entailment verification is independent and does not receive extractor
  rationale.
- Entailment is judged against the whole chunk, with the quote as highlighted
  locus, and must honor negation, scope, exceptions, temporal qualifiers, and
  conditionals.
- Entailment verifies semantic support for normalized claims rather than literal
  string equality for deterministic normalization outputs.
- Required grounding types are loaded from stakes config, not hardcoded in the
  worker.
- Required-grounding failures route to review/unknown and do not become
  reliable extracted records.
- A grounding gold slice is defined before hard gating production flow.
- The gold slice has an explicit abstention-rate ceiling.
- Grounding results are versioned for re-grounding when verifier prompt, model,
  or stakes config changes.
- Entailment calls are deduplicated by stable claim/evidence/verifier hash.
- Calibration is explicitly sequenced after grounding.
- `context_bundle.v1` compatibility is preserved.
