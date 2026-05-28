# Source Pack Context Bundle Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a source-pack compiler that turns `C:\tmp\context-builder-sources\compounding-pharmacy-gold` into a deterministic, sanitized, schema-valid `context_bundle.v1` JSON artifact.

**Architecture:** Add a new pure Python package for source-pack compilation, separate from the Supabase-backed API exporter. The compiler reads a filesystem source pack, performs manifest preflight, registers deterministic published sources, extracts evidence/facts/rules/gaps/tests/memory/tool recommendations, validates/sanitizes the result, and writes a bundle using the existing `ContextBundleResponse` contract. A thin CLI script calls the package.

**Tech Stack:** Python 3.12, Pydantic, stdlib `csv`/`hashlib`/`pathlib`, existing `context_builder.schemas.context_bundle`, pytest, ruff, mypy.

---

## Execution Model

Use multi-agent SDD with one fresh implementer subagent per task.

For every task:

1. Implementer uses `superpowers:test-driven-development`.
2. Implementer writes failing tests first and verifies RED.
3. Implementer writes minimal implementation and verifies GREEN.
4. Spec reviewer checks the task against this plan.
5. Code-quality reviewer checks maintainability, determinism, and contract safety.
6. Controller runs the task-specific gate before proceeding.

Do not dispatch implementation subagents in parallel against the same files.

## File Map

Create:

- `packages/source_pack/pyproject.toml`
- `packages/source_pack/src/source_pack/__init__.py`
- `packages/source_pack/src/source_pack/ids.py`
- `packages/source_pack/src/source_pack/manifest.py`
- `packages/source_pack/src/source_pack/readers.py`
- `packages/source_pack/src/source_pack/evidence.py`
- `packages/source_pack/src/source_pack/extractors.py`
- `packages/source_pack/src/source_pack/compiler.py`
- `packages/source_pack/src/source_pack/validators.py`
- `packages/source_pack/src/source_pack/writer.py`
- `packages/source_pack/tests/test_ids.py`
- `packages/source_pack/tests/test_manifest.py`
- `packages/source_pack/tests/test_readers.py`
- `packages/source_pack/tests/test_evidence.py`
- `packages/source_pack/tests/test_extractors.py`
- `packages/source_pack/tests/test_compiler.py`
- `packages/source_pack/tests/test_validators.py`
- `scripts/source_pack/compile_context_bundle.py`
- `tests/compat/test_compounding_pharmacy_source_pack_compiler.py`
- `docs/operations/source-pack-compiler-runbook.md`
- `tasks/TASK-017-source-pack-context-bundle-compiler.md`

Modify:

- `pyproject.toml`
- `uv.lock`
- `docs/README.md`
- `docs/03-pipeline/CONTEXT_BUNDLE.md`
- `docs/07-qa/ACCEPTANCE_CRITERIA.md`

## Canonical Input

Source dir:

```text
C:\tmp\context-builder-sources\compounding-pharmacy-gold
```

Manifest:

```text
00_source_manifest.md
```

Expected numbered source files:

```text
01_regulatory_scope_and_safety_policy.md
02_active_ingredients_catalog.csv
03_product_lines_and_formulations.csv
04_allergens_excipients_triage.csv
05_sales_triage_rules.md
06_context_builder_expected_tests.md
07_pharmacy_commercial_profile.md
08_channels_and_handoff_matrix.csv
09_order_status_lifecycle.csv
10_quote_pricing_policy.md
11_regulatory_category_matrix.csv
12_pharmacovigilance_adverse_events.md
13_prescription_document_handling.md
14_known_gaps_and_publish_gates.csv
15_canonical_evidence_map.csv
16_memory_and_tool_policy.md
17_sample_user_queries.csv
18_dcb_normalization_policy.csv
19_compounding_good_practices_rdc67.md
20_labeling_and_patient_instructions.md
21_controlled_antimicrobial_handoff_matrix.csv
22_adverse_event_quality_complaint_schema.csv
23_stability_storage_beyond_use_policy.md
24_patient_friendly_safe_language.md
25_do_not_answer_clinical_boundaries.md
26_expanded_active_ingredients_backlog.csv
27_inventory_stock_catalog.csv
28_inventory_freshness_policy.md
29_inventory_mutation_contract.csv
30_calendar_event_catalog.csv
31_calendar_event_policy.md
32_calendar_mutation_contract.csv
33_expanded_drug_catalog_batch_2.csv
34_synonyms_brand_terms_catalog.csv
35_pharmaceutical_forms_catalog.csv
36_excipient_compatibility_catalog.csv
37_supplier_mock_catalog.csv
38_synthetic_inventory_large_catalog.csv
39_synthetic_price_catalog.csv
40_quote_rules_matrix.csv
41_quote_flow_scenarios.csv
42_delivery_pickup_policy_matrix.csv
43_payment_discount_gap_policy.md
44_risk_combination_matrix.csv
45_interaction_detection_triggers.csv
46_population_safety_matrix.csv
47_adverse_event_scenarios.csv
48_controlled_substance_refusal_examples.md
49_clinical_boundary_eval_cases.csv
50_synthetic_calendar_slots.csv
51_calendar_booking_scenarios.csv
52_inventory_mutation_scenarios.csv
53_tool_calling_policy_matrix.csv
54_tool_calling_expected_traces.csv
55_audit_and_rollback_policy.md
56_sales_conversation_playbook.md
57_objection_handling_playbook.md
58_long_conversation_scenarios.csv
59_synthetic_customer_query_eval_set.csv
60_golden_answer_style_guide.md
61_context_builder_extraction_expectations.md
62_chatbot_readiness_scorecard.md
63_release_gate_eval_suite.md
64_failure_modes_and_regression_tests.md
```

`README.md` may be present but is not counted as a numbered source. The current pack has 64 numbered documents plus manifest and README. If the product requirement keeps saying "66 documents", the implementation must report exact counts rather than silently pretending.

## Output

Default output path:

```text
C:\tmp\context-builder-sources\compounding-pharmacy-gold\compounding-pharmacy-gold.context_bundle.v1.json
```

The output must validate as `ContextBundleResponse` and as `examples/context_bundle/context-bundle.v1.schema.json`.

---

## Task 1: Package Scaffold And Deterministic IDs

**Agent:** Source Pack Core Agent

**Files:**
- Create: `packages/source_pack/pyproject.toml`
- Create: `packages/source_pack/src/source_pack/__init__.py`
- Create: `packages/source_pack/src/source_pack/ids.py`
- Create: `packages/source_pack/tests/test_ids.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing tests for deterministic UUIDs**

Create tests proving:

```python
from source_pack.ids import stable_uuid, slug_from_filename

def test_stable_uuid_is_deterministic_for_semantic_id() -> None:
    assert stable_uuid("source:02_active_ingredients_catalog.csv") == stable_uuid(
        "source:02_active_ingredients_catalog.csv"
    )

def test_stable_uuid_changes_by_namespace_prefix() -> None:
    assert stable_uuid("source:x") != stable_uuid("fact:x")

def test_slug_from_filename_strips_prefix_and_extension() -> None:
    assert slug_from_filename("02_active_ingredients_catalog.csv") == "active-ingredients-catalog"
```

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\source_pack\tests\test_ids.py -q
```

Expected: FAIL because package does not exist.

- [ ] **Step 2: Implement package scaffold**

Implement:

```python
NAMESPACE = UUID("7b4d4a56-91ab-54fa-9a91-sourcepack0001")

def stable_uuid(value: str) -> UUID:
    return uuid5(NAMESPACE, value)

def slug_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"^\d+_", "", stem)
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
```

Use a valid UUID constant. Do not use random UUIDs.

- [ ] **Step 3: Update workspace**

Add `packages/source_pack` to `[tool.uv.workspace].members` and `[tool.uv.sources]`.

- [ ] **Step 4: Verify**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\source_pack\tests\test_ids.py -q
uv run --cache-dir .uv-cache ruff check packages\source_pack
```

Expected: PASS.

## Task 2: Manifest Parser And Preflight

**Agent:** Manifest Agent

**Files:**
- Create: `packages/source_pack/src/source_pack/manifest.py`
- Create: `packages/source_pack/tests/test_manifest.py`

- [ ] **Step 1: Write failing manifest tests**

Tests must cover:

- frontmatter fields:
  - `source_pack_id`
  - `source_pack_version`
  - `language`
  - `intended_consumer`
  - `publication_status`
- official source references table;
- document roles table;
- missing listed file fails preflight;
- extra unlisted numbered file warns;
- count reports manifest + numbered files + README separately.

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\source_pack\tests\test_manifest.py -q
```

Expected: FAIL.

- [ ] **Step 2: Implement parser**

Expose:

```python
@dataclass(frozen=True)
class SourcePackManifest:
    source_pack_id: str
    source_pack_version: str
    language: str
    intended_consumer: str
    publication_status: str
    official_references: list[OfficialReference]
    document_roles: list[DocumentRole]

def parse_manifest(path: Path) -> SourcePackManifest: ...
def preflight_source_pack(source_dir: Path) -> SourcePackPreflight: ...
```

Use Markdown table parsing scoped to the two table headings. Avoid loose regex across the whole file when a line-based table parser is enough.

- [ ] **Step 3: Verify on real pack**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\source_pack\tests\test_manifest.py -q
```

Expected: PASS and real pack preflight reports 64 numbered sources.

## Task 3: Source Registration And Readers

**Agent:** Source Reader Agent

**Files:**
- Create: `packages/source_pack/src/source_pack/readers.py`
- Create: `packages/source_pack/tests/test_readers.py`

- [ ] **Step 1: Write failing tests**

Tests must prove:

- CSV rows keep 1-based data row numbers matching file line numbers;
- Markdown sections produce stable anchors from headings;
- source records are published by default for valid source-pack files;
- `README.md` is ignored as content source unless explicitly listed in manifest.

- [ ] **Step 2: Implement readers**

Expose:

```python
def build_sources(manifest: SourcePackManifest, source_dir: Path) -> list[dict[str, Any]]
def read_csv_rows(path: Path) -> list[CsvRow]
def read_markdown_sections(path: Path) -> list[MarkdownSection]
```

Source fields must fit current `ContextBundleSource`:

```python
{
    "id": stable_uuid(f"source:{filename}"),
    "title": title_from_manifest_or_filename,
    "original_filename": filename,
    "type": "csv" | "markdown",
    "source_reliability": "synthetic_approved",
    "authority_level": document_type,
    "status": "published",
}
```

- [ ] **Step 3: Verify**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\source_pack\tests\test_readers.py -q
```

Expected: PASS.

## Task 4: Evidence Extraction

**Agent:** Evidence Agent

**Files:**
- Create: `packages/source_pack/src/source_pack/evidence.py`
- Create: `packages/source_pack/tests/test_evidence.py`

- [ ] **Step 1: Write failing tests**

Tests must cover:

- CSV row evidence has `row_number`;
- Markdown section evidence has a stable quote and anchor stored in safe details only if contract allows it;
- evidence IDs are deterministic UUIDs;
- evidence quote is sanitized and not longer than the configured max.

- [ ] **Step 2: Implement evidence generation**

Expose:

```python
def evidence_from_csv_row(source_id: UUID, filename: str, row: CsvRow) -> dict[str, Any]
def evidence_from_markdown_section(source_id: UUID, filename: str, section: MarkdownSection) -> dict[str, Any]
```

Current bundle contract does not allow arbitrary `metadata` on evidence. Preserve anchors by encoding them into deterministic IDs and, where useful, inside short `quote` context. Do not add non-contract fields.

- [ ] **Step 3: Verify**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\source_pack\tests\test_evidence.py -q
```

Expected: PASS.

## Task 5: CSV And Markdown Extractors

**Agent:** Domain Extraction Agent

**Files:**
- Create: `packages/source_pack/src/source_pack/extractors.py`
- Create: `packages/source_pack/tests/test_extractors.py`

- [ ] **Step 1: Write failing tests for representative files**

Required fixtures/tests:

- `02_active_ingredients_catalog.csv` generates `active_ingredient` facts.
- `04_allergens_excipients_triage.csv` generates allergen/excipient facts and handoff rules.
- `14_known_gaps_and_publish_gates.csv` generates gaps.
- `16_memory_and_tool_policy.md` generates memory policy and tool rules.
- `40_quote_rules_matrix.csv` generates quote rules.
- `53_tool_calling_policy_matrix.csv` generates tool recommendations.
- `54_tool_calling_expected_traces.csv` generates tests.
- `59_synthetic_customer_query_eval_set.csv` generates tests.
- `05_sales_triage_rules.md` generates rules from headings/sections.
- `63_release_gate_eval_suite.md` generates release-gate tests.

- [ ] **Step 2: Implement dispatch by document role**

Expose:

```python
def extract_document(
    role: DocumentRole,
    source: dict[str, Any],
    csv_rows: list[CsvRow] | None,
    markdown_sections: list[MarkdownSection] | None,
) -> ExtractedDocument
```

`ExtractedDocument` contains:

```python
facts: list[dict[str, Any]]
rules: list[dict[str, Any]]
gaps: list[dict[str, Any]]
tests: list[dict[str, Any]]
memory_policy_patch: dict[str, Any]
tool_recommendations: list[dict[str, Any]]
evidence: list[dict[str, Any]]
```

Map semantic facts into current contract:

```python
{
    "id": stable_uuid("fact:{source_filename}:{anchor}"),
    "fact_type": "active_ingredient",
    "schema_version": "source_pack.fact.v1",
    "normalized_content": {...},
    "confidence": 1.0,
    "source_id": source["id"],
    "chunk_id": stable_uuid("chunk:{source_filename}:{anchor}"),
    "evidence_span_id": evidence_id,
    "status": "published",
}
```

Map rules into current contract:

```python
{
    "id": stable_uuid("rule:{source_filename}:{anchor}"),
    "rule_type": "sales_triage" | "quote_policy" | "tool_policy" | "...",
    "schema_version": "source_pack.rule.v1",
    "condition": {...},
    "action": {...},
    "priority": int,
    "confidence": 1.0,
    "source_id": source["id"],
    "chunk_id": stable_uuid("chunk:{source_filename}:{anchor}"),
    "evidence_span_id": evidence_id,
    "status": "published",
}
```

- [ ] **Step 3: Verify**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\source_pack\tests\test_extractors.py -q
```

Expected: PASS.

## Task 6: Sanitization And Bundle Validation

**Agent:** Safety Validation Agent

**Files:**
- Create: `packages/source_pack/src/source_pack/validators.py`
- Create: `packages/source_pack/tests/test_validators.py`

- [ ] **Step 1: Write failing tests**

Tests must block:

- `sk-...` style secrets;
- `Bearer ...`;
- local private paths such as `C:\Users\...`, `/home/...`, `/root/...`;
- stack traces;
- raw prompt labels like `SYSTEM PROMPT`;
- provider raw response payloads;
- critical rules without evidence;
- critical tests without required evidence;
- source records not `published`;
- memory policy storing diagnosis/full prescription/card numbers/controlled details.

- [ ] **Step 2: Implement validators**

Expose:

```python
def validate_source_pack_bundle(bundle: ContextBundleResponse) -> list[ValidationIssue]
def raise_if_blocked(issues: list[ValidationIssue]) -> None
```

Validation issue severities:

```python
"blocker" | "warning"
```

- [ ] **Step 3: Verify**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\source_pack\tests\test_validators.py -q
```

Expected: PASS.

## Task 7: Compiler And Readiness

**Agent:** Compiler Agent

**Files:**
- Create: `packages/source_pack/src/source_pack/compiler.py`
- Create: `packages/source_pack/tests/test_compiler.py`

- [ ] **Step 1: Write failing compiler tests**

Tests must prove:

- compiler reads real `compounding-pharmacy-gold`;
- compiler outputs `ContextBundleResponse`;
- source count is 64 for numbered source files;
- `readiness.status == "warning"` for synthetic accepted gaps;
- no blocker for synthetic inventory/prices when declared as accepted gaps;
- bundle contains non-empty facts/rules/evidence/gaps/tests/tool recommendations;
- `context_version` is stable across repeated compiles when content is unchanged.

- [ ] **Step 2: Implement compiler**

Expose:

```python
def compile_source_pack(source_dir: Path, *, workspace_id: UUID | None = None) -> ContextBundleResponse
```

Use `context_builder.services.context_bundle_service.build_context_bundle_from_rows` to avoid duplicating hash and contract projection. Pass extracted rows into that function.

Readiness rules:

- blocker if any validator issue is blocker;
- blocker if no published source;
- blocker if no facts and no rules;
- warning if accepted synthetic gaps exist;
- warning if inventory is synthetic;
- warning if prices are synthetic;
- warning if ERP is not integrated;
- warning if official full DCB list is not materialized;
- score starts at 100 and subtracts weighted warnings, but compounding-pharmacy synthetic pack should remain non-blocked.

- [ ] **Step 3: Verify**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\source_pack\tests\test_compiler.py -q
```

Expected: PASS.

## Task 8: CLI Writer

**Agent:** CLI Agent

**Files:**
- Create: `packages/source_pack/src/source_pack/writer.py`
- Create: `scripts/source_pack/compile_context_bundle.py`
- Create: `tests/compat/test_compounding_pharmacy_source_pack_compiler.py`

- [ ] **Step 1: Write failing CLI tests**

Test:

- CLI accepts `--source-dir`;
- CLI accepts `--output`;
- `--check` exits non-zero if output is missing or stale;
- generated JSON validates through `ContextBundleResponse`;
- integrity counts match arrays.

- [ ] **Step 2: Implement writer and CLI**

CLI usage:

```powershell
uv run --cache-dir .uv-cache python scripts\source_pack\compile_context_bundle.py --source-dir C:\tmp\context-builder-sources\compounding-pharmacy-gold --output C:\tmp\context-builder-sources\compounding-pharmacy-gold\compounding-pharmacy-gold.context_bundle.v1.json
```

Check usage:

```powershell
uv run --cache-dir .uv-cache python scripts\source_pack\compile_context_bundle.py --source-dir C:\tmp\context-builder-sources\compounding-pharmacy-gold --output C:\tmp\context-builder-sources\compounding-pharmacy-gold\compounding-pharmacy-gold.context_bundle.v1.json --check
```

- [ ] **Step 3: Verify**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\compat\test_compounding_pharmacy_source_pack_compiler.py -q
```

Expected: PASS.

## Task 9: Documentation And Acceptance Criteria

**Agent:** Documentation Agent

**Files:**
- Create: `docs/operations/source-pack-compiler-runbook.md`
- Create: `tasks/TASK-017-source-pack-context-bundle-compiler.md`
- Modify: `docs/README.md`
- Modify: `docs/03-pipeline/CONTEXT_BUNDLE.md`
- Modify: `docs/07-qa/ACCEPTANCE_CRITERIA.md`

- [ ] **Step 1: Document user-facing product flow**

Document:

```text
user uploads folder/zip/lote
-> preflight detects source pack
-> source pack compiler validates manifest
-> package is compiled into draft/reviewable bundle
-> human review/publish remains required for product flow
```

Do not imply end users run CLI. CLI is the first implementation adapter and test harness.

- [ ] **Step 2: Document current CLI**

Include exact commands and expected outputs.

- [ ] **Step 3: Update acceptance criteria**

Add source-pack compiler evidence criteria:

- preflight detects complete pack;
- compiler reads 64 numbered files plus manifest;
- generated bundle validates schema;
- generated bundle has non-empty facts/rules/evidence/gaps/tests;
- bundle readiness is warning, not blocked, for synthetic accepted gaps;
- sanitizer blocks secrets/private paths/raw prompts;
- hash is deterministic.

## Task 10: Full Gate And Final Review

**Agent:** Integration Review Agent

**Files:**
- No production files unless fixing review findings.

- [ ] **Step 1: Run focused gate**

```powershell
uv run --cache-dir .uv-cache pytest packages\source_pack\tests tests\compat\test_compounding_pharmacy_source_pack_compiler.py -q
uv run --cache-dir .uv-cache python scripts\source_pack\compile_context_bundle.py --source-dir C:\tmp\context-builder-sources\compounding-pharmacy-gold --output C:\tmp\context-builder-sources\compounding-pharmacy-gold\compounding-pharmacy-gold.context_bundle.v1.json
uv run --cache-dir .uv-cache python scripts\source_pack\compile_context_bundle.py --source-dir C:\tmp\context-builder-sources\compounding-pharmacy-gold --output C:\tmp\context-builder-sources\compounding-pharmacy-gold\compounding-pharmacy-gold.context_bundle.v1.json --check
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

- [ ] **Step 2: Run repository gates**

```powershell
uv run --cache-dir .uv-cache pytest -q
uv run --cache-dir .uv-cache ruff check .
npm run typecheck:python
npm run typecheck:python:strict-full
corepack pnpm --filter @context-builder/web typecheck
corepack pnpm --filter @context-builder/web build
```

- [ ] **Step 3: Final review**

Dispatch final reviewers:

- spec compliance reviewer: confirms every requested field and criterion is covered;
- code quality reviewer: checks deterministic IDs, sanitization, schema strictness, and no Supabase coupling;
- security reviewer: checks forbidden data classes and path/secret leakage.

## Success Criteria

The implementation is complete only when:

1. `C:\tmp\context-builder-sources\compounding-pharmacy-gold` compiles without manual edits.
2. The compiler reads `00_source_manifest.md`.
3. The compiler registers all 64 numbered source files as published sources.
4. CSV row evidence and Markdown section evidence are citably preserved.
5. Facts, rules, gaps, tests, memory policy and tool recommendations are non-empty.
6. Critical rules and tests have evidence references.
7. Synthetic gaps produce `readiness.status = "warning"` rather than `blocked`.
8. Secrets, private local paths, raw prompts, provider responses and stack traces are blocked or absent.
9. `ContextBundleResponse` validation passes.
10. JSON Schema validation passes.
11. Hash and `context_version` are deterministic.
12. `--check` detects stale output.
13. Repository gates pass.

## Known Product Follow-Up

This plan builds the compiler and CLI harness. A later product slice should add:

- folder/zip upload in the web console;
- `source_pack_import` persistence;
- source-pack preflight endpoint;
- package-level review UI;
- package-level publish action;
- automatic bundle export after publish.
