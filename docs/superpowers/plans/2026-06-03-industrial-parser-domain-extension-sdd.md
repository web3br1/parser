# Industrial Parser Domain Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Context Compiler with industrial/QMS controlled-document semantics while preserving `context_bundle.v1` compatibility.

**Architecture:** Add an additive industrial domain layer: typed domain models, deterministic metadata candidates, revision resolver, industrial classification/extraction schemas, review/readiness gates, fixture pack and bundle-compatible relation export. Existing generic parsers, review flow and `context_bundle.v1` remain the backbone.

**Tech Stack:** Python 3.12, Pydantic, FastAPI service layer, Supabase migrations/RLS, pytest, ruff, mypy, existing Next.js console for review surfaces.

---

## Execution Model

Use SDD with four roles:

1. **Orchestrator** reads this plan, creates the task list, dispatches one task
   at a time and resolves blockers.
2. **Task Worker** uses `superpowers:test-driven-development`, writes failing
   tests first, implements only the assigned task and reports status.
3. **Reviewer** performs spec-compliance review first, then code-quality review.
4. **Approval** runs final gates and blocks merge if docs, tests, security or
   compatibility are incomplete.

Do not dispatch multiple Task Workers in parallel against the same files.
Do not publish industrial knowledge without human review.

## File Map

Create:

- `packages/domain/src/domain/industrial.py`
- `packages/domain/tests/test_industrial_models.py`
- `packages/parsers/src/parsers/industrial_metadata.py`
- `packages/parsers/src/parsers/industrial_structure.py`
- `packages/parsers/tests/test_industrial_metadata.py`
- `packages/parsers/tests/test_industrial_structure.py`
- `packages/domain/src/domain/industrial_revision.py`
- `packages/domain/tests/test_industrial_revision.py`
- `examples/industrial_qms/manifest.json`
- `docs/operations/industrial-parser-runbook.md`

Modify as needed:

- `packages/domain/src/domain/__init__.py`
- `workers/classification/src/worker_classification/classifier.py`
- `workers/classification/src/worker_classification/prompt.py`
- `workers/classification/tests/test_classifier.py`
- `workers/extraction/src/worker_extraction/prompt.py`
- `workers/extraction/src/worker_extraction/extractor.py`
- `packages/schema_registry/src/schema_registry/types.py`
- `packages/schema_registry/src/schema_registry/validators.py`
- `packages/schema_registry/tests/test_validators.py`
- `apps/api/src/context_builder/services/context_bundle_service.py`
- `apps/api/src/context_builder/schemas/context_bundle.py` only if a compatible
  field already exists or a separate v2 ADR is accepted.
- `docs/03-pipeline/CONTEXT_BUNDLE.md`
- `docs/07-qa/ACCEPTANCE_CRITERIA.md`

## Task 1: Industrial Domain Models

**Agent:** Task Worker

**Files:**
- Create: `packages/domain/src/domain/industrial.py`
- Create: `packages/domain/tests/test_industrial_models.py`
- Modify: `packages/domain/src/domain/__init__.py`

- [ ] **Step 1: Write failing model tests**

Create tests proving valid document metadata, valid relation records and enum
normalization.

```python
from domain.industrial import ControlledDocumentMetadata, DocumentRelationship

def test_controlled_document_metadata_accepts_pop_revision() -> None:
    item = ControlledDocumentMetadata(
        document_code="POP-QA-014",
        document_type="POP",
        title="Controle de Nao Conformidades",
        revision="04",
        status="vigent",
        owner_area="Qualidade",
    )

    assert item.document_code == "POP-QA-014"
    assert item.revision == "04"

def test_relationship_requires_known_type() -> None:
    relation = DocumentRelationship(
        from_id="POP-QA-014",
        from_type="Document",
        to_id="FOR-QA-002",
        to_type="Form",
        relationship_type="uses_form",
    )

    assert relation.relationship_type == "uses_form"
```

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\domain\tests\test_industrial_models.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 2: Implement minimal models**

Implement `ControlledDocumentMetadata`, `DocumentRelationship`, document type
literal values, status values and relationship type values. Use Pydantic strict
models following existing domain/schema style.

- [ ] **Step 3: Verify**

```powershell
uv run --cache-dir .uv-cache pytest packages\domain\tests\test_industrial_models.py -q
uv run --cache-dir .uv-cache ruff check packages\domain
```

Expected: PASS.

## Task 2: Deterministic Metadata Candidates

**Agent:** Task Worker

**Files:**
- Create: `packages/parsers/src/parsers/industrial_metadata.py`
- Create: `packages/parsers/tests/test_industrial_metadata.py`

- [ ] **Step 1: Write failing metadata tests**

```python
from parsers.industrial_metadata import extract_metadata_candidates

def test_extracts_document_code_and_revision_from_filename() -> None:
    result = extract_metadata_candidates(
        filename="POP-QA-014 Rev. 04 Controle de NC.pdf",
        text="",
    )

    assert result.document_code == "POP-QA-014"
    assert result.revision == "04"

def test_missing_revision_is_gap_candidate() -> None:
    result = extract_metadata_candidates(
        filename="POP-QA-014 Controle de NC.pdf",
        text="Controle de Nao Conformidades",
    )

    assert "missing_revision" in result.gap_codes
```

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_metadata.py -q
```

Expected: FAIL.

- [ ] **Step 2: Implement deterministic extraction**

Extract candidates from filename and first-page/header text:

- document code pattern like `POP-QA-014`;
- revision markers like `Rev. 04`, `Revisao 04`, `R04`;
- document type prefix;
- likely title;
- explicit status words `vigente`, `obsoleto`, `rascunho`, `aprovado`;
- owner area if labeled.

Return candidates plus `gap_codes`.

- [ ] **Step 3: Verify**

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_metadata.py -q
```

Expected: PASS.

## Task 3: Revision Resolver

**Agent:** Task Worker

**Files:**
- Create: `packages/domain/src/domain/industrial_revision.py`
- Create: `packages/domain/tests/test_industrial_revision.py`

- [ ] **Step 1: Write failing revision tests**

```python
from domain.industrial_revision import resolve_revision_family

def test_highest_revision_is_candidate_when_no_conflict() -> None:
    result = resolve_revision_family([
        {"document_code": "POP-QA-014", "revision": "03", "status": "obsolete", "content_hash": "a"},
        {"document_code": "POP-QA-014", "revision": "04", "status": "approved", "content_hash": "b"},
    ])

    assert result.vigent_revision == "04"
    assert result.blocking_gap_codes == []

def test_same_revision_different_hash_blocks() -> None:
    result = resolve_revision_family([
        {"document_code": "POP-QA-014", "revision": "04", "status": "approved", "content_hash": "a"},
        {"document_code": "POP-QA-014", "revision": "04", "status": "approved", "content_hash": "b"},
    ])

    assert "duplicate_revision_conflict" in result.blocking_gap_codes
```

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\domain\tests\test_industrial_revision.py -q
```

Expected: FAIL.

- [ ] **Step 2: Implement resolver**

Group by normalized document code. Sort revisions numerically when possible,
then lexically. Block missing revision, duplicate same revision with different
hash and multiple approved revisions without explicit obsolete marking.

- [ ] **Step 3: Verify**

```powershell
uv run --cache-dir .uv-cache pytest packages\domain\tests\test_industrial_revision.py -q
```

Expected: PASS.

## Task 4: Industrial Structure Hints

**Agent:** Task Worker

**Files:**
- Create: `packages/parsers/src/parsers/industrial_structure.py`
- Create: `packages/parsers/tests/test_industrial_structure.py`
- Modify: `packages/parsers/src/parsers/chunker.py` only if needed.

- [ ] **Step 1: Write failing structure tests**

Test section numbers, annex labels, form-field labels and table headings.

- [ ] **Step 2: Implement structure hints**

Expose a function that receives extracted text and returns ordered hints:

```python
{
  "kind": "section",
  "label": "5.2",
  "title": "Abertura de NC",
  "char_start": 120,
  "char_end": 460
}
```

Do not change existing chunk behavior until tests prove the hint can be safely
stored in chunk metadata.

- [ ] **Step 3: Verify**

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_structure.py packages\parsers\tests\test_chunker.py -q
```

Expected: PASS.

## Task 5: Industrial Schema Registry And Prompts

**Agent:** Task Worker

**Files:**
- Modify: `packages/schema_registry/src/schema_registry/types.py`
- Modify: `packages/schema_registry/src/schema_registry/validators.py`
- Modify: `packages/schema_registry/tests/test_validators.py`
- Modify: `workers/classification/src/worker_classification/classifier.py`
- Modify: `workers/classification/src/worker_classification/prompt.py`
- Modify: `workers/classification/tests/test_classifier.py`
- Modify: `workers/extraction/src/worker_extraction/prompt.py`
- Modify: `workers/extraction/tests/test_extractor.py`

- [ ] **Step 1: Write failing classification and validation tests**

Add tests for:

- `controlled_document_metadata`;
- `industrial_requirement`;
- `industrial_responsibility`;
- `industrial_relation`;
- low confidence routes to unknown;
- unsupported industrial class routes to unknown.

- [ ] **Step 2: Add schema types**

Add strict Pydantic schemas for metadata, requirement, responsibility and
relation. Keep them explicit; do not add a generic catch-all schema.

- [ ] **Step 3: Add prompts**

Prompt rules:

- extract only explicit text;
- include evidence quote;
- never infer revision status without source signal;
- return failed if evidence is absent.

- [ ] **Step 4: Verify**

```powershell
uv run --cache-dir .uv-cache pytest packages\schema_registry\tests workers\classification\tests workers\extraction\tests -q
```

Expected: PASS.

## Task 6: Review And Readiness Gates

**Agent:** Task Worker

**Files:**
- Modify: `apps/api/src/context_builder/services/context_bundle_service.py`
- Modify: `tests/api/test_context_bundle.py`
- Create or modify service helpers under `apps/api/src/context_builder/services/`.

- [ ] **Step 1: Write failing readiness tests**

Cover blockers:

- missing document code;
- missing revision;
- unresolved revision conflict;
- obsolete document used in active rule;
- relation references missing node;
- industrial record missing evidence.

- [ ] **Step 2: Implement industrial readiness helper**

Keep generic readiness behavior. Add industrial blocker/warning computation when
published facts/rules contain industrial types.

- [ ] **Step 3: Verify**

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_bundle.py -q
```

Expected: PASS.

## Task 7: Industrial Fixture Pack

**Agent:** Task Worker

**Files:**
- Create: `examples/industrial_qms/manifest.json`
- Create fixture documents under `examples/industrial_qms/`
- Create: `tests/smoke/test_industrial_qms_fixtures.py`

- [ ] **Step 1: Write failing fixture tests**

Assert fixture corpus contains:

- vigent POP revision;
- obsolete POP revision;
- work instruction;
- form;
- record/log;
- FAQ;
- XLSX/CSV table;
- missing-revision document;
- duplicate-revision conflict;
- prompt-injection document;
- OCR-required empty/scanned fixture.

- [ ] **Step 2: Add fixtures**

Use small synthetic documents. Keep them safe, deterministic and free of
secrets/private paths.

- [ ] **Step 3: Verify**

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_qms_fixtures.py -q
```

Expected: PASS.

## Task 8: Documentation And PR Readiness

**Agent:** Task Worker

**Files:**
- Create: `docs/operations/industrial-parser-runbook.md`
- Modify: `docs/03-pipeline/INDUSTRIAL_DOCUMENTS.md`
- Modify: `docs/07-qa/ACCEPTANCE_CRITERIA.md`
- Modify: `docs/README.md`
- Update PR body artifact.

- [ ] **Step 1: Document operator flow**

Document:

```text
upload controlled docs
-> quality gate
-> industrial metadata candidates
-> revision review
-> fact/rule/relation review
-> publish
-> context_bundle.v1 export
```

- [ ] **Step 2: Document first-slice limits**

Explicitly list OCR and QMS connectors as out of scope.

- [ ] **Step 3: Verify docs**

```powershell
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Expected: PASS.

## Task 9: Final Approval Gate

**Agent:** Approval

**Files:**
- No production files unless fixing review findings.

- [ ] **Step 1: Run focused gate**

```powershell
uv run --cache-dir .uv-cache pytest packages\domain\tests packages\parsers\tests packages\schema_registry\tests workers\classification\tests workers\extraction\tests tests\api\test_context_bundle.py tests\smoke\test_industrial_qms_fixtures.py -q
uv run --cache-dir .uv-cache ruff check packages apps workers tests
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Expected: PASS.

- [ ] **Step 2: Run compatibility gate**

```powershell
uv run --cache-dir .uv-cache pytest tests\compat\test_context_bundle_schema_export.py tests\compat\test_context_bundle_golden.py -q
uv run --cache-dir .uv-cache python scripts\context_bundle\export_json_schema.py --check
uv run --cache-dir .uv-cache python scripts\context_bundle\export_golden_bundle.py --check
```

Expected: PASS. If this fails because a top-level bundle field was added, stop
and require a new bundle-version ADR.

- [ ] **Step 3: Approval checklist**

Approval must confirm:

- no OCR implementation entered the slice;
- no QMS connector entered the slice;
- no free-form industrial schema was added;
- existing generic flows still pass;
- industrial records are evidence-backed;
- revision conflicts block readiness;
- PR body states closed gaps and deferred gaps.

## Success Criteria

The feature is complete only when:

1. Industrial controlled-document metadata is schema validated.
2. Revision families resolve deterministically.
3. Missing/ambiguous revision blocks industrial activation.
4. Obsolete documents do not publish active operational rules.
5. Industrial relations export through `context_bundle.v1` facts/rules.
6. Human review can distinguish metadata, facts, rules and relations.
7. Fixture pack covers happy path, obsolete path, conflict path and OCR-required
   path.
8. Bundle compatibility gates pass.
9. Secret scan passes.
10. PR body lists closed and deferred gaps.
