from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

SCHEMA_VERSION = "parser_ground_truth_eval.v1"
MANIFEST_SCHEMA_VERSION = "parser_ground_truth_manifest.v1"
PRECISION_MIN = 0.85
RECALL_MIN = 0.75
DEFAULT_MANIFEST = Path("examples/parser_ground_truth/manifest.json")
DEFAULT_INPUT_DIR = Path("examples/parser_ground_truth")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    manifest_path = _resolve_repo_path(repo_root, args.manifest)
    input_dir = _resolve_repo_path(repo_root, args.input_dir)

    try:
        manifest = load_manifest(manifest_path)
        benchmark_report = (
            _load_json(_resolve_repo_path(repo_root, args.benchmark_report))
            if args.benchmark_report
            else build_benchmark_report(repo_root=repo_root, input_dir=input_dir, manifest_path=manifest_path)
        )
        report = compute_ground_truth_report(
            manifest=manifest,
            benchmark_report=benchmark_report,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(_safe_error_message(exc, repo_root=repo_root), file=sys.stderr)
        return 2

    rendered = render_report_json(report)
    if args.report:
        report_path = _resolve_repo_path(repo_root, args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "pass" else 1


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Parser benchmark outputs to committed ground truth expectations.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--benchmark-report", type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args(argv)


def load_manifest(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"Manifest schema_version must be {MANIFEST_SCHEMA_VERSION}: {path.name}",
        )
    documents = payload.get("documents")
    if not isinstance(documents, list):
        raise ValueError("Manifest must contain a documents list")
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            raise ValueError(f"Manifest document {index} must be an object")
        if not isinstance(document.get("filename"), str) or not document["filename"]:
            raise ValueError(f"Manifest document {index} must contain filename")
        expected = document.get("expected", [])
        if not isinstance(expected, list):
            raise ValueError(f"Manifest document {document['filename']} expected must be a list")
        for expected_index, item in enumerate(expected):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Manifest document {document['filename']} expected item {expected_index} must be an object",
                )
            for key in ("kind", "type", "canonical"):
                if not isinstance(item.get(key), str) or not item[key]:
                    raise ValueError(
                        f"Manifest document {document['filename']} expected item {expected_index} missing {key}",
                    )
    return payload


def build_benchmark_report(*, repo_root: Path, input_dir: Path, manifest_path: Path) -> dict[str, Any]:
    benchmark = _load_benchmark_module(repo_root)
    if hasattr(benchmark, "build_report_with_options"):
        return cast(
            "dict[str, Any]",
            benchmark.build_report_with_options(
                input_dir=input_dir,
                manifest_path=manifest_path,
                include_candidate_details=True,
            ),
        )
    return cast(
        "dict[str, Any]",
        benchmark.build_report(input_dir=input_dir, manifest_path=manifest_path),
    )


def compute_ground_truth_report(
    *,
    manifest: Mapping[str, Any],
    benchmark_report: Mapping[str, Any],
) -> dict[str, Any]:
    expected_items = expected_truth_items(manifest)
    predicted_items = scoped_prediction_items(
        manifest=manifest,
        benchmark_report=benchmark_report,
    )
    expected_positive = {
        item["key"]
        for item in expected_items
        if item["negative"] is False
    }
    expected_negative = {
        item["key"]
        for item in expected_items
        if item["negative"] is True
    }
    predicted_keys = {item["key"] for item in predicted_items}

    matched = expected_positive & predicted_keys
    missing = expected_positive - predicted_keys
    false_positives = predicted_keys - expected_positive
    negative_false_positives = false_positives & expected_negative

    precision = _rate(len(matched), len(predicted_keys))
    recall = _rate(len(matched), len(expected_positive))
    f1 = 0.0 if precision + recall == 0 else round(2 * precision * recall / (precision + recall), 4)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "manifest": {
            "schema_version": manifest.get("schema_version"),
            "document_count": len(_manifest_documents(manifest)),
            "expected_positive_count": len(expected_positive),
            "expected_negative_count": len(expected_negative),
        },
        "benchmark": {
            "schema_version": benchmark_report.get("schema_version"),
            "document_count": len(_benchmark_documents(benchmark_report)),
        },
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "expected_count": len(expected_positive),
        "prediction_count": len(predicted_keys),
        "matched_count": len(matched),
        "missing_count": len(missing),
        "false_positive_count": len(false_positives),
        "critical_false_positives": len(negative_false_positives),
        "missing": sorted(missing),
        "false_positives": sorted(false_positives),
        "negative_false_positives": sorted(negative_false_positives),
        "by_document": _by_document_metrics(expected_items, predicted_items),
    }
    report["parser_ground_truth_gate"] = _ground_truth_gate(report)
    report["status"] = "pass" if report["parser_ground_truth_gate"]["passed"] is True else "fail"
    return report


def expected_truth_items(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for document in _manifest_documents(manifest):
        filename = str(document["filename"])
        for raw_item in document.get("expected", []):
            if not isinstance(raw_item, Mapping):
                continue
            item = _truth_item(
                filename=filename,
                kind=str(raw_item.get("kind", "")),
                item_type=str(raw_item.get("type", "")),
                canonical=str(raw_item.get("canonical", "")),
                negative=bool(raw_item.get("negative", False)),
            )
            items.append(item)
    return items


def scoped_prediction_items(
    *,
    manifest: Mapping[str, Any],
    benchmark_report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expected_items = expected_truth_items(manifest)
    scope_by_filename: dict[str, set[tuple[str, str]]] = defaultdict(set)
    manifest_filenames = {
        str(document["filename"])
        for document in _manifest_documents(manifest)
    }
    for item in expected_items:
        scope_by_filename[item["filename"]].add((item["kind"], item["type"]))

    scoped: list[dict[str, Any]] = []
    for item in prediction_items(benchmark_report):
        if item["filename"] not in manifest_filenames:
            continue
        if (item["kind"], item["type"]) not in scope_by_filename[item["filename"]]:
            continue
        scoped.append(item)
    return scoped


def prediction_items(benchmark_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for document in _benchmark_documents(benchmark_report):
        filename = str(document.get("file_name") or document.get("relative_path") or "")
        if not filename:
            continue
        metadata = document.get("metadata")
        if isinstance(metadata, Mapping):
            items.extend(_metadata_prediction_items(filename, metadata))
        section_diagnostics = document.get("section_diagnostics")
        if isinstance(section_diagnostics, Mapping):
            items.extend(_section_prediction_items(filename, section_diagnostics))
        items.extend(_semantic_prediction_items(filename, document.get("semantic_candidates")))
        items.extend(_table_figure_prediction_items(filename, document.get("table_figure_candidates")))
        review_summary = document.get("review_packet_summary")
        if isinstance(review_summary, Mapping):
            items.extend(_review_packet_prediction_items(filename, review_summary))
    return sorted(items, key=lambda item: item["key"])


def render_report_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _metadata_prediction_items(filename: str, metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for field in ("document_code", "revision"):
        value = metadata.get(field)
        if isinstance(value, str) and value:
            items.append(_truth_item(
                filename=filename,
                kind="metadata",
                item_type=field,
                canonical=value,
            ))
    return items


def _section_prediction_items(filename: str, diagnostics: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    section_spans = diagnostics.get("section_spans", [])
    if not isinstance(section_spans, list):
        return items
    for span in section_spans:
        if not isinstance(span, Mapping):
            continue
        section_path = span.get("section_path")
        if isinstance(section_path, str) and section_path:
            items.append(_truth_item(
                filename=filename,
                kind="section",
                item_type="section_path",
                canonical=section_path,
            ))
    return items


def _semantic_prediction_items(filename: str, candidates: Any) -> list[dict[str, Any]]:
    if not isinstance(candidates, list):
        return []
    items: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        kind = str(candidate.get("kind") or "")
        canonical = _semantic_candidate_canonical(candidate)
        if kind and canonical:
            items.append(_truth_item(
                filename=filename,
                kind="semantic",
                item_type=kind,
                canonical=canonical,
            ))
    return items


def _table_figure_prediction_items(filename: str, candidates: Any) -> list[dict[str, Any]]:
    if not isinstance(candidates, list):
        return []
    items: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        kind = str(candidate.get("kind") or "")
        canonical = _table_figure_candidate_canonical(candidate)
        if kind and canonical:
            items.append(_truth_item(
                filename=filename,
                kind="table_figure",
                item_type=kind,
                canonical=canonical,
            ))
    return items


def _review_packet_prediction_items(filename: str, summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    reason_counts = summary.get("reason_code_counts", {})
    if not isinstance(reason_counts, Mapping):
        return []
    return [
        _truth_item(
            filename=filename,
            kind="review_packet",
            item_type="reason_code",
            canonical=str(reason_code),
        )
        for reason_code, count in reason_counts.items()
        if _positive_int(count)
    ]


def _semantic_candidate_canonical(candidate: Mapping[str, Any]) -> str:
    normalized_content = candidate.get("normalized_content")
    if isinstance(normalized_content, Mapping):
        for key in ("identifier", "requirement", "responsibility", "instruction", "equipment"):
            value = normalized_content.get(key)
            if isinstance(value, str) and value:
                return value
    normalized_text = candidate.get("normalized_text")
    if isinstance(normalized_text, str) and normalized_text:
        return normalized_text
    evidence = candidate.get("evidence")
    if isinstance(evidence, Mapping):
        quote = evidence.get("quote")
        if isinstance(quote, str) and quote:
            return quote
    return ""


def _table_figure_candidate_canonical(candidate: Mapping[str, Any]) -> str:
    kind = str(candidate.get("kind") or "")
    normalized_content = candidate.get("normalized_content")
    if kind == "text_table":
        return "table_present"
    if isinstance(normalized_content, Mapping):
        for key in ("label", "identifier", "name"):
            value = normalized_content.get(key)
            if isinstance(value, str) and value:
                return value
    quote = candidate.get("quote")
    return quote if isinstance(quote, str) else ""


def _truth_item(
    *,
    filename: str,
    kind: str,
    item_type: str,
    canonical: str,
    negative: bool = False,
) -> dict[str, Any]:
    canonical_value = _canonicalize(canonical)
    return {
        "filename": filename,
        "kind": kind,
        "type": item_type,
        "canonical": canonical_value,
        "negative": negative,
        "key": f"{filename}|{kind}|{item_type}|{canonical_value}",
    }


def _canonicalize(value: str) -> str:
    normalized = value.strip().casefold()
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFKD", normalized)
        if not unicodedata.combining(char)
    )
    normalized = normalized.replace("r$", "")
    normalized = re.sub(r"\bbrl\b", "", normalized)
    normalized = re.sub(r"[\"'`]", "", normalized)
    normalized = re.sub(r"[;,]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" .:-")


def _ground_truth_gate(report: Mapping[str, Any]) -> dict[str, Any]:
    gates = {
        "precision": {
            "threshold": f">= {PRECISION_MIN}",
            "value": report["precision"],
            "passed": report["precision"] >= PRECISION_MIN,
        },
        "recall": {
            "threshold": f">= {RECALL_MIN}",
            "value": report["recall"],
            "passed": report["recall"] >= RECALL_MIN,
        },
        "critical_false_positives": {
            "threshold": "= 0",
            "value": report["critical_false_positives"],
            "passed": report["critical_false_positives"] == 0,
        },
        "missing_count": {
            "threshold": "= 0",
            "value": report["missing_count"],
            "passed": report["missing_count"] == 0,
        },
    }
    return {"passed": all(gate["passed"] for gate in gates.values()), "gates": gates}


def _by_document_metrics(
    expected_items: list[dict[str, Any]],
    predicted_items: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    expected_by_document: dict[str, set[str]] = defaultdict(set)
    predicted_by_document: dict[str, set[str]] = defaultdict(set)
    for item in expected_items:
        if item["negative"] is False:
            expected_by_document[item["filename"]].add(item["key"])
    for item in predicted_items:
        predicted_by_document[item["filename"]].add(item["key"])
    documents = set(expected_by_document) | set(predicted_by_document)
    return {
        document: {
            "precision": _rate(
                len(expected_by_document[document] & predicted_by_document[document]),
                len(predicted_by_document[document]),
            ),
            "recall": _rate(
                len(expected_by_document[document] & predicted_by_document[document]),
                len(expected_by_document[document]),
            ),
            "expected_count": len(expected_by_document[document]),
            "prediction_count": len(predicted_by_document[document]),
        }
        for document in sorted(documents)
    }


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _manifest_documents(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    documents = manifest.get("documents", [])
    return [document for document in documents if isinstance(document, dict)]


def _benchmark_documents(benchmark_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    documents = benchmark_report.get("documents", [])
    return [document for document in documents if isinstance(document, dict)]


def _positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _load_benchmark_module(repo_root: Path) -> Any:
    script_path = repo_root / "scripts" / "industrial" / "benchmark_dirty_documents.py"
    module_name = "industrial_dirty_benchmark_for_ground_truth"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load benchmark script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path.name}")
    return cast("dict[str, Any]", payload)


def _resolve_repo_path(repo_root: Path, value: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root / path


def _safe_error_message(exc: Exception, *, repo_root: Path) -> str:
    message = str(exc)
    root_text = str(repo_root)
    for prefix in (root_text + "\\", root_text + "/"):
        message = message.replace(prefix, "")
    message = message.replace(root_text, ".")
    return re.sub(
        r"'([A-Za-z]:\\[^']+)'",
        lambda match: f"'{Path(match.group(1)).name}'",
        message,
    )


if __name__ == "__main__":
    raise SystemExit(main())
