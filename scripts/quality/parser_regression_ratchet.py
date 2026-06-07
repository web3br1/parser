from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

SCHEMA_VERSION = "parser_fragility_ratchet.v1"
FIXTURE_PACK_ID = "parser_fragility.v1"
DEFAULT_BASELINE = Path(
    "examples/parser_fragility/baselines/parser-fragility-baseline.v1.json",
)
DEFAULT_DIRTY_CORPUS = Path(".run/industrial-real")
DIRTY_BENCHMARK_REPORT = "benchmark-latest.json"
PRIVATE_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:\\"),
    re.compile(r"(^|[/\\])\.run([/\\]|$)"),
    re.compile(r"(^|[/\\])Users[/\\][^/\\]+"),
)
SUPPORTED_NEGATIVE_EXPECTATION_KEYS = {
    "multi_document_appendix_code_ambiguity": {
        "must_not_promote_document_code",
    },
    "toc_requirement_contamination": {
        "must_not_promote_toc_requirement",
    },
    "repeated_header_footer_contamination": {
        "must_not_promote_boilerplate_candidate",
    },
    "figure_reference_without_visual_evidence": {
        "must_not_claim_visual_understanding",
    },
    "sparse_image_placeholder_review_risk": {
        "must_not_claim_clean_text_extraction",
    },
    "section_hierarchy_gap": {
        "must_not_claim_grouping_clean",
    },
    "evidence_quote_boundary_drift": {
        "must_not_claim_quote_on_wrong_page",
    },
    "split_document_stress_surrogate": {
        "must_not_claim_split_diagnostics_complete_without_ranges",
    },
}


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    baseline_path = _resolve_repo_path(repo_root, args.baseline)
    dirty_corpus_dir = _resolve_repo_path(repo_root, args.dirty_corpus_dir)

    if args.update_baseline:
        reason = str(args.reason or "").strip()
        if not reason:
            print("--update-baseline requires a non-empty --reason", file=sys.stderr)
            return 2
        current = build_current_signals(
            repo_root=repo_root,
            dirty_corpus_dir=dirty_corpus_dir,
        )
        baseline = baseline_payload(current=current, reason=reason)
        private_tokens = find_private_path_tokens(baseline)
        if private_tokens:
            print(
                "Refusing to write baseline with private path tokens: "
                + ", ".join(private_tokens),
                file=sys.stderr,
            )
            return 2
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote parser ratchet baseline: {baseline_path}")
        return 0

    if not baseline_path.exists():
        print(f"Baseline not found: {baseline_path}", file=sys.stderr)
        return 2

    baseline = cast(
        "dict[str, Any]",
        json.loads(baseline_path.read_text(encoding="utf-8")),
    )
    current = build_current_signals(
        repo_root=repo_root,
        dirty_corpus_dir=dirty_corpus_dir,
    )
    report = compare_to_baseline(current=current, baseline=baseline)
    if args.report:
        report_path = _resolve_repo_path(repo_root, args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare parser fragility quality signals against an accepted baseline.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--dirty-corpus-dir", type=Path, default=DEFAULT_DIRTY_CORPUS)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--reason", default="")
    return parser.parse_args(argv)


def build_current_signals(
    *,
    repo_root: Path,
    dirty_corpus_dir: Path | None = None,
) -> dict[str, Any]:
    _ensure_parser_src_on_path(repo_root)
    fixture_dir = repo_root / "examples" / "parser_fragility"
    manifest = _read_json(fixture_dir / "manifest.json")
    documents = [
        document
        for document in manifest.get("documents", [])
        if isinstance(document, dict)
    ]
    fixture_snapshots = [
        _build_fixture_snapshot(fixture_dir=fixture_dir, document=document)
        for document in documents
    ]
    dirty_dir = dirty_corpus_dir or repo_root / DEFAULT_DIRTY_CORPUS

    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_pack_id": str(manifest.get("fixture_pack_id", FIXTURE_PACK_ID)),
        "signals": {
            "metadata_expected_hits": _metadata_expected_hits(fixture_snapshots),
            "negative_expectation_passes": _negative_expectation_passes(
                fixture_snapshots,
            ),
            "adversarial_risk_emissions": _adversarial_risk_emissions(
                fixture_snapshots,
            ),
            "invariant_pass_counts": fixture_invariant_pass_counts(fixture_snapshots),
            "review_packet_reason_counts": _review_packet_reason_counts(
                fixture_snapshots,
            ),
            "benchmark_schema_version": _benchmark_schema_version(repo_root),
        },
        "dirty_corpus_optional": _dirty_corpus_summary(
            repo_root=repo_root,
            dirty_corpus_dir=dirty_dir,
        ),
    }


def compare_to_baseline(
    *,
    current: Mapping[str, Any],
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    baseline_values = {
        "schema_version": baseline.get("schema_version"),
        "fixture_pack_id": baseline.get("fixture_pack_id"),
    }
    baseline_values.update(_flatten_signals(
        _mapping_field(baseline, "signals"),
        prefix="signals",
    ))
    current_values = {
        "schema_version": current.get("schema_version"),
        "fixture_pack_id": current.get("fixture_pack_id"),
    }
    current_values.update(_flatten_signals(
        _mapping_field(current, "signals"),
        prefix="signals",
    ))
    regressions: list[dict[str, Any]] = []
    neutral_deltas: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []

    for path in sorted(baseline_values):
        baseline_value = baseline_values[path]
        current_value = current_values.get(
            path,
            0 if _is_number(baseline_value) else None,
        )
        delta = _delta(current_value, baseline_value)
        entry = {
            "path": path,
            "baseline": baseline_value,
            "current": current_value,
            "delta": delta,
        }
        if _is_regression_for_path(path, current_value, baseline_value):
            regressions.append(entry)
        elif _is_improvement_for_path(path, current_value, baseline_value):
            improvements.append(entry)
        else:
            neutral_deltas.append(entry)

    current_only: list[dict[str, Any]] = []
    for path in sorted(set(current_values) - set(baseline_values)):
        current_value = current_values[path]
        baseline_value = _current_only_baseline(path, current_value)
        if baseline_value is None:
            current_only.append({"path": path, "current": current_value})
            continue
        entry = {
            "path": path,
            "baseline": baseline_value,
            "current": current_value,
            "delta": _delta(current_value, baseline_value),
        }
        if _is_regression_for_path(path, current_value, baseline_value):
            regressions.append(entry)
        elif _is_improvement_for_path(path, current_value, baseline_value):
            improvements.append(entry)
        else:
            neutral_deltas.append(entry)

    return {
        "status": "fail" if regressions else "pass",
        "regressions": regressions,
        "neutral_deltas": neutral_deltas,
        "improvements": improvements,
        "current_only": current_only,
        "dirty_corpus_optional": current.get("dirty_corpus_optional", {}),
    }


def baseline_payload(*, current: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_pack_id": current.get("fixture_pack_id", FIXTURE_PACK_ID),
        "accepted_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace(
            "+00:00",
            "Z",
        ),
        "accepted_reason": reason,
        "signals": current.get("signals", {}),
        "dirty_corpus_optional": _baseline_dirty_corpus_summary(
            current.get("dirty_corpus_optional", {}),
        ),
    }


def find_private_path_tokens(payload: Any) -> list[str]:
    tokens: list[str] = []
    for value in _iter_string_values(payload):
        for pattern in PRIVATE_PATH_PATTERNS:
            if pattern.search(value):
                tokens.append(value)
                break
    return sorted(set(tokens))


def _build_fixture_snapshot(
    *,
    fixture_dir: Path,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    from parsers.base import ExtractedPage, ExtractionResult
    from parsers.chunker import RawChunk, chunk_extraction
    from parsers.industrial_metadata import extract_metadata_candidates
    from parsers.industrial_review import build_review_packets, summarize_review_packets
    from parsers.industrial_sections import (
        resolve_document_sections,
        section_diagnostics_to_metadata,
    )
    from parsers.industrial_semantics import (
        extract_semantic_candidates,
        semantic_candidates_to_metadata,
    )
    from parsers.industrial_tables import (
        extract_table_figure_candidates,
        table_figure_candidates_to_metadata,
    )

    filename = str(document["filename"])
    text = (fixture_dir / filename).read_text(encoding="utf-8")
    pages = _pages_from_fixture_text(text, extracted_page_type=ExtractedPage)
    page_profiles = _fixture_page_profiles(pages)
    base_result = ExtractionResult(
        mime_type="text/plain",
        pages=pages,
        total_chars=sum(page.char_count for page in pages),
        metadata={"parser": "txt"},
    )
    diagnostics = resolve_document_sections(pages)
    section_metadata = section_diagnostics_to_metadata(diagnostics)
    enriched_result = ExtractionResult(
        mime_type="text/plain",
        pages=pages,
        total_chars=sum(page.char_count for page in pages),
        metadata={
            "parser": "txt",
            "page_profiles": page_profiles,
            "section_diagnostics": section_metadata,
        },
    )
    chunks: list[RawChunk] = chunk_extraction(
        enriched_result,
        industrial_context=section_metadata,
    )
    semantic_candidates = extract_semantic_candidates(chunks)
    table_candidates = extract_table_figure_candidates(
        chunks,
        page_profiles=page_profiles,
    )
    page_profile_table_candidates = extract_table_figure_candidates(
        [],
        page_profiles=page_profiles,
    )
    metadata = extract_metadata_candidates(filename=filename, text=text)
    packets = build_review_packets(
        document_id=str(document["scenario"]),
        metadata=asdict(metadata),
        section_diagnostics=section_metadata,
        semantic_candidates=semantic_candidates_to_metadata(semantic_candidates),
        table_figure_candidates=table_figure_candidates_to_metadata(table_candidates),
    )
    page_profile_packets = build_review_packets(
        document_id=str(document["scenario"]),
        table_figure_candidates=table_figure_candidates_to_metadata(
            page_profile_table_candidates,
        ),
    )

    return {
        "document": document,
        "repo_root": fixture_dir.parents[1],
        "text": text,
        "pages": pages,
        "page_profiles": page_profiles,
        "base_result": base_result,
        "enriched_result": enriched_result,
        "metadata": metadata,
        "section_metadata": section_metadata,
        "chunks": chunks,
        "semantic_candidates": semantic_candidates,
        "table_candidates": table_candidates,
        "page_profile_table_candidates": page_profile_table_candidates,
        "packets": packets,
        "page_profile_packets": page_profile_packets,
        "review_summary": summarize_review_packets(packets),
        "page_profile_review_summary": summarize_review_packets(page_profile_packets),
    }


def _metadata_expected_hits(snapshots: Iterable[Mapping[str, Any]]) -> int:
    hits = 0
    for snapshot in snapshots:
        document = _mapping_field(snapshot, "document")
        expected = _dict_field(document, "positive_expectations").get(
            "should_expose",
            [],
        )
        metadata = snapshot["metadata"]
        gap_codes = set(getattr(metadata, "gap_codes", ()))
        if "multiple_nested_pop_codes" in expected:
            hits += int("ambiguous_nested_document_codes" in gap_codes)
        if "missing_file_level_document_code" in expected:
            hits += int("missing_document_code" in gap_codes)
    return hits


def _negative_expectation_passes(snapshots: Iterable[Mapping[str, Any]]) -> int:
    passes = 0
    for snapshot in snapshots:
        document = _mapping_field(snapshot, "document")
        negative_expectations = _dict_field(document, "negative_expectations")
        if not negative_expectations:
            continue
        passes += sum(
            int(_scenario_negative_expectation_passed(snapshot, str(key)))
            for key in negative_expectations
        )
    return passes


def _scenario_negative_expectation_passed(
    snapshot: Mapping[str, Any],
    expectation_key: str,
) -> bool:
    document = _mapping_field(snapshot, "document")
    scenario = str(document.get("scenario", ""))
    supported_keys = SUPPORTED_NEGATIVE_EXPECTATION_KEYS.get(scenario)
    if supported_keys is None:
        raise ValueError(f"Unsupported negative expectation scenario: {scenario}")
    if expectation_key not in supported_keys:
        raise ValueError(
            f"Unsupported negative expectation key for {scenario}: {expectation_key}",
        )

    metadata = snapshot["metadata"]
    section_metadata = _mapping_field(snapshot, "section_metadata")
    review_summary = _mapping_field(snapshot, "review_summary")

    if scenario == "multi_document_appendix_code_ambiguity":
        return getattr(metadata, "document_code", None) is None
    if scenario == "toc_requirement_contamination":
        return not _semantic_candidates_include_kind(
            snapshot,
            {"requirement", "procedure_step"},
        )
    if scenario == "repeated_header_footer_contamination":
        chunk_text = "\n".join(chunk.text for chunk in snapshot["chunks"])
        return "Cabecalho:" not in chunk_text and "Rodape:" not in chunk_text
    if scenario == "figure_reference_without_visual_evidence":
        return not any(
            getattr(candidate, "kind", "") == "visual_understanding"
            for candidate in snapshot["table_candidates"]
        )
    if scenario == "sparse_image_placeholder_review_risk":
        return _reason_count(
            _mapping_field(snapshot, "page_profile_review_summary"),
            "visual_table_figure_risk",
        ) >= 1
    if scenario == "section_hierarchy_gap":
        return "section_hierarchy_gap" in set(section_metadata.get("risk_codes", []))
    if scenario == "evidence_quote_boundary_drift":
        return _semantic_quotes_stay_on_source_pages(snapshot)
    if scenario == "split_document_stress_surrogate":
        return (
            _reason_count(review_summary, "ambiguous_section_hierarchy") >= 1
            and _reason_count(review_summary, "visual_table_figure_risk") >= 1
        )
    raise ValueError(f"Unsupported negative expectation scenario: {scenario}")


def fixture_invariant_pass_counts(
    snapshots: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    snapshot_list = list(snapshots)
    repo_root = _snapshot_repo_root(snapshot_list)
    helpers = _load_invariant_helpers(repo_root)
    counts: Counter[str] = Counter()
    for snapshot in snapshot_list:
        scenario = _scenario(snapshot)
        checks = {
            "diagnostics_preserve_text": lambda item=snapshot: helpers.assert_diagnostics_preserve_extraction_text(
                item["base_result"],
                item["enriched_result"],
            ),
            "chunk_source_spans": lambda item=snapshot: _assert_chunks_have_valid_source_spans(
                helpers.assert_chunks_have_valid_source_spans,
                item["chunks"],
            ),
            "candidate_evidence_pages": lambda item=snapshot: _assert_candidate_evidence_pages(
                helpers.assert_candidate_evidence_pages_within_result,
                item,
            ),
            "candidate_evidence_quotes": lambda item=snapshot: _assert_candidate_evidence_quotes(
                helpers.assert_candidate_evidence_quotes_in_source,
                item,
            ),
            "review_packets_well_formed": lambda item=snapshot: helpers.assert_review_packets_well_formed(
                item["packets"],
            ),
            "review_packet_counts_bounded": lambda item=snapshot: helpers.assert_review_packet_counts_bounded(
                item["packets"],
            ),
            "known_parser_risk_codes": lambda item=snapshot: helpers.assert_known_parser_risk_codes(
                asdict(item["metadata"]),
                item["section_metadata"],
                item["semantic_candidates"],
                item["table_candidates"],
                item["packets"],
                item["chunks"],
            ),
        }
        for name, check in checks.items():
            try:
                check()
            except AssertionError as exc:
                raise AssertionError(f"{scenario}:{name}: {exc}") from exc
            counts[name] += 1
    return dict(sorted(counts.items()))


def _snapshot_repo_root(snapshots: Sequence[Mapping[str, Any]]) -> Path:
    for snapshot in snapshots:
        repo_root = snapshot.get("repo_root")
        if isinstance(repo_root, Path):
            return repo_root
    return Path.cwd()


def _load_invariant_helpers(repo_root: Path) -> Any:
    helper_path = repo_root / "packages" / "parsers" / "tests" / "industrial_invariant_helpers.py"
    spec = importlib.util.spec_from_file_location(
        "industrial_invariant_helpers_under_ratchet",
        helper_path,
    )
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load invariant helpers: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["industrial_invariant_helpers_under_ratchet"] = module
    spec.loader.exec_module(module)
    return module


def _assert_chunks_have_valid_source_spans(
    assertion: Any,
    chunks: Sequence[Any],
) -> None:
    if not chunks:
        raise AssertionError("chunk_source_spans expected at least one chunk")
    assertion(chunks)


def _assert_candidate_evidence_pages(
    assertion: Any,
    snapshot: Mapping[str, Any],
) -> None:
    candidates = [
        *snapshot["semantic_candidates"],
        *snapshot["table_candidates"],
    ]
    assertion(candidates, snapshot["enriched_result"])


def _assert_candidate_evidence_quotes(
    assertion: Any,
    snapshot: Mapping[str, Any],
) -> None:
    candidates = [
        *snapshot["semantic_candidates"],
        *snapshot["table_candidates"],
    ]
    assertion(candidates, snapshot["enriched_result"])


def _adversarial_risk_emissions(snapshots: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    for snapshot in snapshots:
        metadata = snapshot["metadata"]
        section_metadata = _mapping_field(snapshot, "section_metadata")
        count += len(getattr(metadata, "gap_codes", ()))
        count += len(section_metadata.get("risk_codes", []))
        for span in section_metadata.get("section_spans", []):
            if isinstance(span, dict):
                count += len(span.get("risk_codes", []))
        for chunk in snapshot["chunks"]:
            count += len(getattr(chunk, "structure_risk_codes", ()))
        for candidate in snapshot["table_candidates"]:
            count += len(getattr(candidate, "risk_codes", ()))
        for packet in snapshot["packets"]:
            count += len(getattr(packet, "risk_codes", ()))
        if _scenario(snapshot) == "sparse_image_placeholder_review_risk":
            for candidate in snapshot["page_profile_table_candidates"]:
                count += len(getattr(candidate, "risk_codes", ()))
            for packet in snapshot["page_profile_packets"]:
                count += len(getattr(packet, "risk_codes", ()))
    return count


def _review_packet_reason_counts(
    snapshots: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for snapshot in snapshots:
        review_summary = _mapping_field(snapshot, "review_summary")
        reason_counts = review_summary.get("reason_code_counts", {})
        if isinstance(reason_counts, dict):
            counts.update({str(key): int(value) for key, value in reason_counts.items()})
        if _scenario(snapshot) == "sparse_image_placeholder_review_risk":
            profile_summary = _mapping_field(snapshot, "page_profile_review_summary")
            profile_reason_counts = profile_summary.get("reason_code_counts", {})
            if isinstance(profile_reason_counts, dict):
                counts.update({
                    str(key): int(value)
                    for key, value in profile_reason_counts.items()
                })
    return dict(sorted(counts.items()))


def _dirty_corpus_summary(
    *,
    repo_root: Path,
    dirty_corpus_dir: Path,
) -> dict[str, Any]:
    if not dirty_corpus_dir.exists():
        return {
            "status": "skipped",
            "reason": f"{_relative_to_repo(repo_root, dirty_corpus_dir)} not found",
        }
    report_path = dirty_corpus_dir / DIRTY_BENCHMARK_REPORT
    if not report_path.exists():
        return {
            "status": "skipped",
            "reason": (
                f"{_relative_to_repo(repo_root, report_path)} not found"
            ),
        }
    report = _read_json(report_path)
    summary = _mapping_field(report, "summary")
    return {
        "status": "compared",
        "schema_version": report.get("schema_version"),
        "document_count": summary.get("document_count", 0),
        "parsed_count": summary.get("parsed_count", 0),
        "failed_count": summary.get("failed_count", 0),
        "review_packet_reason_counts": summary.get("review_packet_reason_counts", {}),
    }


def _baseline_dirty_corpus_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("status") != "compared":
        return {
            "status": "skipped",
            "reason": "optional dirty corpus not committed",
        }
    return {
        key: value[key]
        for key in (
            "status",
            "schema_version",
            "document_count",
            "parsed_count",
            "failed_count",
            "review_packet_reason_counts",
        )
        if key in value
    }


def _benchmark_schema_version(repo_root: Path) -> str:
    script = repo_root / "scripts" / "industrial" / "benchmark_dirty_documents.py"
    spec = importlib.util.spec_from_file_location(
        "industrial_dirty_benchmark_schema_under_ratchet",
        script,
    )
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load benchmark script: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["industrial_dirty_benchmark_schema_under_ratchet"] = module
    spec.loader.exec_module(module)
    return str(module.SCHEMA_VERSION)


def _ensure_parser_src_on_path(repo_root: Path) -> None:
    parser_src = repo_root / "packages" / "parsers" / "src"
    parser_src_text = str(parser_src)
    if parser_src_text not in sys.path:
        sys.path.insert(0, parser_src_text)


def _pages_from_fixture_text(text: str, *, extracted_page_type: Any) -> list[Any]:
    pages: list[Any] = []
    current_page: int | None = None
    current_lines: list[str] = []

    def page(page_number: int, page_text: str) -> Any:
        clean = page_text.strip()
        return extracted_page_type(
            page_number=page_number,
            text=clean,
            char_count=len(clean),
            is_empty=not bool(clean),
        )

    def flush_current() -> None:
        nonlocal current_page, current_lines
        if current_page is not None:
            pages.append(page(current_page, "\n".join(current_lines)))
        current_page = None
        current_lines = []

    for line in text.splitlines():
        bare_marker = re.fullmatch(r"Pagina\s+(\d+)", line.strip(), flags=re.IGNORECASE)
        inline_marker = re.fullmatch(
            r"Pagina\s+(\d+):\s*(.*)",
            line.strip(),
            flags=re.IGNORECASE,
        )
        if bare_marker:
            flush_current()
            current_page = int(bare_marker.group(1))
            continue
        if inline_marker:
            flush_current()
            pages.append(page(int(inline_marker.group(1)), inline_marker.group(2)))
            continue
        if current_page is not None:
            current_lines.append(line)

    flush_current()
    return pages or [page(1, text)]


def _fixture_page_profiles(pages: Sequence[Any]) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for page in pages:
        text = str(page.text)
        if "[IMAGEM-APENAS" not in text:
            continue
        profiles.append(
            {
                "page_number": page.page_number,
                "image_count": 1,
                "text_chars": 0,
                "risk_codes": [
                    "ocr_required",
                    "sparse_text_with_images",
                    "visual_content_without_caption",
                ],
            },
        )
    return profiles


def _semantic_candidates_include_kind(
    snapshot: Mapping[str, Any],
    kinds: set[str],
) -> bool:
    return any(
        getattr(candidate, "kind", "") in kinds
        for candidate in snapshot["semantic_candidates"]
    )


def _semantic_quotes_stay_on_source_pages(snapshot: Mapping[str, Any]) -> bool:
    source_by_page = {
        page.page_number: page.text
        for page in snapshot["pages"]
    }
    for candidate in snapshot["semantic_candidates"]:
        evidence = getattr(candidate, "evidence", None)
        quote = getattr(evidence, "quote", None)
        page_start = getattr(evidence, "page_start", None)
        if not quote or page_start is None:
            continue
        if quote not in source_by_page.get(page_start, ""):
            return False
    return True


def _reason_count(review_summary: Mapping[str, Any], reason: str) -> int:
    reason_counts = review_summary.get("reason_code_counts", {})
    if not isinstance(reason_counts, dict):
        return 0
    return int(reason_counts.get(reason, 0))


def _scenario(snapshot: Mapping[str, Any]) -> str:
    return str(_mapping_field(snapshot, "document").get("scenario", ""))


def _flatten_signals(node: Mapping[str, Any], *, prefix: str) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}"
        if isinstance(value, dict):
            flattened.update(_flatten_signals(value, prefix=path))
        else:
            flattened[path] = value
    return flattened


def _current_only_baseline(path: str, current_value: Any) -> Any | None:
    if _comparison_policy(path) == "lower_or_equal_is_better" and _is_number(current_value):
        return 0
    return None


def _is_regression_for_path(path: str, current_value: Any, baseline_value: Any) -> bool:
    policy = _comparison_policy(path)
    if policy == "higher_or_equal_is_better":
        if _is_number(current_value) and _is_number(baseline_value):
            return int(current_value) < int(baseline_value)
        return current_value != baseline_value
    if policy == "lower_or_equal_is_better":
        if _is_number(current_value) and _is_number(baseline_value):
            return int(current_value) > int(baseline_value)
        return current_value != baseline_value
    return current_value != baseline_value


def _is_improvement_for_path(path: str, current_value: Any, baseline_value: Any) -> bool:
    policy = _comparison_policy(path)
    if policy == "higher_or_equal_is_better":
        if _is_number(current_value) and _is_number(baseline_value):
            return int(current_value) > int(baseline_value)
        return False
    if policy == "lower_or_equal_is_better":
        if _is_number(current_value) and _is_number(baseline_value):
            return int(current_value) < int(baseline_value)
        return False
    return False


def _comparison_policy(path: str) -> str:
    if (
        path.startswith("signals.review_packet_reason_counts.")
        or path == "signals.adversarial_risk_emissions"
    ):
        return "lower_or_equal_is_better"
    if (
        path == "signals.metadata_expected_hits"
        or path == "signals.negative_expectation_passes"
        or path.startswith("signals.invariant_pass_counts.")
    ):
        return "higher_or_equal_is_better"
    return "exact"


def _delta(current_value: Any, baseline_value: Any) -> int | str:
    if _is_number(current_value) and _is_number(baseline_value):
        return int(current_value) - int(baseline_value)
    return 0 if current_value == baseline_value else "changed"


def _is_number(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _mapping_field(node: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = node.get(key, {})
    if isinstance(value, dict):
        return value
    return {}


def _dict_field(node: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = node.get(key, {})
    if isinstance(value, dict):
        return cast("dict[str, Any]", value)
    return {}


def _read_json(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def _iter_string_values(payload: Any) -> Iterable[str]:
    if isinstance(payload, str):
        yield payload
    elif isinstance(payload, dict):
        for value in payload.values():
            yield from _iter_string_values(value)
    elif isinstance(payload, list):
        for value in payload:
            yield from _iter_string_values(value)


def _resolve_repo_path(repo_root: Path, value: Path | None) -> Path:
    if value is None:
        return value
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root / path


def _relative_to_repo(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


if __name__ == "__main__":
    raise SystemExit(main())
