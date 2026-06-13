# Parser-Wide Quality Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a parser-wide quality closure layer that prevents unsafe promotion of parser candidates into truth and proves the behavior through ground truth, review packets, bundle readiness and the top Parser quality gate.

**Architecture:** Add a small generic `quality_profile` module that extracts parser-wide quality signals from text-like artifacts. Industrial modules consume those signals for collection/document-family review behavior, while the benchmark and ground-truth evaluator expose the signals as testable predictions. Publication readiness remains in `context_bundle.v1` through existing gap/blocking mechanisms.

**Tech Stack:** Python 3.12/3.13, pytest, dataclasses, existing Parser package, existing benchmark and quality-gate scripts.

---

## File Structure

- `packages/parsers/src/parsers/quality_profile.py`: new generic quality profile module with nested identifier detection, document-family classification and JSON metadata conversion.
- `packages/parsers/tests/test_quality_profile.py`: parser-wide unit tests for text and CSV-like content.
- `packages/parsers/src/parsers/industrial_metadata.py`: enrich industrial metadata candidates with nested identifier evidence and document-family quality signals while preserving existing conservative file-level metadata behavior.
- `packages/parsers/src/parsers/industrial_review.py`: add review packet support for parser quality profiles.
- `packages/parsers/tests/test_industrial_metadata.py`: regression tests for unsafe file-level metadata blocking and nested evidence.
- `packages/parsers/tests/test_industrial_review.py`: review packet tests for document-family risks.
- `scripts/industrial/benchmark_dirty_documents.py`: include quality profile diagnostics and candidate details.
- `scripts/quality/parser_ground_truth_eval.py`: add prediction extraction for `quality_profile` and `nested_identifier` expectation kinds.
- `tests/smoke/test_parser_ground_truth_eval.py`: red/green coverage for new expectation kinds.
- `examples/parser_ground_truth/manifest.json`: new sanitized fixture expectations.
- `examples/parser_ground_truth/document_family_collection.txt`: committed PMPR-like collection fixture.
- `examples/parser_ground_truth/toc_nested_identifier_noise.txt`: committed TOC-noise fixture.
- `examples/parser_ground_truth/csv_register_like_rows.csv`: committed CSV-like row identifier fixture.
- `tests/api/test_context_bundle.py`: readiness test for unresolved parser quality collection gap.
- `docs/07-qa/PARSER_GROUND_TRUTH_EVALUATION.md`: document new expectation kinds.
- `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`: document quality profile diagnostics.
- `tasks/TASK-040-parser-wide-quality-closure.md`: execution evidence.

---

### Task 1: Parser-Wide Quality Profile

**Files:**
- Create: `packages/parsers/src/parsers/quality_profile.py`
- Create: `packages/parsers/tests/test_quality_profile.py`

- [ ] **Step 1: Write failing tests for document-family detection**

Create `packages/parsers/tests/test_quality_profile.py` with:

```python
from parsers.quality_profile import build_quality_profile, quality_profile_to_metadata


def test_detects_document_family_from_multiple_nested_identifiers() -> None:
    text = "\n".join([
        "Manual operacional consolidado",
        "POP 101 - Atendimento inicial",
        "1 Objetivo",
        "POP 102 - Encerramento",
        "2 Procedimento",
    ])

    profile = build_quality_profile(filename="manual-consolidado.txt", text=text)

    assert profile.document_family_candidate is True
    assert profile.nested_identifier_count == 2
    assert profile.unsafe_file_metadata_blocked is True
    assert profile.review_required is True
    assert profile.publication_blocking_risk is True
    assert [item.identifier for item in profile.nested_identifiers] == ["POP 101", "POP 102"]
    assert profile.risk_codes == ("document_family_candidate", "unsafe_file_metadata_blocked")


def test_quality_profile_metadata_is_stable_and_serializable() -> None:
    profile = build_quality_profile(
        filename="manual-consolidado.txt",
        text="POP 101 - Atendimento\nPOP 102 - Encerramento",
    )

    metadata = quality_profile_to_metadata(profile)

    assert metadata["document_family_candidate"] is True
    assert metadata["nested_identifier_count"] == 2
    assert metadata["unsafe_file_metadata_blocked"] is True
    assert metadata["review_required"] is True
    assert metadata["publication_blocking_risk"] is True
    assert metadata["risk_codes"] == [
        "document_family_candidate",
        "unsafe_file_metadata_blocked",
    ]
    assert metadata["nested_identifiers"][0]["identifier"] == "POP 101"
    assert metadata["nested_identifiers"][0]["line_number"] == 2
    assert metadata["nested_identifiers"][0]["quote"] == "POP 101 - Atendimento"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_quality_profile.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'parsers.quality_profile'`.

- [ ] **Step 3: Implement `quality_profile.py`**

Create `packages/parsers/src/parsers/quality_profile.py`:

```python
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

NESTED_IDENTIFIER_RE = re.compile(
    r"\b(?P<prefix>POP|IT|MAN|MANUAL|POL|PTC|FOR|FR|FRM|REG)"
    r"(?:[ .-][A-Z]{1,8}){0,3}[ .-]\d{1,4}\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NestedIdentifierCandidate:
    identifier: str
    line_number: int
    quote: str
    identifier_type: str


@dataclass(frozen=True)
class ParserQualityProfile:
    document_family_candidate: bool = False
    nested_identifier_count: int = 0
    nested_identifiers: tuple[NestedIdentifierCandidate, ...] = field(default_factory=tuple)
    unsafe_file_metadata_blocked: bool = False
    review_required: bool = False
    publication_blocking_risk: bool = False
    risk_codes: tuple[str, ...] = field(default_factory=tuple)


def build_quality_profile(*, filename: str, text: str) -> ParserQualityProfile:
    identifiers = _nested_identifiers(text)
    distinct_identifiers = {candidate.identifier for candidate in identifiers}
    document_family_candidate = len(distinct_identifiers) >= 2
    risk_codes: list[str] = []
    if document_family_candidate:
        risk_codes.append("document_family_candidate")
        risk_codes.append("unsafe_file_metadata_blocked")
    return ParserQualityProfile(
        document_family_candidate=document_family_candidate,
        nested_identifier_count=len(distinct_identifiers),
        nested_identifiers=tuple(identifiers),
        unsafe_file_metadata_blocked=document_family_candidate,
        review_required=document_family_candidate,
        publication_blocking_risk=document_family_candidate,
        risk_codes=tuple(risk_codes),
    )


def quality_profile_to_metadata(profile: ParserQualityProfile) -> dict[str, Any]:
    return {
        "document_family_candidate": profile.document_family_candidate,
        "nested_identifier_count": profile.nested_identifier_count,
        "nested_identifiers": [asdict(candidate) for candidate in profile.nested_identifiers],
        "unsafe_file_metadata_blocked": profile.unsafe_file_metadata_blocked,
        "review_required": profile.review_required,
        "publication_blocking_risk": profile.publication_blocking_risk,
        "risk_codes": list(profile.risk_codes),
    }


def summarize_quality_profiles(profiles: list[ParserQualityProfile]) -> dict[str, Any]:
    risk_counts = Counter(code for profile in profiles for code in profile.risk_codes)
    return {
        "document_family_candidate_count": sum(
            1 for profile in profiles if profile.document_family_candidate
        ),
        "nested_identifier_count": sum(profile.nested_identifier_count for profile in profiles),
        "review_required_count": sum(1 for profile in profiles if profile.review_required),
        "publication_blocking_risk_count": sum(
            1 for profile in profiles if profile.publication_blocking_risk
        ),
        "risk_code_counts": dict(sorted(risk_counts.items())),
    }


def _nested_identifiers(text: str) -> list[NestedIdentifierCandidate]:
    seen: set[str] = set()
    candidates: list[NestedIdentifierCandidate] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        normalized_line = _normalize_search_text(line)
        for match in NESTED_IDENTIFIER_RE.finditer(normalized_line):
            identifier = _normalize_identifier(match.group(0))
            if identifier in seen:
                continue
            seen.add(identifier)
            candidates.append(
                NestedIdentifierCandidate(
                    identifier=identifier,
                    line_number=line_number,
                    quote=line.strip(),
                    identifier_type=identifier.split(maxsplit=1)[0].split("-", 1)[0].upper(),
                )
            )
    return candidates


def _normalize_identifier(value: str) -> str:
    normalized = _normalize_search_text(value).upper()
    normalized = re.sub(r"\s*-\s*", "-", normalized)
    normalized = re.sub(r"\s*\.\s*", ".", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return normalized.strip(" .:-")


def _normalize_search_text(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_quality_profile.py -q
```

Expected: `2 passed`.

---

### Task 2: Industrial Metadata And Review Integration

**Files:**
- Modify: `packages/parsers/src/parsers/industrial_metadata.py`
- Modify: `packages/parsers/src/parsers/industrial_review.py`
- Modify: `packages/parsers/tests/test_industrial_metadata.py`
- Modify: `packages/parsers/tests/test_industrial_review.py`

- [ ] **Step 1: Write failing metadata tests**

Add to `packages/parsers/tests/test_industrial_metadata.py`:

```python
def test_collection_keeps_nested_identifiers_without_file_level_code() -> None:
    candidate = extract_metadata_candidates(
        filename="manual-consolidado.txt",
        text="\n".join([
            "Manual operacional consolidado",
            "POP 101 - Atendimento inicial",
            "POP 102 - Encerramento",
        ]),
    )

    assert candidate.document_code is None
    assert "ambiguous_nested_document_codes" in candidate.gap_codes
    assert "document_family_candidate" in candidate.gap_codes
    assert [item["identifier"] for item in candidate.nested_identifiers] == ["POP 101", "POP 102"]
    assert candidate.quality_profile["document_family_candidate"] is True
```

- [ ] **Step 2: Write failing review tests**

Add to `packages/parsers/tests/test_industrial_review.py`:

```python
def test_document_family_review_packet_groups_nested_identifier_evidence() -> None:
    packets = build_review_packets(
        document_id="manual-consolidado",
        quality_profile={
            "document_family_candidate": True,
            "publication_blocking_risk": True,
            "nested_identifiers": [
                {"identifier": "POP 101", "line_number": 2, "quote": "POP 101 - Atendimento"},
                {"identifier": "POP 102", "line_number": 3, "quote": "POP 102 - Encerramento"},
            ],
            "risk_codes": ["document_family_candidate", "unsafe_file_metadata_blocked"],
        },
    )

    family_packets = [
        packet for packet in packets if packet.reason_code == "document_family_requires_review"
    ]
    assert len(family_packets) == 1
    assert family_packets[0].severity == "critical"
    assert family_packets[0].suggested_decision == "classify_collection_before_publication"
    assert family_packets[0].risk_codes == (
        "document_family_candidate",
        "unsafe_file_metadata_blocked",
    )
    assert [item["identifier"] for item in family_packets[0].evidence] == ["POP 101", "POP 102"]
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_metadata.py packages\parsers\tests\test_industrial_review.py -q
```

Expected: fail because `nested_identifiers`, `quality_profile` and `quality_profile` review input do not exist.

- [ ] **Step 4: Extend metadata candidate and review builder**

Modify `IndustrialMetadataCandidate` with:

```python
nested_identifiers: list[dict[str, object]] = field(default_factory=list)
quality_profile: dict[str, object] = field(default_factory=dict)
```

In `extract_metadata_candidates`, import and call:

```python
from parsers.quality_profile import build_quality_profile, quality_profile_to_metadata
```

Then:

```python
quality_profile = build_quality_profile(filename=filename, text=text)
quality_profile_metadata = quality_profile_to_metadata(quality_profile)
gap_codes = _gap_codes(code=code, revision=revision, text=text)
if quality_profile.document_family_candidate and "document_family_candidate" not in gap_codes:
    gap_codes.append("document_family_candidate")
return IndustrialMetadataCandidate(
    ...,
    gap_codes=gap_codes,
    nested_identifiers=list(quality_profile_metadata["nested_identifiers"]),
    quality_profile=quality_profile_metadata,
)
```

Modify `build_review_packets` signature:

```python
quality_profile: dict[str, Any] | None = None,
```

Add:

```python
packets.extend(_quality_profile_packets(document_id, quality_profile or {}))
```

Implement:

```python
def _quality_profile_packets(document_id: str, profile: dict[str, Any]) -> list[IndustrialReviewPacket]:
    if profile.get("document_family_candidate") is not True:
        return []
    risk_codes = tuple(sorted({str(code) for code in profile.get("risk_codes", [])}))
    evidence = [
        item for item in profile.get("nested_identifiers", []) if isinstance(item, dict)
    ][:10]
    if not evidence:
        evidence = [{"risk_code": "document_family_candidate"}]
    return [
        IndustrialReviewPacket(
            packet_id=f"{document_id}:document_family_requires_review",
            reason_code="document_family_requires_review",
            severity="critical",
            evidence=evidence,
            suggested_decision="classify_collection_before_publication",
            risk_codes=risk_codes or ("document_family_candidate",),
        )
    ]
```

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_quality_profile.py packages\parsers\tests\test_industrial_metadata.py packages\parsers\tests\test_industrial_review.py -q
```

Expected: all tests pass.

---

### Task 3: Benchmark And Ground Truth Evaluation

**Files:**
- Modify: `scripts/industrial/benchmark_dirty_documents.py`
- Modify: `scripts/quality/parser_ground_truth_eval.py`
- Modify: `tests/smoke/test_parser_ground_truth_eval.py`
- Modify: `examples/parser_ground_truth/manifest.json`
- Add: `examples/parser_ground_truth/document_family_collection.txt`
- Add: `examples/parser_ground_truth/toc_nested_identifier_noise.txt`
- Add: `examples/parser_ground_truth/csv_register_like_rows.csv`

- [ ] **Step 1: Write failing ground truth evaluator tests**

Add to `tests/smoke/test_parser_ground_truth_eval.py`:

```python
def test_ground_truth_evaluates_quality_profile_and_nested_identifiers() -> None:
    evaluator = load_eval()
    manifest = {
        "schema_version": "parser_ground_truth_manifest.v1",
        "documents": [
            {
                "filename": "collection.txt",
                "expected": [
                    {
                        "kind": "quality_profile",
                        "type": "document_family_candidate",
                        "canonical": "true",
                    },
                    {
                        "kind": "nested_identifier",
                        "type": "identifier",
                        "canonical": "POP 101",
                    },
                    {
                        "kind": "metadata",
                        "type": "document_code",
                        "canonical": "POP 101",
                        "negative": True,
                    },
                    {
                        "kind": "review_packet",
                        "type": "reason_code",
                        "canonical": "document_family_requires_review",
                    },
                ],
            }
        ],
    }
    benchmark = {
        "schema_version": "industrial_dirty_benchmark.v1",
        "documents": [
            {
                "file_name": "collection.txt",
                "metadata": {"document_code": None},
                "quality_profile": {
                    "document_family_candidate": True,
                    "nested_identifiers": [{"identifier": "POP 101"}],
                },
                "review_packet_summary": {
                    "reason_code_counts": {"document_family_requires_review": 1},
                },
            }
        ],
    }

    report = evaluator.compute_ground_truth_report(manifest=manifest, benchmark_report=benchmark)

    assert report["status"] == "pass"
    assert report["matched_count"] == 3
    assert report["critical_false_positives"] == 0
```

- [ ] **Step 2: Run evaluator tests and verify RED**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_ground_truth_eval.py -q
```

Expected: fail because `quality_profile` and `nested_identifier` prediction items are unsupported.

- [ ] **Step 3: Include quality profile in benchmark documents**

In `scripts/industrial/benchmark_dirty_documents.py`, pass metadata quality profile to review packets and include it in document rows:

```python
quality_profile = metadata_dict.get("quality_profile")
...
review_packets = build_review_packets(
    document_id=document_id,
    metadata=metadata_dict,
    section_diagnostics=section_diagnostics,
    semantic_candidates=semantic_candidates,
    table_figure_candidates=table_figure_candidates,
    quality_profile=quality_profile if isinstance(quality_profile, dict) else None,
)
...
"quality_profile": quality_profile if isinstance(quality_profile, dict) else {},
```

- [ ] **Step 4: Extend ground truth predictions**

In `parser_ground_truth_eval.py`, add `quality_profile` extraction in `prediction_items`:

```python
quality_profile = document.get("quality_profile")
if isinstance(quality_profile, Mapping):
    items.extend(_quality_profile_prediction_items(filename, quality_profile))
    items.extend(_nested_identifier_prediction_items(filename, quality_profile))
```

Add:

```python
def _quality_profile_prediction_items(filename: str, profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for field in (
        "document_family_candidate",
        "unsafe_file_metadata_blocked",
        "review_required",
        "publication_blocking_risk",
    ):
        value = profile.get(field)
        if isinstance(value, bool):
            items.append(_truth_item(
                filename=filename,
                kind="quality_profile",
                item_type=field,
                canonical="true" if value else "false",
            ))
    return items


def _nested_identifier_prediction_items(filename: str, profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    nested = profile.get("nested_identifiers", [])
    if not isinstance(nested, list):
        return []
    return [
        _truth_item(
            filename=filename,
            kind="nested_identifier",
            item_type="identifier",
            canonical=str(item["identifier"]),
        )
        for item in nested
        if isinstance(item, Mapping) and isinstance(item.get("identifier"), str)
    ]
```

- [ ] **Step 5: Add committed fixtures and manifest expectations**

Append manifest documents for:

```json
{
  "filename": "document_family_collection.txt",
  "expected": [
    {"kind": "quality_profile", "type": "document_family_candidate", "canonical": "true"},
    {"kind": "quality_profile", "type": "unsafe_file_metadata_blocked", "canonical": "true"},
    {"kind": "nested_identifier", "type": "identifier", "canonical": "POP 101"},
    {"kind": "nested_identifier", "type": "identifier", "canonical": "POP 102"},
    {"kind": "metadata", "type": "document_code", "canonical": "POP 101", "negative": true},
    {"kind": "review_packet", "type": "reason_code", "canonical": "document_family_requires_review"}
  ]
}
```

Create `document_family_collection.txt`:

```text
Manual operacional consolidado
POP 101 - Atendimento inicial
Objetivo: orientar a abertura do atendimento.
POP 102 - Encerramento
Objetivo: orientar o encerramento seguro.
```

Create `toc_nested_identifier_noise.txt`:

```text
Sumario
POP 101 Atendimento inicial .... 5
POP 102 Encerramento .... 9
5.1 Deve registrar incidentes
```

Create `csv_register_like_rows.csv`:

```csv
registro,descricao,status
REG 001,Registro de limpeza,ativo
REG 002,Registro de inspecao,ativo
```

- [ ] **Step 6: Run evaluator tests and CLI**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_ground_truth_eval.py -q
uv run --cache-dir .uv-cache python scripts\quality\parser_ground_truth_eval.py
```

Expected: tests pass and CLI exits `0`.

---

### Task 4: Publication Readiness And Documentation

**Files:**
- Modify: `apps/api/src/context_builder/services/context_bundle_service.py`
- Modify: `tests/api/test_context_bundle.py`
- Modify: `docs/07-qa/PARSER_GROUND_TRUTH_EVALUATION.md`
- Modify: `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`
- Modify: `tasks/TASK-040-parser-wide-quality-closure.md`

- [ ] **Step 1: Write failing context bundle test**

Add to `tests/api/test_context_bundle.py` near existing industrial gap tests:

```python
def test_context_bundle_parser_document_family_gap_blocks_readiness() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[],
        rules=[],
        evidence=[],
        open_unknown_count=0,
        blocking_contradiction_count=0,
        gaps=[
            {
                "id": "gap-document-family",
                "kind": "parser_document_family_requires_review",
                "description": "Collection-like parser artifact requires review before publication.",
                "severity": "high",
                "status": "open",
            }
        ],
    )

    assert bundle.readiness.status == "blocked"
    assert "parser_document_family_requires_review" in bundle.readiness.blocking_reasons
```

- [ ] **Step 2: Run test and verify RED**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_bundle.py::test_context_bundle_parser_document_family_gap_blocks_readiness -q
```

Expected: fail because the parser-wide gap kind is not mapped to a blocker.

- [ ] **Step 3: Add parser-wide gap blocker mapping**

In `context_bundle_service.py`, add to `INDUSTRIAL_GAP_BLOCKERS`:

```python
"parser_document_family_requires_review": "parser_document_family_requires_review",
```

This preserves the existing gap path and does not add bundle schema fields.

- [ ] **Step 4: Run targeted tests**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_bundle.py::test_context_bundle_parser_document_family_gap_blocks_readiness tests\api\test_context_bundle.py::test_context_bundle_industrial_gap_blocks_readiness -q
```

Expected: both pass.

- [ ] **Step 5: Update docs and task evidence**

In `docs/07-qa/PARSER_GROUND_TRUTH_EVALUATION.md`, document:

- `quality_profile` expectations;
- `nested_identifier` expectations;
- negative metadata expectations for unsafe file-level promotions.

In `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`, document:

- `quality_profile` document field;
- document-family review behavior;
- no schema change to `context_bundle.v1`.

In `tasks/TASK-040-parser-wide-quality-closure.md`, change status to
`implemented` and record final evidence after the verification task runs.

---

### Task 5: Final Verification And Review

**Files:**
- No new files.
- Review all files modified by Tasks 1-4.

- [ ] **Step 1: Run focused parser tests**

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_quality_profile.py packages\parsers\tests\test_industrial_metadata.py packages\parsers\tests\test_industrial_review.py -q
```

Expected: pass.

- [ ] **Step 2: Run ground truth and context bundle tests**

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_ground_truth_eval.py tests\api\test_context_bundle.py -q
```

Expected: pass.

- [ ] **Step 3: Run CLIs**

```powershell
uv run --cache-dir .uv-cache python scripts\quality\parser_ground_truth_eval.py
uv run --cache-dir .uv-cache python scripts\quality\parser_quality_gate.py --report .run\parser-quality-closure-final.json
```

Expected: both exit `0`. Dirty benchmark may be skipped if `.run\industrial-real` is absent in the worktree.

- [ ] **Step 4: Run lint, type and secret checks**

```powershell
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Expected: all exit `0`.

- [ ] **Step 5: Inspect diff**

```powershell
git diff --stat
git diff --check
git status --short
```

Expected: no whitespace errors; only expected files changed.

- [ ] **Step 6: Commit implementation**

```powershell
git add packages\parsers scripts\industrial scripts\quality tests examples docs tasks apps\api\src\context_builder\services\context_bundle_service.py
git commit -m "feat: close parser-wide quality loop"
```

Expected: commit succeeds.

