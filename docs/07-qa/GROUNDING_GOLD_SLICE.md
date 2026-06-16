# Grounding Gold Slice Runbook

Status: implemented (starter slice — below the 50-100 target, expand before hard gating)
Related: `docs/03-pipeline/GROUNDING_WORKER.md`, `tasks/TASK-040-grounding-worker.md`

## Purpose

The grounding gold slice measures the grounding stage against a committed,
human-labeled corpus **before** hard grounding is allowed to block production
flow. It answers two questions deterministically in CI:

1. Does the deterministic evidence check (Check A) ever pass evidence it should
   reject? (`false_pass_count` must be `0`.)
2. Is the metric harness for entailment precision/recall/abstention correct and
   reproducible?

Check A runs for real via `grounding.verify_evidence`. Check B is judged by a
verifier; in CI that verifier is a deterministic **stub** so the run is
reproducible. Real entailment precision/recall require running the slice against
a live provider locally — the CI numbers describe the `clean_document` subset
with a perfect stub and are an optimistic upper bound.

## Commands

```powershell
# Report only (non-blocking signal; always exits 0 unless the manifest is invalid):
uv run --cache-dir .uv-cache python scripts\quality\grounding_gold_eval.py

# Enforce the thresholds (exit 1 when any gate is below threshold):
uv run --cache-dir .uv-cache python scripts\quality\grounding_gold_eval.py --enforce

# Industrial stakes profile:
uv run --cache-dir .uv-cache python scripts\quality\grounding_gold_eval.py --profile industrial

# Tests:
uv run --cache-dir .uv-cache pytest tests\smoke\test_grounding_gold_eval.py -q
```

Exit codes: `0` pass, `1` evaluated gate failure (only with `--enforce`), `2`
invalid input (missing/malformed manifest).

## Manifest shape

`examples/grounding_gold/manifest.json`, schema `grounding_gold_manifest.v1`.
Each case:

| field | required | meaning |
|-------|----------|---------|
| `case_id` | yes | unique stable id |
| `fact_type` | yes | drives required vs warn-only via the stakes config |
| `claim` | no | structured claim payload (context only in CI) |
| `chunk_text` | yes | the full source chunk Check A/B see |
| `evidence_quote` | yes | the quote under test |
| `evidence_char_start` / `evidence_char_end` | no | offsets; omit to test substring matching |
| `expected_deterministic` | yes | `passed` or `failed` — anchored to `grounding.verify_evidence` |
| `expected_entailment` | no | human label: `passed` / `failed` / `abstained` / `null` |
| `stub_entailment` | no | simulated verifier prediction for the CI metric harness; defaults to `expected_entailment` |
| `modality` | no | corpus tag (e.g. `clean_document`); reported with every metric |
| `label_reason` | no | why the human labeled it this way |

`expected_deterministic` **must** match what `grounding.verify_evidence` returns
for the case, otherwise the case manufactures a false pass/fail. Verify with:

```powershell
uv run --cache-dir .uv-cache python -c "import json; from grounding import verify_evidence; m=json.load(open('examples/grounding_gold/manifest.json',encoding='utf-8')); [print(c['case_id']) for c in m['cases'] if verify_evidence(c['chunk_text'],c['evidence_quote'],c.get('evidence_char_start'),c.get('evidence_char_end')).deterministic_status!=c['expected_deterministic']]"
```

## Gates

Reported always; enforced only with `--enforce` (design "Gold Slice Before Hard
Gate"):

| gate | threshold |
|------|-----------|
| `deterministic_false_pass` | `= 0` |
| `deterministic_false_fail_rate` | `<= 0.02` |
| `entailment_precision` (required types) | `>= 0.95` |
| `entailment_recall` (required types) | `>= 0.90` |
| `abstention_rate` (required types) | `<= 0.10` |

Entailment metrics are scoped to required-grounding types (from the stakes
config) that carry an `expected_entailment` label.

## Adding cases without committing private documents

- Keep `chunk_text` to short, synthetic, non-confidential snippets. Never paste
  a real customer/industrial document into the manifest.
- Cover all failure modes: positive, negation, scope/exception, conditional,
  temporal qualifier, normalized-claim, ambiguous substring, bad offsets,
  non-literal evidence.
- Tag every case with `modality` so metrics stay honest per corpus.
- Re-run the anchor check above so `expected_deterministic` stays truthful.

## Promotion: warn-only → hard gate

The grounding stage ships warn-only and flag-gated (`GROUNDING_ENABLED` off by
default). To promote required-grounding types to hard routing:

1. Grow the slice toward 50-100 labeled cases across the required types.
2. Run `--enforce` (ideally with a real verifier locally) and confirm all five
   gates pass.
3. Review the labeled failures with a human; confirm the failure modes are
   understandable.
4. Record the decision as a Truth Contract note, then enable `GROUNDING_ENABLED`
   and (if desired) wire `--enforce` into the quality gate.

Thresholds may only change through a documented Truth Contract decision after
reviewing labeled failures.
