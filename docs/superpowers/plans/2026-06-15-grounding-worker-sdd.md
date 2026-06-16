# Grounding Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the grounding stage from `docs/03-pipeline/GROUNDING_WORKER.md`: a deterministic evidence check (Check A) plus an independent entailment check (Check B), wired into the extraction worker as the `parse_artifact_created -> truth_evaluated` gate, and validated by a committed grounding gold slice before any hard gating.

**Architecture:** Add a self-contained `packages/grounding` package holding pure Check A, stakes config, re-grounding hash, Check B verifier, and a `run_grounding` orchestrator. Persist results additively in a new `grounding_results` side table written atomically by the extraction completion RPC. The extraction worker calls grounding after normalization/evidence and before promotion, warn-only first, routing required-grounding failures to `needs_review`. A deterministic `grounding_gold_eval.py` CLI measures precision/recall/abstention before the gate is allowed to block.

**Tech Stack:** Python 3.13 via `uv`, pytest, Pydantic v2, existing `model_gateway` and `normalizers` packages, Supabase/Postgres SQL RPC, JSON manifests. No OCR, no calibration, no entity registry, no `context_bundle.v2`.

---

## Execution Model (Multi-Agent SDD)

Six roles. The Orchestrator drives; workers/reviewers run as subagents.

1. **Orchestrator** - owns scope, sequencing, the core/adapter boundary, and integration. Splits work, dispatches Task Workers, and runs the review loop after each task.
2. **Task Worker** - TDD per task: writes red tests, then minimal code, edits only that task's files.
3. **Spec Reviewer** - checks the task against `docs/03-pipeline/GROUNDING_WORKER.md` acceptance and `TASK-040`; rejects scope creep into Non-Goals.
4. **Code Reviewer** - checks Check A determinism, Check B prompt isolation, tenant safety, idempotency, migration rollback, log hygiene (no chunk text / PII in logs).
5. **Adversarial Verifier** - tries to defeat Check B: narrow-quote claims that the surrounding chunk negates, scopes away, or makes conditional. Confirms the verifier fails/abstains rather than rubber-stamps.
6. **Approval** - runs the Verification Target, gold-slice eval, lint, types, secret scan.

**Parallelization** (after Task 0):
- Stream 1 (deterministic, no model): Task 1 (Check A) -> Task 2 (config) -> Task 3 (cache).
- Stream 2 (persistence): Task 4 (migration + RPC + db).
- Stream 3 (model contract): Task 5 (gateway `verify_entailment`) -> Task 6 (Check B).
- Streams 1-3 run concurrently. Task 7 (orchestrator) joins Streams 1+3. Task 8 (worker integration) joins Tasks 7+4. Task 9 (gold slice) depends on Tasks 1+7. Task 10 (docs) last.

Do not introduce OCR, vision, calibration/ECE, entity registry, `match_mode = "fuzzy"`, or `context_bundle` schema changes.

## File Map

Create:

- `packages/grounding/pyproject.toml`
- `packages/grounding/src/grounding/__init__.py`
- `packages/grounding/src/grounding/types.py`: dataclasses/enums (`DeterministicResult`, `EntailmentResult`, `GroundingResult`, status literals).
- `packages/grounding/src/grounding/evidence_check.py`: Check A.
- `packages/grounding/src/grounding/config.py` + `packages/grounding/src/grounding/stakes_config.json`: stakes loader.
- `packages/grounding/src/grounding/cache.py`: stable grounding hash.
- `packages/grounding/src/grounding/prompt.py` + entailment prompt asset: Check B prompt + `get_grounding_prompt_version`.
- `packages/grounding/src/grounding/entailment.py`: Check B verifier.
- `packages/grounding/src/grounding/runner.py`: `run_grounding`.
- `packages/grounding/tests/test_evidence_check.py`, `test_config.py`, `test_cache.py`, `test_entailment.py`, `test_runner.py`.
- `supabase/migrations/049_grounding_results.sql`.
- `examples/grounding_gold/manifest.json` + labeled fixtures.
- `scripts/quality/grounding_gold_eval.py`.
- `tests/smoke/test_grounding_gold_eval.py`.
- `docs/07-qa/GROUNDING_GOLD_SLICE.md`.

Modify:

- `packages/model_gateway/src/model_gateway/base.py` (+ `ollama_client.py`, `openai_client.py`, `anthropic_client.py`): add `verify_entailment`.
- `workers/extraction/src/worker_extraction/tasks.py`: grounding call + routing.
- `workers/extraction/src/worker_extraction/db.py` + `supabase/migrations/032_extraction_rpc.sql` successor: persist grounding atomically.
- `tasks/TASK-040-grounding-worker.md`: execution evidence.

## Task 0: Commit Design And Plan

**Files:**
- Confirm: `docs/03-pipeline/GROUNDING_WORKER.md`
- Confirm: `tasks/TASK-040-grounding-worker.md`
- Confirm: `docs/superpowers/plans/2026-06-15-grounding-worker-sdd.md`

- [ ] **Step 1: Verify design of record is committed** and that `TASK-040` and this plan reference it. No code yet. Spec Reviewer confirms acceptance criteria are testable.

## Task 1: Check A - Deterministic Evidence (TDD)

**Files:**
- Create: `packages/grounding/pyproject.toml`, `__init__.py`, `types.py`
- Create: `packages/grounding/src/grounding/evidence_check.py`
- Create: `packages/grounding/tests/test_evidence_check.py`

- [ ] **Step 1: Red tests for the normalization + match matrix**

Write failing tests asserting `verify_evidence(chunk_text, quote, char_start, char_end)` returns a `DeterministicResult`:

- exact raw match -> `passed`, `match_mode = "exact"`.
- match only after NFC / curly-quote / NBSP / collapsed-whitespace / trim normalization -> `passed`, `match_mode = "normalized"`.
- empty quote -> `failed`, reason names empty evidence.
- `char_start > char_end` or negative -> `failed`, invalid ordering.
- offsets out of range for `chunk_text` -> `failed`.
- offsets present but slice != quote after normalization -> `failed`.
- offsets absent, quote is a substring -> `passed`, `offset_status = "substring_without_offsets"`.
- offsets absent, quote repeated twice -> `passed` but flagged ambiguous via `offset_status`.
- `verified_quote` is the canonical (normalized) form; recovered canonical offsets present when derivable.

- [ ] **Step 2: Run red tests**

```powershell
uv run --cache-dir .uv-cache pytest packages\grounding\tests\test_evidence_check.py -q
```

Expected: FAIL (module absent).

- [ ] **Step 3: Implement `evidence_check.py`** as pure functions: a `_normalize` helper (Unicode NFC, canonical quotes, NBSP->space, whitespace collapse, trim) and `verify_evidence` returning `DeterministicResult`. No model imports. Define result/enum types in `types.py`.

- [ ] **Step 4: Run green tests** (same command). Expected: PASS. Code Reviewer confirms determinism and zero model dependency.

## Task 2: Stakes Config Loader (TDD)

**Files:**
- Create: `packages/grounding/src/grounding/config.py`, `stakes_config.json`
- Create: `packages/grounding/tests/test_config.py`

- [ ] **Step 1: Red tests** for `load_stakes_config(profile)` returning required/warn-only sets, with `default` and `industrial` profiles from the design; `grounding_mode(fact_type, profile)` returns `"required" | "warn_only" | "not_configured"`; unknown profile falls back to `default`; config is loaded through a replaceable interface (a `StakesConfigProvider` protocol) so adapters can override without editing worker code. Include a `config_version` field used by the cache.

- [ ] **Step 2: Run red, implement loader + JSON, run green.**

```powershell
uv run --cache-dir .uv-cache pytest packages\grounding\tests\test_config.py -q
```

Spec Reviewer confirms types are config-driven, never hardcoded in worker logic.

## Task 3: Re-Grounding Cache Hash (TDD)

**Files:**
- Create: `packages/grounding/src/grounding/cache.py`
- Create: `packages/grounding/tests/test_cache.py`

- [ ] **Step 1: Red tests** for `grounding_key(...)` = stable sha256 over `fact_or_rule_type + normalized_claim_payload + verified_quote + grounding_prompt_version + grounding_model`. Assert: identical inputs -> identical key; payload key-order/whitespace differences canonicalize to the same key; changing prompt version, model, or claim changes the key. Document that the key gates Check B only - Check A always re-runs.

- [ ] **Step 2: Run red, implement, run green.**

```powershell
uv run --cache-dir .uv-cache pytest packages\grounding\tests\test_cache.py -q
```

## Task 4: Grounding Persistence (Migration + RPC + DB)

**Files:**
- Create: `supabase/migrations/049_grounding_results.sql`
- Modify: successor RPC of `supabase/migrations/032_extraction_rpc.sql`
- Modify: `workers/extraction/src/worker_extraction/db.py`

- [ ] **Step 1: Write migration** creating `grounding_results` with `workspace_id` (RLS, tenant-scoped), `source_id`, `chunk_id`, optional `fact_id`/`rule_id`, and every persistence field from the design (`grounding_status`, `grounding_required`, `grounding_reason`, `deterministic_status`, `deterministic_reason`, `match_mode`, `offset_status`, `entailment_status`, `entailment_reason`, `grounding_model`, `grounding_prompt_version`, `grounding_checked_at`, plus `grounding_key`, `config_version`). Add RLS policies matching sibling tables, an index on `grounding_key`, and a rollback section. Do **not** alter `extracted_facts`/`business_rules` published columns or `context_bundle.v1`.

- [ ] **Step 2: Extend `complete_extraction_job` RPC** to accept an optional `grounding_result jsonb` and insert it atomically in the same transaction as the fact/rule/evidence rows (security definer, `search_path = public`, workspace-checked).

- [ ] **Step 3: Wire `db.py`** to pass the grounding payload through. Add focused tests/fakes in `workers/extraction/tests` mirroring existing `test_extraction_db.py` style. Code Reviewer checks rollback, RLS, and that no chunk text is stored beyond what the design allows.

## Task 5: Gateway `verify_entailment` Contract

**Files:**
- Modify: `packages/model_gateway/src/model_gateway/base.py`, `ollama_client.py`, `openai_client.py`, `anthropic_client.py`
- Modify: `packages/model_gateway/tests/` (add coverage)

- [ ] **Step 1: Red test** for a new abstract `verify_entailment(claim_payload, fact_type, chunk_text, verified_quote, location, prompt_template, prompt_version, config)` returning an `EntailmentResponse` (verdict text + tokens/latency/cost/provider/hash), mirroring `ExtractionResponse`. The contract must accept only grounding inputs - no extractor rationale field exists on the signature.

- [ ] **Step 2: Implement** the abstract method on `base.py` and the three clients (Ollama for local/CI determinism via a stubbable path; OpenAI/Anthropic native). Keep temperature 0. Run gateway tests green.

```powershell
uv run --cache-dir .uv-cache pytest packages\model_gateway\tests -q
```

## Task 6: Check B - Independent Entailment (TDD)

**Files:**
- Create: `packages/grounding/src/grounding/prompt.py` + prompt asset
- Create: `packages/grounding/src/grounding/entailment.py`
- Create: `packages/grounding/tests/test_entailment.py`

- [ ] **Step 1: Red tests** with a fake gateway:

- supported claim -> `entailment_status = "passed"`.
- chunk negates the quoted value (the design's "desconto de 20% ... não oferecido" case) -> `failed`.
- claim depends on a condition/exception elsewhere in the chunk -> `failed`.
- normalized claim (e.g. ISO date from "junho") is semantically supported even though the ISO string is absent literally -> `passed`.
- model returns malformed/unsure verdict -> `abstained`.
- assert the prompt builder **never** includes extractor rationale, prompt internals, or self-reported confidence (inspect the rendered prompt string).

- [ ] **Step 2: Run red, implement `entailment.py` + versioned prompt, run green.**

```powershell
uv run --cache-dir .uv-cache pytest packages\grounding\tests\test_entailment.py -q
```

Adversarial Verifier reviews the prompt and the negation/scope fixtures.

## Task 7: `run_grounding` Orchestrator (TDD)

**Files:**
- Create: `packages/grounding/src/grounding/runner.py`
- Create: `packages/grounding/tests/test_runner.py`

- [ ] **Step 1: Red tests** for `run_grounding(claim, fact_type, chunk_text, evidence, profile, gateway, cache=...)` returning a single `GroundingResult`:

- type not in config -> `grounding_status = "not_required"`, `grounding_required = False`, Check B skipped.
- Check A fails on a required type -> status `failed`, reason `grounding_evidence_not_literal`, Check B skipped.
- Check A passes, Check B fails (required) -> `failed`, reason `grounding_entailment_failed`.
- Check B abstains (required) -> `abstained`, reason `grounding_abstained`.
- warn-only type with Check B failure -> result records the warning but does not mark the item unreliable.
- identical claim+evidence twice -> Check B called once (cache hit), Check A run both times.

- [ ] **Step 2: Run red, implement orchestrator, run green.**

```powershell
uv run --cache-dir .uv-cache pytest packages\grounding\tests -q
```

## Task 8: Extraction Worker Integration (Warn-Only First)

**Files:**
- Modify: `workers/extraction/src/worker_extraction/tasks.py`
- Create: `workers/extraction/src/worker_extraction/grounding.py` (thin adapter)
- Modify: `workers/extraction/tests/test_extraction_tasks.py`

- [ ] **Step 1: Red tests** asserting that, after step 8 (evidence) and before persist in `_extract_fact_impl`:

- grounding runs only when `GROUNDING_ENABLED` is set; default off keeps current behavior.
- a required-type Check A failure routes to `_complete_unknown` with the grounding reason and `chunk_status = "needs_review"`; no reliable fact/rule is created.
- a warn-only failure still persists the fact/rule **and** the grounding result.
- the grounding payload reaches `complete_extraction_job`.
- grounding respects the existing idempotency key and tenant (`workspace_id`) checks.

- [ ] **Step 2: Implement** a `grounding.py` adapter that builds the claim payload from `ExtractionOutput.normalized_content` (or each multi-record) plus the `EvidenceSpanInput`, calls `run_grounding`, and returns a routing decision. Insert the call between current steps 8 and 9 of `tasks.py`. Keep it flag-gated and warn-only for required types until the gold slice passes (Task 9). Run worker tests green.

```powershell
uv run --cache-dir .uv-cache pytest workers\extraction\tests -q
```

Code Reviewer verifies idempotency, tenant checks, and that grounding failures never silently drop a record without a review route.

## Task 9: Grounding Gold Slice + Evaluator

**Files:**
- Create: `examples/grounding_gold/manifest.json` + fixtures
- Create: `scripts/quality/grounding_gold_eval.py`
- Create: `tests/smoke/test_grounding_gold_eval.py`

- [ ] **Step 1: Build the labeled corpus** of 50-100 cases. Each case: `case_id`, `fact_type`/`rule_type`, structured claim, `chunk_text`, evidence quote + offsets, `expected_deterministic`, `expected_entailment`, and human label reason. Cover positives, negation, scope/exception, conditional, normalized-claim, ambiguous-substring, and bad-offset cases. Tag each with corpus/modality (clean-document subset).

- [ ] **Step 2: Red tests** for `grounding_gold_eval.py` pure functions: deterministic false-pass counting, false-fail rate, entailment precision/recall by required type, abstention rate, and deterministic JSON output (`grounding_gold_eval.v1`, no absolute paths, no timestamps).

- [ ] **Step 3: Implement evaluator + CLI.** Check A runs for real (deterministic); Check B runs against a fake/stub verifier in CI and optionally a real provider locally. Gates (reported, enforced only when `--enforce`): deterministic false-pass `= 0`, false-fail `<= 0.02`, precision `>= 0.95`, recall `>= 0.90`, abstention `<= 0.10`. Exit `0` pass, `1` evaluated failure, `2` invalid input.

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_grounding_gold_eval.py -q
uv run --cache-dir .uv-cache python scripts\quality\grounding_gold_eval.py
```

- [ ] **Step 4: Decision gate.** Only after the slice meets thresholds and review agrees failure modes are understandable, flip Task 8 required types from warn-only to hard routing. Record the decision as a Truth Contract note.

## Task 10: Documentation And Evidence

**Files:**
- Create: `docs/07-qa/GROUNDING_GOLD_SLICE.md`
- Modify: `tasks/TASK-040-grounding-worker.md`
- Modify: `docs/03-pipeline/PIPELINE.md` (add grounding stage to the sequence)

- [ ] **Step 1: Runbook** - purpose, commands, manifest shape, gates, how to add cases without committing private documents, and the warn-only -> hard-gate promotion procedure.
- [ ] **Step 2: Update `PIPELINE.md`** to show `normalization -> grounding A -> grounding B -> persist`.
- [ ] **Step 3: Record execution evidence** in `TASK-040` with red-first results and final command outputs.

## Final Verification

```powershell
uv run --cache-dir .uv-cache pytest packages\grounding\tests -q
uv run --cache-dir .uv-cache pytest packages\model_gateway\tests -q
uv run --cache-dir .uv-cache pytest workers\extraction\tests -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_grounding_gold_eval.py -q
uv run --cache-dir .uv-cache python scripts\quality\grounding_gold_eval.py
uv run --cache-dir .uv-cache ruff check packages\grounding scripts\quality\grounding_gold_eval.py
uv run --cache-dir .uv-cache mypy --ignore-missing-imports packages\grounding\src\grounding
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Expected:

- grounding, gateway, and extraction worker tests pass;
- gold-slice smoke tests pass and CLI exits `0`;
- ruff and mypy pass;
- secret scan exits `0`;
- `context_bundle.v1` unchanged; grounding hard gating remains off until the gold slice clears thresholds.
