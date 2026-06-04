from __future__ import annotations

import argparse
import json
import mimetypes
import re
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any

from parsers import UnsupportedMimeError, get_parser
from parsers.base import ExtractionError, sanitize_text, truncate_to_limit
from parsers.industrial_metadata import extract_metadata_candidates
from parsers.industrial_structure import extract_structure_hints
from parsers.quality_gate import run_quality_gate

SCHEMA_VERSION = "industrial_dirty_benchmark.v1"
SUPPORTED_EXTENSIONS = {".csv", ".docx", ".pdf", ".txt", ".xlsx"}
DEFAULT_EXPECTED_DOCUMENTS: dict[str, dict[str, str]] = {
    "pop-o-snvs-010-rev4.pdf": {"expected_code": "POP-O-SNVS-010"},
    "bluesun-blu002-kit-fotovoltaico.pdf": {"expected_code": "BLU002"},
    "cispar-pop-005-inspecao-concreto.pdf": {"expected_code": "POP 005"},
    "hospitalregional-higienizacao-maos-figuras.pdf": {
        "expected_code": "PTC.DEPQI-SCIRAS.001",
        "expected_revision": "1.0.0",
    },
    "ponte-pop-pmpr-fotos.pdf": {"expected_processing_mode": "split_pages"},
}


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        input_dir=args.input_dir,
        manifest_path=args.manifest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote benchmark report: {args.output}")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark industrial parser behavior on dirty technical documents.",
    )
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    return parser.parse_args(argv)


def build_report(*, input_dir: Path, manifest_path: Path | None = None) -> dict[str, Any]:
    input_root = input_dir.resolve()
    expected_documents = _load_expected_documents(manifest_path)
    documents = [
        benchmark_document(path=path, root=input_root, expected_documents=expected_documents)
        for path in _iter_input_documents(input_root)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "input_root": input_dir.name,
        "expected_documents": _expected_document_summary(documents, expected_documents),
        "summary": _summary(documents),
        "documents": documents,
    }


def benchmark_document(
    *,
    path: Path,
    root: Path,
    expected_documents: dict[str, dict[str, str]],
) -> dict[str, Any]:
    relative_path = _relative_path(path, root)
    mime_type = _mime_type(path)
    pdf_metrics = _pdf_metrics(path) if path.suffix.lower() == ".pdf" else {}
    started = time.perf_counter()
    result = None
    unsupported_error: str | None = None
    try:
        result = get_parser(mime_type).extract(path)
    except UnsupportedMimeError:
        unsupported_error = "unsupported_format"

    text = _extracted_text(result)
    metadata = extract_metadata_candidates(filename=path.name, text=text)
    structure_hints = extract_structure_hints(text)
    quality = run_quality_gate(result) if result is not None else None
    parser_error = unsupported_error or _parser_error(result)
    processing = _default_processing()
    original_parser_error = parser_error

    if parser_error == ExtractionError.PAGES_EXCEEDED.value and path.suffix.lower() == ".pdf":
        fallback = _split_pages_extraction(path=path, pdf_metrics=pdf_metrics)
        if fallback["text"]:
            text = str(fallback["text"])
            metadata = extract_metadata_candidates(filename=path.name, text=text)
            structure_hints = extract_structure_hints(text)
            parser_error = None
            quality = None
            processing = {
                "mode": "split_pages",
                "worker_count": 2,
                "original_parser_error": original_parser_error,
                "page_ranges": fallback["page_ranges"],
            }

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    metadata_dict = asdict(metadata)
    gap_codes = list(metadata.gap_codes)
    extracted_char_count = (
        len(text)
        if processing["mode"] == "split_pages"
        else result.total_chars if result is not None else 0
    )
    return {
        "document_id": _document_id(relative_path),
        "relative_path": relative_path,
        "file_name": path.name,
        "extension": path.suffix.lower(),
        "mime_type": mime_type,
        "file_size_bytes": path.stat().st_size,
        "file_size_kb": round(path.stat().st_size / 1024, 1),
        "page_count": pdf_metrics.get("page_count") if pdf_metrics else _page_count(result),
        "page_profile_summary": _page_profile_summary(
            result=result,
            path=path,
            parser_error=parser_error,
            processing=processing,
        ),
        "sheet_count": len(result.sheets) if result is not None else 0,
        "embedded_image_count": pdf_metrics.get("embedded_image_count"),
        "parser_error": parser_error,
        "processing": processing,
        "elapsed_ms": elapsed_ms,
        "extracted_char_count": extracted_char_count,
        "quality": _quality_payload(quality, parser_error, text=text),
        "metadata": metadata_dict,
        "gap_codes": sorted(gap_codes),
        "structure_hint_count": len(structure_hints),
        "known_findings": _known_findings(
            file_name=path.name,
            metadata=metadata_dict,
            parser_error=parser_error,
            processing=processing,
            expected_documents=expected_documents,
        ),
    }


def _iter_input_documents(input_root: Path) -> list[Path]:
    if not input_root.exists():
        raise FileNotFoundError(f"input directory not found: {input_root}")
    return sorted(
        (
            path
            for path in input_root.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: path.relative_to(input_root).as_posix(),
    )


def _load_expected_documents(manifest_path: Path | None) -> dict[str, dict[str, str]]:
    if manifest_path is None:
        return DEFAULT_EXPECTED_DOCUMENTS
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = payload.get("documents", [])
    expected: dict[str, dict[str, str]] = {}
    for item in documents:
        if not isinstance(item, dict) or not isinstance(item.get("filename"), str):
            continue
        expected[item["filename"]] = {
            key: value
            for key, value in item.items()
            if key != "filename" and isinstance(value, str)
        }
    return expected


def _expected_document_summary(
    documents: list[dict[str, Any]],
    expected_documents: dict[str, dict[str, str]],
) -> dict[str, Any]:
    present = sorted({
        document["file_name"]
        for document in documents
        if document["file_name"] in expected_documents
    })
    missing = sorted(set(expected_documents) - set(present))
    return {
        "configured_count": len(expected_documents),
        "present_count": len(present),
        "missing": missing,
    }


def _summary(documents: list[dict[str, Any]]) -> dict[str, Any]:
    parser_errors = Counter(
        document["parser_error"]
        for document in documents
        if document["parser_error"] is not None
    )
    gap_counts = Counter(
        gap
        for document in documents
        for gap in document["gap_codes"]
    )
    return {
        "document_count": len(documents),
        "parsed_count": sum(1 for document in documents if document["parser_error"] is None),
        "failed_count": sum(1 for document in documents if document["parser_error"] is not None),
        "split_processed_count": sum(
            1
            for document in documents
            if document["processing"]["mode"] == "split_pages"
        ),
        "total_pages": sum(
            document["page_count"]
            for document in documents
            if isinstance(document["page_count"], int)
        ),
        "total_images": sum(
            document["embedded_image_count"]
            for document in documents
            if isinstance(document["embedded_image_count"], int)
        ),
        "total_extracted_chars": sum(document["extracted_char_count"] for document in documents),
        "parser_errors": dict(sorted(parser_errors.items())),
        "gap_counts": dict(sorted(gap_counts.items())),
    }


def _mime_type(path: Path) -> str:
    if path.suffix.lower() == ".txt":
        return "text/plain"
    if path.suffix.lower() == ".csv":
        return "text/csv"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _pdf_metrics(path: Path) -> dict[str, int] | dict[str, None]:
    try:
        import fitz  # type: ignore[import-untyped]

        with fitz.open(path) as document:
            return {
                "page_count": document.page_count,
                "embedded_image_count": sum(
                    len(page.get_images(full=True))
                    for page in document
                ),
            }
    except Exception:
        return {"page_count": None, "embedded_image_count": None}


def _split_pages_extraction(
    *,
    path: Path,
    pdf_metrics: dict[str, int] | dict[str, None],
) -> dict[str, Any]:
    page_count = pdf_metrics.get("page_count")
    if not isinstance(page_count, int) or page_count <= 0:
        return {"text": "", "page_ranges": []}
    page_ranges = _two_worker_page_ranges(page_count)
    text = _extract_pdf_text_with_workers(path=path, page_ranges=page_ranges)
    return {"text": text, "page_ranges": [list(item) for item in page_ranges]}


def _two_worker_page_ranges(page_count: int) -> list[tuple[int, int]]:
    midpoint = (page_count + 1) // 2
    return [(0, midpoint), (midpoint, page_count)]


def _extract_pdf_text_with_workers(
    *,
    path: Path,
    page_ranges: list[tuple[int, int]],
) -> str:
    with ThreadPoolExecutor(max_workers=2) as executor:
        parts = list(executor.map(
            lambda page_range: _extract_pdf_text_range(path, page_range),
            page_ranges,
        ))
    text = "\n".join(part for part in parts if part)
    text, _truncated = truncate_to_limit(text, 0)
    return text


def _extract_pdf_text_range(path: Path, page_range: tuple[int, int]) -> str:
    start, end = page_range
    try:
        import fitz

        with fitz.open(path) as document:
            chunks = [
                sanitize_text(document[index].get_text("text"))
                for index in range(start, min(end, document.page_count))
            ]
        return "\n".join(chunk for chunk in chunks if chunk)
    except Exception:
        return ""


def _page_count(result: Any) -> int:
    if result is None:
        return 0
    return len(result.pages)


def _page_profile_summary(
    *,
    result: Any,
    path: Path,
    parser_error: str | None,
    processing: dict[str, Any],
) -> dict[str, Any]:
    if (
        path.suffix.lower() == ".pdf"
        and result is not None
        and parser_error is None
        and processing.get("mode") == "single_parser"
    ):
        summary = result.metadata.get("page_profile_summary")
        if isinstance(summary, dict):
            return dict(summary)
    return _default_page_profile_summary()


def _default_page_profile_summary() -> dict[str, Any]:
    return {
        "page_count": 0,
        "text_pages": 0,
        "image_pages": 0,
        "ocr_required_pages": [],
        "ocr_risk_pages": [],
        "empty_pages": [],
        "image_only_pages": [],
        "table_candidate_pages": [],
        "table_risk_pages": [],
        "header_detected_pages": [],
        "footer_detected_pages": [],
        "layout_complexity_counts": {},
        "layout_complexity": {},
        "text_layer_type_counts": {},
        "risk_code_counts": {},
        "risk_codes": {},
    }


def _parser_error(result: Any) -> str | None:
    if result is None or result.error is None:
        return None
    return str(result.error.value)


def _extracted_text(result: Any) -> str:
    if result is None:
        return ""
    page_text = "\n".join(page.text for page in result.pages)
    sheet_text = "\n".join(
        " ".join(str(value) for row in sheet.rows for value in row.values())
        for sheet in result.sheets
    )
    return "\n".join(part for part in (page_text, sheet_text) if part)


def _quality_payload(quality: Any, parser_error: str | None, *, text: str) -> dict[str, Any]:
    if parser_error is None and quality is None:
        if len(text) < 100:
            return {
                "passed": False,
                "rejection_reason": "too_short",
                "warnings": [],
                "empty_pages": 0,
            }
        return {
            "passed": True,
            "rejection_reason": None,
            "warnings": [],
            "empty_pages": 0,
        }
    if quality is None:
        return {
            "passed": False,
            "rejection_reason": parser_error,
            "warnings": [],
            "empty_pages": 0,
        }
    return {
        "passed": quality.passed,
        "rejection_reason": quality.rejection_reason,
        "warnings": sorted(quality.warnings),
        "empty_pages": quality.empty_pages,
    }


def _default_processing() -> dict[str, Any]:
    return {
        "mode": "single_parser",
        "worker_count": 1,
        "original_parser_error": None,
        "page_ranges": [],
    }


def _known_findings(
    *,
    file_name: str,
    metadata: dict[str, Any],
    parser_error: str | None,
    processing: dict[str, Any],
    expected_documents: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    expected = expected_documents.get(file_name) or expected_documents.get(Path(file_name).stem)
    if not expected:
        return []
    findings: list[dict[str, Any]] = []
    expected_code = expected.get("expected_code")
    if expected_code and metadata.get("document_code") != expected_code:
        findings.append({
            "kind": "expected_code_missed",
            "expected": expected_code,
            "actual": metadata.get("document_code"),
        })
    expected_revision = expected.get("expected_revision")
    if expected_revision and metadata.get("revision") != expected_revision:
        findings.append({
            "kind": "expected_revision_missed",
            "expected": expected_revision,
            "actual": metadata.get("revision"),
        })
    expected_parser_error = expected.get("expected_parser_error")
    if expected_parser_error and parser_error != expected_parser_error:
        findings.append({
            "kind": "expected_parser_error_changed",
            "expected": expected_parser_error,
            "actual": parser_error,
        })
    expected_processing_mode = expected.get("expected_processing_mode")
    if expected_processing_mode and processing.get("mode") != expected_processing_mode:
        findings.append({
            "kind": "expected_processing_mode_changed",
            "expected": expected_processing_mode,
            "actual": processing.get("mode"),
        })
    return findings


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _document_id(relative_path: str) -> str:
    stem = str(Path(relative_path).with_suffix("")).replace("\\", "/")
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


if __name__ == "__main__":
    raise SystemExit(main())
