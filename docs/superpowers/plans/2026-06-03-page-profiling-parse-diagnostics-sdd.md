# Page Profiling And Parse Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-page diagnostics layer for PDF parsing so industrial documents expose OCR risk, layout risk, table/header/footer signals and page-level evidence before later chunking or semantic extraction.

**Architecture:** Create an additive `parsers.page_profile` module with pure profiling helpers and dataclass outputs. Wire the profile summary into `PDFParser.metadata` and the industrial dirty-document benchmark without changing parsed text, chunk behavior or `context_bundle.v1`.

**Tech Stack:** Python 3.12, dataclasses, PyMuPDF (`fitz`), pytest, ruff, existing parser and industrial benchmark modules.

---

## Execution Model

Use SDD with four explicit roles:

1. **Agent Orchestrator** reads this plan, maintains the checklist, dispatches one task at a time, prevents overlapping file ownership and resolves blockers.
2. **Agent Task** uses `superpowers:test-driven-development`, writes failing tests first, implements only the assigned task and reports changed paths.
3. **Agent Reviewer** runs two reviews after each task: spec compliance first, then code quality.
4. **Agent Approval** runs the final verification gates and refuses completion if docs, tests, compatibility or benchmark evidence are missing.

Do not dispatch multiple Agent Task workers against the same files. Do not add OCR, vision, table extraction, section tree changes or bundle schema changes in this task.

## File Map

Create:

- `packages/parsers/src/parsers/page_profile.py`
- `packages/parsers/tests/test_page_profile.py`

Modify:

- `packages/parsers/src/parsers/pdf.py`
- `packages/parsers/tests/test_pdf.py`
- `scripts/industrial/benchmark_dirty_documents.py`
- `tests/smoke/test_industrial_dirty_benchmark.py`
- `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`
- `tasks/TASK-026-page-profiling-parse-diagnostics.md`

Do not modify:

- `apps/api/src/context_builder/schemas/context_bundle.py`
- `examples/context_bundle/context-bundle.v1.schema.json`
- Supabase migrations

## Task 1: Page Profile Model And Helper

**Agent:** Agent Task

**Files:**
- Create: `packages/parsers/src/parsers/page_profile.py`
- Create: `packages/parsers/tests/test_page_profile.py`

- [ ] **Step 1: Write failing page profile tests**

Create `packages/parsers/tests/test_page_profile.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from parsers.page_profile import profile_pdf_pages, summarize_page_profiles

fitz = pytest.importorskip("fitz")

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05"
    b"\xfe\x02\xfeA\xe2&\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_profile_pdf_pages_detects_text_header_footer_and_table(tmp_path: Path) -> None:
    path = tmp_path / "industrial.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 36), "POP-O-SNVS-010 Rev. 04")
    page.insert_text((72, 120), "5. RESPONSABILIDADES")
    page.insert_text((72, 150), "Atividade | Responsavel | Registro")
    page.insert_text((72, 800), "Pagina 1 de 1")
    document.save(path)

    profiles = profile_pdf_pages(path)

    assert len(profiles) == 1
    profile = profiles[0]
    assert profile.page_number == 1
    assert profile.text_chars > 0
    assert profile.line_count >= 4
    assert profile.block_count >= 4
    assert profile.image_count == 0
    assert profile.table_candidates == 1
    assert profile.ocr_required is False
    assert profile.text_layer_type == "digital_text"
    assert profile.header_detected is True
    assert profile.footer_detected is True
    assert "table_candidates_present" in profile.risk_codes


def test_profile_pdf_pages_marks_image_only_page_as_ocr_required(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_image(fitz.Rect(72, 72, 180, 180), stream=PNG_1X1)
    document.save(path)

    profiles = profile_pdf_pages(path)

    assert len(profiles) == 1
    profile = profiles[0]
    assert profile.text_chars == 0
    assert profile.image_count == 1
    assert profile.empty_page is False
    assert profile.ocr_required is True
    assert profile.text_layer_type == "scanned_image"
    assert "ocr_required" in profile.risk_codes


def test_summarize_page_profiles_returns_stable_counts(tmp_path: Path) -> None:
    path = tmp_path / "mixed.pdf"
    document = fitz.open()
    text_page = document.new_page()
    text_page.insert_text((72, 72), "Codigo: POP-QA-014")
    image_page = document.new_page()
    image_page.insert_image(fitz.Rect(72, 72, 180, 180), stream=PNG_1X1)
    document.save(path)

    summary = summarize_page_profiles(profile_pdf_pages(path))

    assert summary["page_count"] == 2
    assert summary["ocr_required_pages"] == [2]
    assert summary["empty_pages"] == []
    assert summary["image_only_pages"] == [2]
    assert summary["risk_code_counts"]["ocr_required"] == 1
```

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_page_profile.py -q
```

Expected: FAIL because `parsers.page_profile` does not exist.

- [ ] **Step 2: Implement the page profile helper**

Create `packages/parsers/src/parsers/page_profile.py`:

```python
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PageProfile:
    page_number: int
    text_chars: int
    line_count: int
    block_count: int
    image_count: int
    table_candidates: int
    ocr_required: bool
    text_layer_type: str
    layout_complexity: str
    rotation: int
    empty_page: bool
    header_detected: bool
    footer_detected: bool
    risk_codes: list[str] = field(default_factory=list)


def profile_pdf_pages(path: Path, *, max_pages: int | None = None) -> list[PageProfile]:
    import fitz

    with fitz.open(path) as document:
        return profile_fitz_document(document, max_pages=max_pages)


def profile_fitz_document(document: Any, *, max_pages: int | None = None) -> list[PageProfile]:
    profiles: list[PageProfile] = []
    for index, page in enumerate(document, start=1):
        if max_pages is not None and index > max_pages:
            break
        text = page.get_text("text").strip()
        blocks = list(page.get_text("blocks"))
        image_count = len(page.get_images(full=True))
        line_count = _line_count(text)
        block_count = _text_block_count(blocks)
        table_candidates = _table_candidate_count(text)
        text_chars = len(text)
        rotation = int(getattr(page, "rotation", 0) or 0)
        empty_page = text_chars == 0 and image_count == 0
        ocr_required = text_chars == 0 and image_count > 0
        text_layer_type = _text_layer_type(text_chars=text_chars, image_count=image_count)
        layout_complexity = _layout_complexity(
            block_count=block_count,
            image_count=image_count,
            table_candidates=table_candidates,
        )
        header_detected, footer_detected = _header_footer_flags(page, blocks)
        risk_codes = _risk_codes(
            empty_page=empty_page,
            ocr_required=ocr_required,
            rotation=rotation,
            layout_complexity=layout_complexity,
            table_candidates=table_candidates,
            text_chars=text_chars,
            image_count=image_count,
        )
        profiles.append(
            PageProfile(
                page_number=index,
                text_chars=text_chars,
                line_count=line_count,
                block_count=block_count,
                image_count=image_count,
                table_candidates=table_candidates,
                ocr_required=ocr_required,
                text_layer_type=text_layer_type,
                layout_complexity=layout_complexity,
                rotation=rotation,
                empty_page=empty_page,
                header_detected=header_detected,
                footer_detected=footer_detected,
                risk_codes=risk_codes,
            )
        )
    return profiles


def page_profiles_to_metadata(profiles: list[PageProfile]) -> list[dict[str, Any]]:
    return [asdict(profile) for profile in profiles]


def summarize_page_profiles(profiles: list[PageProfile]) -> dict[str, Any]:
    risk_codes = Counter(code for profile in profiles for code in profile.risk_codes)
    layout_counts = Counter(profile.layout_complexity for profile in profiles)
    text_layer_counts = Counter(profile.text_layer_type for profile in profiles)
    return {
        "page_count": len(profiles),
        "ocr_required_pages": [
            profile.page_number for profile in profiles if profile.ocr_required
        ],
        "empty_pages": [
            profile.page_number for profile in profiles if profile.empty_page
        ],
        "image_only_pages": [
            profile.page_number
            for profile in profiles
            if profile.text_layer_type == "scanned_image"
        ],
        "table_candidate_pages": [
            profile.page_number
            for profile in profiles
            if profile.table_candidates > 0
        ],
        "layout_complexity_counts": dict(sorted(layout_counts.items())),
        "text_layer_type_counts": dict(sorted(text_layer_counts.items())),
        "risk_code_counts": dict(sorted(risk_codes.items())),
    }


def _line_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


def _text_block_count(blocks: list[Any]) -> int:
    return sum(1 for block in blocks if _block_text(block).strip())


def _table_candidate_count(text: str) -> int:
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.count("|") >= 2:
            count += 1
            continue
        if len(re.split(r"\s{2,}", stripped)) >= 3:
            count += 1
    return count


def _text_layer_type(*, text_chars: int, image_count: int) -> str:
    if text_chars > 0 and image_count > 0:
        return "mixed"
    if text_chars > 0:
        return "digital_text"
    if image_count > 0:
        return "scanned_image"
    return "empty"


def _layout_complexity(*, block_count: int, image_count: int, table_candidates: int) -> str:
    if block_count >= 18 or image_count >= 4 or table_candidates >= 3:
        return "high"
    if block_count >= 8 or image_count >= 1 or table_candidates >= 1:
        return "medium"
    return "low"


def _header_footer_flags(page: Any, blocks: list[Any]) -> tuple[bool, bool]:
    page_height = float(page.rect.height or 0)
    if page_height <= 0:
        return False, False
    top_cutoff = page_height * 0.15
    bottom_cutoff = page_height * 0.85
    header = False
    footer = False
    for block in blocks:
        text = _block_text(block).strip()
        if not text:
            continue
        y0 = float(block[1])
        y1 = float(block[3])
        header = header or y0 <= top_cutoff
        footer = footer or y1 >= bottom_cutoff
    return header, footer


def _block_text(block: Any) -> str:
    if len(block) >= 5 and isinstance(block[4], str):
        return block[4]
    return ""


def _risk_codes(
    *,
    empty_page: bool,
    ocr_required: bool,
    rotation: int,
    layout_complexity: str,
    table_candidates: int,
    text_chars: int,
    image_count: int,
) -> list[str]:
    codes: list[str] = []
    if empty_page:
        codes.append("empty_page")
    if ocr_required:
        codes.append("ocr_required")
    if rotation not in (0, 360):
        codes.append("rotated_page")
    if layout_complexity == "high":
        codes.append("high_layout_complexity")
    if table_candidates > 0:
        codes.append("table_candidates_present")
    if 0 < text_chars < 100 and image_count > 0:
        codes.append("sparse_text_with_images")
    return codes
```

- [ ] **Step 3: Verify Task 1**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_page_profile.py -q
uv run --cache-dir .uv-cache ruff check packages\parsers\src\parsers\page_profile.py packages\parsers\tests\test_page_profile.py
```

Expected: PASS.

## Task 2: PDF Parser Metadata Integration

**Agent:** Agent Task

**Files:**
- Modify: `packages/parsers/src/parsers/pdf.py`
- Modify: `packages/parsers/tests/test_pdf.py`

- [ ] **Step 1: Write failing parser metadata test**

Append this test to `packages/parsers/tests/test_pdf.py`:

```python
def test_pdf_parser_adds_page_profile_metadata(tmp_path: Path) -> None:
    path = tmp_path / "profiled.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 36), "POP-QA-014 Rev. 04")
    page.insert_text((72, 150), "Atividade | Responsavel | Registro")
    document.save(path)

    result = PDFParser().extract(path)

    assert result.error is None
    assert result.metadata["parser"] == "pdf"
    profiles = result.metadata["page_profiles"]
    assert profiles[0]["page_number"] == 1
    assert profiles[0]["text_layer_type"] == "digital_text"
    assert profiles[0]["table_candidates"] == 1
    summary = result.metadata["page_profile_summary"]
    assert summary["page_count"] == 1
    assert summary["table_candidate_pages"] == [1]
```

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_pdf.py::test_pdf_parser_adds_page_profile_metadata -q
```

Expected: FAIL because metadata does not include page profiles.

- [ ] **Step 2: Wire profiles into `PDFParser`**

In `packages/parsers/src/parsers/pdf.py`, add imports:

```python
from parsers.page_profile import (
    page_profiles_to_metadata,
    profile_fitz_document,
    summarize_page_profiles,
)
```

Inside `PDFParser.extract()`, after the `MAX_PDF_PAGES` guard and before the page text loop, add:

```python
                page_profiles = profile_fitz_document(document)
```

Replace the final metadata payload:

```python
                    metadata={
                        "parser": "pdf",
                        "page_profiles": page_profiles_to_metadata(page_profiles),
                        "page_profile_summary": summarize_page_profiles(page_profiles),
                    },
```

Keep the `pages_exceeded` branch unchanged so huge PDFs still return the same parser error.

- [ ] **Step 3: Verify Task 2**

Run:

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_pdf.py packages\parsers\tests\test_page_profile.py -q
```

Expected: PASS.

## Task 3: Benchmark Diagnostic Summary

**Agent:** Agent Task

**Files:**
- Modify: `scripts/industrial/benchmark_dirty_documents.py`
- Modify: `tests/smoke/test_industrial_dirty_benchmark.py`

- [ ] **Step 1: Write failing benchmark JSON tests**

Append this assertion block to
`test_benchmark_writes_stable_json_shape_for_successful_document` in
`tests/smoke/test_industrial_dirty_benchmark.py`:

```python
    assert document["page_profile_summary"] == {
        "page_count": 0,
        "ocr_required_pages": [],
        "empty_pages": [],
        "image_only_pages": [],
        "table_candidate_pages": [],
        "layout_complexity_counts": {},
        "text_layer_type_counts": {},
        "risk_code_counts": {},
    }
```

Append this assertion to
`test_benchmark_splits_pages_exceeded_pdf_across_two_workers`:

```python
    assert document["page_profile_summary"]["page_count"] == 0
```

Add a new PDF-specific test:

```python
def test_benchmark_includes_pdf_page_profile_summary(tmp_path: Path) -> None:
    benchmark = load_benchmark()
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    output = tmp_path / "benchmark.json"
    path = input_dir / "POP-QA-014_Rev04.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 36), "Codigo: POP-QA-014")
    page.insert_text((72, 150), "Atividade | Responsavel | Registro")
    document.save(path)

    code = run_cli(benchmark, ["--input-dir", str(input_dir), "--output", str(output)])

    assert code == 0
    page_summary = read_report(output)["documents"][0]["page_profile_summary"]
    assert page_summary["page_count"] == 1
    assert page_summary["table_candidate_pages"] == [1]
    assert page_summary["text_layer_type_counts"]["digital_text"] == 1
```

At the top of `tests/smoke/test_industrial_dirty_benchmark.py`, add:

```python
import pytest

fitz = pytest.importorskip("fitz")
```

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py -q
```

Expected: FAIL because benchmark documents do not include `page_profile_summary`.

- [ ] **Step 2: Add benchmark summary extraction**

In `scripts/industrial/benchmark_dirty_documents.py`, add this helper:

```python
def _page_profile_summary(result: Any) -> dict[str, Any]:
    default = {
        "page_count": 0,
        "ocr_required_pages": [],
        "empty_pages": [],
        "image_only_pages": [],
        "table_candidate_pages": [],
        "layout_complexity_counts": {},
        "text_layer_type_counts": {},
        "risk_code_counts": {},
    }
    if result is None:
        return default
    summary = result.metadata.get("page_profile_summary")
    if isinstance(summary, dict):
        return summary
    return default
```

In the `benchmark_document()` return payload, add:

```python
        "page_profile_summary": _page_profile_summary(result),
```

For the split-page fallback, keep `page_profile_summary` at the default because
the fallback extracts text ranges without preserving one profile per page.

- [ ] **Step 3: Verify Task 3**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py packages\parsers\tests\test_pdf.py packages\parsers\tests\test_page_profile.py -q
```

Expected: PASS.

## Task 4: Documentation And Task Evidence

**Agent:** Agent Task

**Files:**
- Modify: `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`
- Modify: `tasks/TASK-026-page-profiling-parse-diagnostics.md`

- [ ] **Step 1: Document the diagnostic fields**

Add this section to `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`:

```markdown
## Page Profile Diagnostics

Each PDF parsed through the normal `PDFParser` path now emits a
`page_profile_summary` object in the benchmark report. The summary is a routing
signal for later extraction strategy decisions, not an OCR or vision result.

Fields:

- `page_count`: number of profiled pages.
- `ocr_required_pages`: pages with embedded images and no extracted text.
- `empty_pages`: pages with no extracted text and no embedded images.
- `image_only_pages`: pages classified as `scanned_image`.
- `table_candidate_pages`: pages with simple table-like text signals.
- `layout_complexity_counts`: counts for `low`, `medium` and `high`.
- `text_layer_type_counts`: counts for `digital_text`, `mixed`,
  `scanned_image` and `empty`.
- `risk_code_counts`: aggregate parse risk codes such as `ocr_required`,
  `table_candidates_present`, `rotated_page` and `high_layout_complexity`.

The profiler deliberately does not extract table cells, interpret figures,
perform OCR or change chunk boundaries. Those behaviors remain follow-up tasks.
```

- [ ] **Step 2: Update task execution evidence**

In `tasks/TASK-026-page-profiling-parse-diagnostics.md`, change status to:

```markdown
Status: implemented; awaiting real benchmark evidence
```

After running the benchmark locally, generate the diagnostic counts with this
command:

```powershell
@'
import json
from pathlib import Path

report = json.loads(Path(".run/industrial-real/benchmark-latest.json").read_text(encoding="utf-8"))
summary = report["summary"]
documents = report["documents"]
ocr_required = sum(
    len(document["page_profile_summary"]["ocr_required_pages"])
    for document in documents
)
image_only = sum(
    len(document["page_profile_summary"]["image_only_pages"])
    for document in documents
)
table_candidate = sum(
    len(document["page_profile_summary"]["table_candidate_pages"])
    for document in documents
)
print(f"- documents: {summary['document_count']}")
print(f"- parsed: {summary['parsed_count']}")
print(f"- OCR-required pages: {ocr_required}")
print(f"- image-only pages: {image_only}")
print(f"- table-candidate pages: {table_candidate}")
'@ | python -
```

Append an `Execution Evidence` section that includes the focused test commands,
the real benchmark command and the five lines printed by the diagnostic-count
command above. The numbers must exactly match the current benchmark JSON.

```markdown
## Execution Evidence

Focused tests:

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_page_profile.py packages\parsers\tests\test_pdf.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py -q
```

Real benchmark:

```powershell
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
```
```

- [ ] **Step 3: Verify docs**

Run:

```powershell
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Expected: PASS.

## Task 5: Agent Reviewer Gate

**Agent:** Agent Reviewer

**Files:**
- No production files unless fixing review findings.

- [ ] **Step 1: Spec compliance review**

Review the patch against `tasks/TASK-026-page-profiling-parse-diagnostics.md`
and this plan. Confirm:

- page diagnostics are additive;
- existing parser text behavior is unchanged;
- `pages_exceeded` behavior is unchanged;
- image-only pages are marked OCR-required;
- header/footer are only signals, not metadata resolvers;
- table support is only candidate counting;
- no bundle schema, Supabase or API contract changes were added.

If any item fails, send findings back to Agent Task and re-review after fixes.

- [ ] **Step 2: Code quality review**

Review for:

- deterministic output ordering;
- simple heuristics with readable names;
- no absolute local paths in benchmark JSON;
- no hidden network access;
- no broad exception swallowing outside existing parser behavior;
- tests covering both success and risk cases.

If any item fails, send findings back to Agent Task and re-review after fixes.

## Task 6: Agent Approval Gate

**Agent:** Agent Approval

**Files:**
- No production files unless fixing approval findings.

- [ ] **Step 1: Run focused verification**

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_page_profile.py packages\parsers\tests\test_pdf.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py -q
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Expected: PASS.

- [ ] **Step 2: Run real benchmark when local corpus is present**

```powershell
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
```

Expected: PASS when `.run\industrial-real` exists. If the corpus is absent,
record that the local real benchmark was skipped because the input directory is
not present.

- [ ] **Step 3: Approval checklist**

Approval must confirm:

- no OCR implementation entered this slice;
- no vision model call entered this slice;
- no table row/cell extractor entered this slice;
- no section tree or chunking behavior changed;
- `context_bundle.v1` compatibility is untouched;
- benchmark JSON has stable diagnostic fields;
- docs state limitations and follow-up tasks;
- dirty worktree changes outside this task were not reverted.

## Success Criteria

The task is complete only when:

1. `profile_pdf_pages()` has unit coverage for digital text, image-only and summary output.
2. `PDFParser.extract()` includes `page_profiles` and `page_profile_summary`.
3. Existing PDF parser tests still pass.
4. Industrial benchmark reports include `page_profile_summary`.
5. Documentation explains the diagnostic meaning and limits.
6. Agent Reviewer approves spec compliance and code quality.
7. Agent Approval runs or explicitly records all verification gates.
