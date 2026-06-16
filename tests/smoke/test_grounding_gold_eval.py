from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "quality" / "grounding_gold_eval.py"
MANIFEST = ROOT / "examples" / "grounding_gold" / "manifest.json"


def load_eval() -> Any:
    module_name = "grounding_gold_eval_under_test"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------


def test_committed_manifest_loads() -> None:
    ev = load_eval()
    manifest = ev.load_manifest(MANIFEST)
    assert manifest["schema_version"] == ev.MANIFEST_SCHEMA_VERSION
    assert len(manifest["cases"]) >= 20


def test_bad_schema_version_raises(tmp_path: Path) -> None:
    ev = load_eval()
    path = tmp_path / "m.json"
    path.write_text('{"schema_version": "wrong", "cases": []}', encoding="utf-8")
    with pytest.raises(ValueError):
        ev.load_manifest(path)


def test_empty_cases_raises(tmp_path: Path) -> None:
    ev = load_eval()
    path = tmp_path / "m.json"
    path.write_text(
        '{"schema_version": "grounding_gold_manifest.v1", "cases": []}', encoding="utf-8"
    )
    with pytest.raises(ValueError):
        ev.load_manifest(path)


def test_duplicate_case_id_raises(tmp_path: Path) -> None:
    ev = load_eval()
    path = tmp_path / "m.json"
    case = (
        '{"case_id": "x", "fact_type": "service_price", "chunk_text": "a", '
        '"evidence_quote": "a", "expected_deterministic": "passed"}'
    )
    path.write_text(
        '{"schema_version": "grounding_gold_manifest.v1", "cases": [' + case + "," + case + "]}",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        ev.load_manifest(path)


# ---------------------------------------------------------------------------
# Deterministic check runs for real; zero false passes on the committed slice
# ---------------------------------------------------------------------------


def test_committed_slice_has_zero_deterministic_false_pass() -> None:
    ev = load_eval()
    report = ev.compute_report(ev.load_manifest(MANIFEST))
    assert report["deterministic"]["false_pass_count"] == 0
    assert report["deterministic"]["false_fail_count"] == 0
    assert report["gates"]["deterministic_false_pass"]["passed"] is True


def test_committed_slice_gates_pass_with_stub_verifier() -> None:
    ev = load_eval()
    report = ev.compute_report(ev.load_manifest(MANIFEST), enforce=True)
    assert report["gates_passed"] is True
    assert report["status"] == "pass"
    # Entailment metrics are tagged with the modality they came from.
    assert report["modalities"] == ["clean_document"]


# ---------------------------------------------------------------------------
# Entailment metric math (synthetic verifier predictions)
# ---------------------------------------------------------------------------


def test_false_positive_verifier_drops_precision_and_fails_enforced_gate() -> None:
    ev = load_eval()
    manifest = ev.load_manifest(MANIFEST)
    # A verifier that says "passed" for everything turns every negated/exception
    # case into a false positive, dropping precision below threshold.
    report = ev.compute_report(manifest, enforce=True, verifier=lambda case: "passed")
    assert report["entailment"]["false_positive"] > 0
    assert report["entailment"]["precision"] < ev.ENTAILMENT_PRECISION_MIN
    assert report["gates"]["entailment_precision"]["passed"] is False
    assert report["status"] == "fail"


def test_always_abstain_breaches_abstention_ceiling() -> None:
    ev = load_eval()
    manifest = ev.load_manifest(MANIFEST)
    report = ev.compute_report(manifest, enforce=True, verifier=lambda case: "abstained")
    assert report["entailment"]["abstention_rate"] > ev.ABSTENTION_RATE_MAX
    assert report["gates"]["abstention_rate"]["passed"] is False
    assert report["status"] == "fail"


def test_non_enforce_never_fails_on_below_threshold_gate() -> None:
    ev = load_eval()
    manifest = ev.load_manifest(MANIFEST)
    # Same failing verifier, but without enforce the slice is a non-blocking signal.
    report = ev.compute_report(manifest, enforce=False, verifier=lambda case: "passed")
    assert report["gates_passed"] is False
    assert report["status"] == "pass"


# ---------------------------------------------------------------------------
# Deterministic JSON + CLI exit codes
# ---------------------------------------------------------------------------


def test_report_json_is_deterministic() -> None:
    ev = load_eval()
    manifest = ev.load_manifest(MANIFEST)
    first = ev.render_report_json(ev.compute_report(manifest))
    second = ev.render_report_json(ev.compute_report(manifest))
    assert first == second
    assert str(ROOT) not in first  # no absolute repo path leaks


def test_cli_exits_zero_without_enforce() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(ROOT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert '"schema_version": "grounding_gold_eval.v1"' in result.stdout


def test_cli_invalid_manifest_exits_two(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(ROOT),
            "--manifest",
            str(tmp_path / "missing.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
