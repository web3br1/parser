from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "quality" / "parser_ground_truth_eval.py"
BENCHMARK_SCRIPT = ROOT / "scripts" / "industrial" / "benchmark_dirty_documents.py"


def load_eval() -> Any:
    module_name = "parser_ground_truth_eval_under_test"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_benchmark() -> Any:
    module_name = "industrial_dirty_benchmark_for_ground_truth_test"
    spec = importlib.util.spec_from_file_location(module_name, BENCHMARK_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict[str, Any]:
    return {
        "schema_version": "parser_ground_truth_manifest.v1",
        "documents": [
            {
                "filename": "sample.txt",
                "expected": [
                    {
                        "kind": "metadata",
                        "type": "document_code",
                        "canonical": "POP-QA-014",
                    },
                    {
                        "kind": "section",
                        "type": "section_path",
                        "canonical": "1/1.1",
                    },
                    {
                        "kind": "semantic",
                        "type": "requirement",
                        "canonical": "Toda nao conformidade deve ser registrada.",
                    },
                    {
                        "kind": "table_figure",
                        "type": "figure_reference",
                        "canonical": "Figura 1",
                    },
                    {
                        "kind": "review_packet",
                        "type": "reason_code",
                        "canonical": "missing_metadata",
                        "negative": True,
                    },
                ],
            }
        ],
    }


def _benchmark_report() -> dict[str, Any]:
    return {
        "schema_version": "industrial_dirty_benchmark.v1",
        "documents": [
            {
                "file_name": "sample.txt",
                "metadata": {
                    "document_code": "POP-QA-014",
                    "revision": "04",
                },
                "section_diagnostics": {
                    "section_spans": [
                        {"section_path": "1/1.1"},
                    ],
                },
                "semantic_candidates": [
                    {
                        "kind": "requirement",
                        "normalized_text": "Toda nao conformidade deve ser registrada.",
                        "normalized_content": {
                            "requirement": "Toda nao conformidade deve ser registrada.",
                        },
                    }
                ],
                "table_figure_candidates": [
                    {
                        "kind": "figure_reference",
                        "normalized_content": {
                            "label": "Figura 1",
                            "caption": "Fluxo de registro de NC.",
                        },
                    }
                ],
                "review_packet_summary": {
                    "reason_code_counts": {},
                },
            }
        ],
    }


def test_ground_truth_metrics_pass_when_expected_items_match() -> None:
    evaluator = load_eval()

    report = evaluator.compute_ground_truth_report(
        manifest=_manifest(),
        benchmark_report=_benchmark_report(),
    )

    assert report["schema_version"] == "parser_ground_truth_eval.v1"
    assert report["status"] == "pass"
    assert report["precision"] == 1.0
    assert report["recall"] == 1.0
    assert report["missing_count"] == 0
    assert report["false_positive_count"] == 0
    assert report["critical_false_positives"] == 0
    assert report["parser_ground_truth_gate"]["passed"] is True


def test_ground_truth_metrics_fail_when_expected_positive_item_is_missing() -> None:
    evaluator = load_eval()
    benchmark = _benchmark_report()
    benchmark["documents"][0]["semantic_candidates"] = []

    report = evaluator.compute_ground_truth_report(
        manifest=_manifest(),
        benchmark_report=benchmark,
    )

    assert report["status"] == "fail"
    assert report["recall"] < 1.0
    assert report["missing_count"] == 1
    assert report["missing"] == [
        "sample.txt|semantic|requirement|toda nao conformidade deve ser registrada"
    ]
    assert report["parser_ground_truth_gate"]["gates"]["missing_count"]["passed"] is False


def test_ground_truth_metrics_fail_on_negative_expected_false_positive() -> None:
    evaluator = load_eval()
    benchmark = _benchmark_report()
    benchmark["documents"][0]["review_packet_summary"] = {
        "reason_code_counts": {"missing_metadata": 1},
    }

    report = evaluator.compute_ground_truth_report(
        manifest=_manifest(),
        benchmark_report=benchmark,
    )

    assert report["status"] == "fail"
    assert report["critical_false_positives"] == 1
    assert report["negative_false_positives"] == [
        "sample.txt|review_packet|reason_code|missing_metadata"
    ]
    assert (
        report["parser_ground_truth_gate"]["gates"]["critical_false_positives"]["passed"]
        is False
    )


def test_manifest_fixture_evaluates_with_cli_and_writes_deterministic_report(
    tmp_path: Path,
) -> None:
    output = tmp_path / "ground-truth-report.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(ROOT),
            "--report",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    stdout_payload = json.loads(completed.stdout)
    file_payload = json.loads(output.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["schema_version"] == "parser_ground_truth_eval.v1"
    assert file_payload["status"] == "pass"
    assert file_payload["manifest"]["document_count"] == 2
    assert str(tmp_path) not in output.read_text(encoding="utf-8")
    assert "generated_at" not in output.read_text(encoding="utf-8")


def test_dirty_benchmark_omits_candidate_details_unless_requested(tmp_path: Path) -> None:
    benchmark = load_benchmark()
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    source = input_dir / "POP-QA-014_Rev04_vigent.txt"
    source.write_text(
        "\n".join([
            "Codigo: POP-QA-014",
            "Revisao: 04",
            "1 Procedimento",
            "Toda nao conformidade deve ser registrada.",
            "Figura 1 - Fluxo de registro de NC.",
        ]),
        encoding="utf-8",
    )

    default_report = benchmark.build_report(input_dir=input_dir)
    details_report = benchmark.build_report_with_options(
        input_dir=input_dir,
        include_candidate_details=True,
    )

    default_document = default_report["documents"][0]
    details_document = details_report["documents"][0]
    assert "semantic_candidates" not in default_document
    assert "table_figure_candidates" not in default_document
    assert details_document["semantic_candidates"]
    assert details_document["table_figure_candidates"]


def test_cli_invalid_manifest_does_not_print_absolute_path(tmp_path: Path) -> None:
    manifest = tmp_path / "bad-manifest.json"
    manifest.write_text("[]", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(ROOT),
            "--manifest",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "bad-manifest.json" in completed.stderr
    assert str(tmp_path) not in completed.stderr
