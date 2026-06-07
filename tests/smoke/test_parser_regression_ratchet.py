from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "quality" / "parser_regression_ratchet.py"
BASELINE = (
    ROOT
    / "examples"
    / "parser_fragility"
    / "baselines"
    / "parser-fragility-baseline.v1.json"
)


def load_ratchet() -> Any:
    module_name = "parser_regression_ratchet_under_test"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_cli(module: Any, argv: list[str]) -> int:
    try:
        result = module.main(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return int(result or 0)


def minimal_baseline() -> dict[str, Any]:
    return {
        "schema_version": "parser_fragility_ratchet.v1",
        "fixture_pack_id": "parser_fragility.v1",
        "accepted_at": "2026-06-06T00:00:00Z",
        "accepted_reason": "test baseline",
        "signals": {
            "metadata_expected_hits": 8,
            "negative_expectation_passes": 8,
            "adversarial_risk_emissions": 6,
            "invariant_pass_counts": {
                "fixture_documents": 8,
                "invariant_assertions": 8,
            },
            "review_packet_reason_counts": {
                "ambiguous_metadata": 1,
                "ambiguous_section_hierarchy": 2,
                "visual_table_figure_risk": 2,
            },
            "benchmark_schema_version": "industrial_dirty_benchmark.v1",
        },
        "dirty_corpus_optional": {
            "status": "skipped",
            "reason": "not available",
        },
    }


def test_ratchet_fails_when_required_signal_drops_below_baseline() -> None:
    ratchet = load_ratchet()
    baseline = minimal_baseline()
    current = json.loads(json.dumps(baseline))
    current["signals"]["metadata_expected_hits"] = 7

    report = ratchet.compare_to_baseline(current=current, baseline=baseline)

    assert report["status"] == "fail"
    assert report["regressions"] == [
        {
            "path": "signals.metadata_expected_hits",
            "baseline": 8,
            "current": 7,
            "delta": -1,
        }
    ]
    assert report["improvements"] == []


def test_ratchet_passes_and_labels_neutral_delta_and_improvement() -> None:
    ratchet = load_ratchet()
    baseline = minimal_baseline()
    current = json.loads(json.dumps(baseline))
    current["signals"]["metadata_expected_hits"] = 9
    current["signals"]["review_packet_reason_counts"]["visual_table_figure_risk"] = 1

    report = ratchet.compare_to_baseline(current=current, baseline=baseline)

    assert report["status"] == "pass"
    assert {
        "path": "signals.negative_expectation_passes",
        "baseline": 8,
        "current": 8,
        "delta": 0,
    } in report["neutral_deltas"]
    assert {
        "path": "signals.metadata_expected_hits",
        "baseline": 8,
        "current": 9,
        "delta": 1,
    } in report["improvements"]
    assert {
        "path": "signals.review_packet_reason_counts.visual_table_figure_risk",
        "baseline": 2,
        "current": 1,
        "delta": -1,
    } in report["improvements"]


def test_review_packet_and_risk_noise_increases_are_regressions() -> None:
    ratchet = load_ratchet()
    baseline = minimal_baseline()
    current = json.loads(json.dumps(baseline))
    current["signals"]["adversarial_risk_emissions"] = 7
    current["signals"]["review_packet_reason_counts"]["missing_metadata"] = 4
    current["signals"]["review_packet_reason_counts"]["visual_table_figure_risk"] = 3

    report = ratchet.compare_to_baseline(current=current, baseline=baseline)

    assert report["status"] == "fail"
    assert {
        "path": "signals.adversarial_risk_emissions",
        "baseline": 6,
        "current": 7,
        "delta": 1,
    } in report["regressions"]
    assert {
        "path": "signals.review_packet_reason_counts.missing_metadata",
        "baseline": 0,
        "current": 4,
        "delta": 4,
    } in report["regressions"]
    assert {
        "path": "signals.review_packet_reason_counts.visual_table_figure_risk",
        "baseline": 2,
        "current": 3,
        "delta": 1,
    } in report["regressions"]
    assert not any(
        item["path"].startswith("signals.review_packet_reason_counts")
        for item in report["improvements"]
    )


def test_top_level_schema_and_fixture_pack_identity_are_compared() -> None:
    ratchet = load_ratchet()
    baseline = minimal_baseline()
    current = json.loads(json.dumps(baseline))
    current["schema_version"] = "parser_fragility_ratchet.v2"
    current["fixture_pack_id"] = "parser_fragility.v2"

    report = ratchet.compare_to_baseline(current=current, baseline=baseline)

    assert report["status"] == "fail"
    assert {
        "path": "fixture_pack_id",
        "baseline": "parser_fragility.v1",
        "current": "parser_fragility.v2",
        "delta": "changed",
    } in report["regressions"]
    assert {
        "path": "schema_version",
        "baseline": "parser_fragility_ratchet.v1",
        "current": "parser_fragility_ratchet.v2",
        "delta": "changed",
    } in report["regressions"]


def test_update_baseline_requires_non_empty_reason(tmp_path: Path) -> None:
    ratchet = load_ratchet()
    output = tmp_path / "baseline.json"

    code = run_cli(
        ratchet,
        [
            "--repo-root",
            str(ROOT),
            "--baseline",
            str(output),
            "--update-baseline",
            "--reason",
            "   ",
        ],
    )

    assert code == 2
    assert not output.exists()


def test_invariant_pass_counts_are_actual_fixture_output_checks() -> None:
    ratchet = load_ratchet()
    current = ratchet.build_current_signals(
        repo_root=ROOT,
        dirty_corpus_dir=ROOT / ".run" / "industrial-real-missing-for-ratchet-test",
    )

    counts = current["signals"]["invariant_pass_counts"]

    assert counts == {
        "candidate_evidence_pages": 8,
        "candidate_evidence_quotes": 8,
        "chunk_source_spans": 8,
        "diagnostics_preserve_text": 8,
        "known_parser_risk_codes": 8,
        "review_packet_counts_bounded": 8,
        "review_packets_well_formed": 8,
    }
    assert "invariant_assertions" not in counts


def test_fixture_invariant_violation_is_a_strict_failure() -> None:
    ratchet = load_ratchet()
    manifest = json.loads((ROOT / "examples" / "parser_fragility" / "manifest.json").read_text(
        encoding="utf-8",
    ))
    snapshot = ratchet._build_fixture_snapshot(
        fixture_dir=ROOT / "examples" / "parser_fragility",
        document=manifest["documents"][0],
    )
    broken_snapshot = dict(snapshot)
    broken_snapshot["chunks"] = []

    with pytest.raises(AssertionError, match="chunk_source_spans"):
        ratchet.fixture_invariant_pass_counts([broken_snapshot])


def test_unknown_negative_expectation_scenario_is_not_counted_as_pass(tmp_path: Path) -> None:
    ratchet = load_ratchet()
    fixture_dir = tmp_path / "examples" / "parser_fragility"
    fixture_dir.mkdir(parents=True)
    benchmark_dir = tmp_path / "scripts" / "industrial"
    benchmark_dir.mkdir(parents=True)
    (benchmark_dir / "benchmark_dirty_documents.py").write_text(
        'SCHEMA_VERSION = "industrial_dirty_benchmark.v1"\n',
        encoding="utf-8",
    )
    (fixture_dir / "unknown_scenario.txt").write_text(
        "Pagina 1\n1 Objetivo\nDeve registrar lote antes da liberacao.",
        encoding="utf-8",
    )
    manifest = {
        "fixture_pack_id": "parser_fragility.v1",
        "language": "pt-BR",
        "documents": [
            {
                "filename": "unknown_scenario.txt",
                "scenario": "new_reviewed_fragility",
                "fragility_ids": ["PF-999"],
                "fixture_kind": "synthetic_text",
                "positive_expectations": {},
                "negative_expectations": {
                    "must_not_claim_new_behavior": "Must be explicitly supported."
                },
                "invariant_expectations": {
                    "deterministic_text_only": True,
                },
            }
        ],
    }
    (fixture_dir / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported negative expectation scenario: new_reviewed_fragility",
    ):
        ratchet.build_current_signals(
            repo_root=tmp_path,
            dirty_corpus_dir=tmp_path / ".run" / "industrial-real",
        )


def test_unknown_negative_expectation_key_is_not_counted_as_pass(tmp_path: Path) -> None:
    ratchet = load_ratchet()
    fixture_dir = tmp_path / "examples" / "parser_fragility"
    fixture_dir.mkdir(parents=True)
    benchmark_dir = tmp_path / "scripts" / "industrial"
    benchmark_dir.mkdir(parents=True)
    (benchmark_dir / "benchmark_dirty_documents.py").write_text(
        'SCHEMA_VERSION = "industrial_dirty_benchmark.v1"\n',
        encoding="utf-8",
    )
    (fixture_dir / "toc_requirement_words.txt").write_text(
        "Pagina 1\nSumario\n5.1 Deve registrar incidentes ........ 8",
        encoding="utf-8",
    )
    manifest = {
        "fixture_pack_id": "parser_fragility.v1",
        "language": "pt-BR",
        "documents": [
            {
                "filename": "toc_requirement_words.txt",
                "scenario": "toc_requirement_contamination",
                "fragility_ids": ["PF-002"],
                "fixture_kind": "synthetic_text",
                "positive_expectations": {},
                "negative_expectations": {
                    "must_not_silently_ignore_new_rule": "Must be explicitly supported."
                },
                "invariant_expectations": {
                    "deterministic_text_only": True,
                },
            }
        ],
    }
    (fixture_dir / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    snapshot = ratchet._build_fixture_snapshot(
        fixture_dir=fixture_dir,
        document=manifest["documents"][0],
    )

    with pytest.raises(
        ValueError,
        match=(
            "Unsupported negative expectation key for "
            "toc_requirement_contamination: must_not_silently_ignore_new_rule"
        ),
    ):
        ratchet._negative_expectation_passes([snapshot])


def test_current_fixture_signals_match_committed_baseline_and_skip_missing_dirty_corpus() -> None:
    ratchet = load_ratchet()
    baseline = cast(
        "dict[str, Any]",
        json.loads(BASELINE.read_text(encoding="utf-8")),
    )
    current = ratchet.build_current_signals(
        repo_root=ROOT,
        dirty_corpus_dir=ROOT / ".run" / "industrial-real-missing-for-ratchet-test",
    )

    report = ratchet.compare_to_baseline(current=current, baseline=baseline)

    assert report["status"] == "pass"
    assert current["dirty_corpus_optional"] == {
        "status": "skipped",
        "reason": ".run/industrial-real-missing-for-ratchet-test not found",
    }


def test_committed_baseline_contains_no_private_or_dirty_paths() -> None:
    ratchet = load_ratchet()
    payload = BASELINE.read_text(encoding="utf-8")

    assert not ratchet.find_private_path_tokens(json.loads(payload))
    assert str(ROOT) not in payload
    assert "C:\\" not in payload
    assert ".run/" not in payload
    assert ".run\\" not in payload
