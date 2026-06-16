# TASK-040 - Grounding Worker (Truth Evaluation Gate)

Status: implemented

## Goal

Add a grounding stage between extraction normalization and reliable-candidate
promotion. Grounding proves that an extracted claim is (A) backed by evidence
text that literally exists in the source chunk and (B) semantically supported by
the surrounding chunk. It is the implementation of the
`parse_artifact_created -> truth_evaluated` transition in the Truth Contract.

Design of record: `docs/03-pipeline/GROUNDING_WORKER.md`.

## Background

The extraction worker (`workers/extraction`) today produces schema-valid,
normalized facts/rules and stores the model-supplied `evidence_quote` without
ever proving the quote is literal source text
(`workers/extraction/src/worker_extraction/evidence.py` only strips whitespace).
There is no entailment check, no stakes config, no grounding persistence, and no
grounding gold slice. The Truth Contract
(`docs/02-architecture/PARSER_ARCHITECTURE_SPINE.md`) already names "evidence
quote absent where required" and "feature promotes a diagnostic into truth
without review" as blocking failures, but nothing enforces them at extraction
time. This task closes that gap.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Owns sequencing, the core/adapter boundary, and cross-task integration; keeps the slice inside the design's Non-Goals. |
| Task Worker | Uses TDD, edits only assigned files per task, writes red tests before code. |
| Spec Reviewer | Confirms each task matches `docs/03-pipeline/GROUNDING_WORKER.md` acceptance criteria and adds no out-of-scope capability. |
| Code Reviewer | Checks determinism of Check A, prompt isolation of Check B, tenant safety, idempotency, migration rollback, and log hygiene. |
| Adversarial Verifier | For Check B design and gold slice: tries to make a narrow-quote claim pass against a chunk that negates it; confirms the verifier refuses. |
| Approval | Runs focused tests, lint, type checks, secret scan, and the grounding gold-slice eval. |

## Scope

- New `packages/grounding` package:
  - deterministic Check A evidence verifier;
  - stakes config loader (default + industrial profiles);
  - stable grounding cache/re-grounding hash;
  - Check B entailment verifier (model-backed, isolated prompt);
  - a `run_grounding` orchestrator returning a single `GroundingResult`.
- Additive grounding persistence (side table `grounding_results`) plus RPC wiring
  in the extraction completion path; no change to `context_bundle.v1`.
- Extraction worker integration behind a config flag, warn-only first, with
  failure routing to `needs_review`/unknown for required-grounding types.
- A committed grounding gold slice (50-100 cases) and a deterministic evaluator
  CLI with explicit precision/recall/abstention gates.
- Runbook and execution evidence.

## Out Of Scope

- Confidence calibration or ECE (sequenced strictly after this task).
- Entity/canonical registry.
- OCR or WhatsApp ingestion and `match_mode = "fuzzy"`.
- `context_bundle.v2` or any change to published bundle top-level contract.
- Automatic publication or replacing human review.
- Full provider-native structured outputs.
- Hard gating production flow before the gold slice meets thresholds.

## Proposed Files

Create:

- `packages/grounding/pyproject.toml`
- `packages/grounding/src/grounding/__init__.py`
- `packages/grounding/src/grounding/types.py`
- `packages/grounding/src/grounding/evidence_check.py` (Check A)
- `packages/grounding/src/grounding/config.py` + `stakes_config.json`
- `packages/grounding/src/grounding/cache.py` (re-grounding hash)
- `packages/grounding/src/grounding/entailment.py` (Check B)
- `packages/grounding/src/grounding/runner.py` (A then B orchestration)
- `packages/grounding/src/grounding/prompt.py` + versioned entailment prompt
- `packages/grounding/tests/test_evidence_check.py`
- `packages/grounding/tests/test_config.py`
- `packages/grounding/tests/test_cache.py`
- `packages/grounding/tests/test_entailment.py`
- `packages/grounding/tests/test_runner.py`
- `supabase/migrations/049_grounding_results.sql`
- `examples/grounding_gold/manifest.json` + labeled case fixtures
- `scripts/quality/grounding_gold_eval.py`
- `tests/smoke/test_grounding_gold_eval.py`
- `docs/07-qa/GROUNDING_GOLD_SLICE.md`
- `docs/superpowers/plans/2026-06-15-grounding-worker-sdd.md`

Modify:

- `packages/model_gateway/src/model_gateway/base.py` (+ clients): add
  `verify_entailment` contract for prompt-isolated grounding calls.
- `workers/extraction/src/worker_extraction/tasks.py`: call grounding after
  normalization/evidence and before persist; route failures.
- `workers/extraction/src/worker_extraction/db.py` + extraction RPC: persist
  `grounding_results` atomically with the extraction completion.

## Acceptance

- Check A is pure deterministic code with no model dependency, applies the
  defined typographic normalization, records `match_mode` and `offset_status`,
  fails empty/invalid/out-of-range offsets, and emits a canonical
  `verified_quote`.
- Check B receives only claim payload, `fact_type`/`rule_type`, full
  `chunk_text`, `verified_quote`, and location metadata - never extractor
  rationale, prompt internals, or model self-confidence as instruction.
- Check B judges against the whole chunk and honors negation, scope, exceptions,
  temporal qualifiers, and conditionals; verifies semantic support for
  normalized claims rather than literal equality of normalized strings.
- Required-grounding types are loaded from stakes config, not hardcoded.
- Required-grounding Check A failure -> `grounding_evidence_not_literal`;
  Check B failure -> `grounding_entailment_failed`; abstention ->
  `grounding_abstained`; all route to `needs_review`/unknown and do not become
  reliable extracted records.
- Warn-only types remain `extracted` but persist a visible grounding result.
- Grounding result persists every field in the design's persistence list,
  additively, with `context_bundle.v1` unchanged.
- Entailment calls deduplicate by the stable
  `type + normalized_claim + verified_quote + prompt_version + model` hash; the
  cache never skips Check A.
- A grounding gold slice of 50-100 labeled cases exists; the evaluator reports
  deterministic false-pass = 0, false-fail rate, entailment precision/recall by
  required type, and abstention rate, each tagged with corpus/modality.
- Hard gating remains off until the gold slice meets: deterministic false-pass
  `= 0`, deterministic false-fail `<= 2%`, entailment precision `>= 0.95`,
  recall `>= 0.90`, abstention `<= 0.10`.
- Worker integration is idempotent, tenant-checked, and re-runnable when prompt,
  model, or stakes config version changes.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest packages\grounding\tests -q
uv run --cache-dir .uv-cache pytest workers\extraction\tests -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_grounding_gold_eval.py -q
uv run --cache-dir .uv-cache python scripts\quality\grounding_gold_eval.py
uv run --cache-dir .uv-cache ruff check packages\grounding scripts\quality\grounding_gold_eval.py
uv run --cache-dir .uv-cache mypy --ignore-missing-imports packages\grounding\src\grounding
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [x] Commit design doc and SDD plan.
- [x] Check A: red tests, then deterministic evidence verifier.
- [x] Stakes config loader (default + industrial) behind a small interface.
- [x] Re-grounding cache hash.
- [x] `grounding_results` migration + RPC + db wiring.
- [x] Gateway `verify_entailment` contract (+ stub/clients).
- [x] Check B entailment verifier with isolated, versioned prompt.
- [x] `run_grounding` orchestrator (A then B, stakes-aware).
- [x] Extraction worker integration, warn-only, with failure routing.
- [x] Grounding gold slice corpus + evaluator CLI + gates.
- [x] Runbook + execution evidence.
- [x] Adversarial verifier pass on Check B (workflow phase).
- [ ] Grow gold slice to 50-100 cases and flip required types to hard gate
      (deferred — see GROUNDING_GOLD_SLICE.md promotion procedure).

## Execution Evidence

Implemented 2026-06-15 via SDD multi-agent workflow (`grounding-worker-sdd`,
run `wf_0bc638d0-f97`) plus a main-loop completion pass for the four agents that
hit a provider session limit (worker integration, gold slice, docs, final verify).

Final verification (worktree `ecstatic-tharp-ede72e`):

```
uv run --cache-dir .uv-cache pytest packages/grounding/tests packages/model_gateway/tests \
  workers/extraction/tests tests/smoke/test_grounding_gold_eval.py -q
  -> 152 passed

uv run --cache-dir .uv-cache python scripts/quality/grounding_gold_eval.py
  -> exit 0; deterministic false_pass_count = 0; gates_passed = true (stub verifier,
     clean_document modality); slice = 20 cases (starter, below 50-100 target)

uv run --cache-dir .uv-cache ruff check packages/grounding scripts/quality/grounding_gold_eval.py \
  workers/extraction/src/worker_extraction/grounding.py            -> All checks passed!
uv run --cache-dir .uv-cache mypy --ignore-missing-imports packages/grounding/src/grounding
  -> Success: no issues found in 8 source files
uv run --cache-dir .uv-cache mypy --ignore-missing-imports \
  workers/extraction/src/worker_extraction/grounding.py workers/extraction/src/worker_extraction/tasks.py
  -> Success: no issues found in 2 source files
uv run --cache-dir .uv-cache python scripts/ci/secret_scan.py     -> exit 0
```

Notes:

- The grounding stage ships warn-only and flag-gated (`GROUNDING_ENABLED`, default
  off); current extraction behavior is unchanged until the flag is set.
- `context_bundle.v1` is unchanged; grounding persists additively in
  `grounding_results` (migration 049) via the extended `complete_extraction_job` RPC.
- Adding `packages/grounding` to the uv workspace may require a one-time
  `uv sync --all-packages` on a clean checkout before `uv run` resolves the new member.
