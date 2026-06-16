"""Grounding gold-slice evaluator (TASK-040, Task 9).

Measures the grounding stage against a committed, human-labeled corpus before the
hard grounding gate is allowed to block production flow.

Two layers, matching the design:

- Check A (deterministic evidence) runs for REAL via ``grounding.verify_evidence``.
  The gold slice asserts deterministic false passes are zero and tracks the
  deterministic false-fail rate.
- Check B (entailment) is judged by a verifier. In CI the verifier is a
  deterministic STUB (each case's ``stub_entailment`` or, by default, its
  ``expected_entailment``), so the run is reproducible. Entailment precision,
  recall and abstention are computed against the human ``expected_entailment``
  labels and are meaningful only when a real verifier is plugged in; until OCR /
  WhatsApp inputs exist the numbers describe the clean-document subset only.

Thresholds (design "Gold Slice Before Hard Gate") are always reported but only
enforced with ``--enforce`` so the slice can be wired into CI as a non-blocking
signal first. The CLI prints deterministic JSON (sorted keys, no absolute paths,
no timestamps) and exits 0 pass / 1 evaluated failure / 2 invalid input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from grounding import grounding_mode, load_stakes_config, verify_evidence

SCHEMA_VERSION = "grounding_gold_eval.v1"
MANIFEST_SCHEMA_VERSION = "grounding_gold_manifest.v1"

DETERMINISTIC_FALSE_PASS_MAX = 0
DETERMINISTIC_FALSE_FAIL_RATE_MAX = 0.02
ENTAILMENT_PRECISION_MIN = 0.95
ENTAILMENT_RECALL_MIN = 0.90
ABSTENTION_RATE_MAX = 0.10

DEFAULT_MANIFEST = Path("examples/grounding_gold/manifest.json")

_ENTAILMENT_VERDICTS = ("passed", "failed", "abstained")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    manifest_path = _resolve_repo_path(repo_root, args.manifest)

    try:
        manifest = load_manifest(manifest_path)
        report = compute_report(manifest, profile=args.profile, enforce=bool(args.enforce))
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
        description="Evaluate the grounding stage against a committed gold slice.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--profile", type=str, default="default")
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Fail (exit 1) when a gate is below threshold. Off by default.",
    )
    parser.add_argument("--report", type=Path)
    return parser.parse_args(argv)


def load_manifest(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"Manifest schema_version must be {MANIFEST_SCHEMA_VERSION}: {path.name}",
        )
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Manifest must contain a non-empty cases list")
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"Case {index} must be an object")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"Case {index} missing case_id")
        if case_id in seen:
            raise ValueError(f"Duplicate case_id: {case_id}")
        seen.add(case_id)
        for key in ("fact_type", "chunk_text", "evidence_quote", "expected_deterministic"):
            if key not in case:
                raise ValueError(f"Case {case_id} missing {key}")
        if case["expected_deterministic"] not in ("passed", "failed"):
            raise ValueError(f"Case {case_id} expected_deterministic must be passed/failed")
        exp_ent = case.get("expected_entailment")
        if exp_ent is not None and exp_ent not in _ENTAILMENT_VERDICTS:
            raise ValueError(f"Case {case_id} expected_entailment invalid: {exp_ent}")
    return payload


def stub_verifier(case: Mapping[str, Any]) -> str | None:
    """Deterministic CI stand-in for Check B.

    Returns ``stub_entailment`` when present, else the human label. Replace with a
    real ``run_grounding`` verifier path for production-grade precision/recall.
    """
    if "stub_entailment" in case:
        return cast("str | None", case["stub_entailment"])
    return cast("str | None", case.get("expected_entailment"))


def compute_report(
    manifest: Mapping[str, Any],
    *,
    profile: str = "default",
    enforce: bool = False,
    verifier: Any = stub_verifier,
) -> dict[str, Any]:
    cases = [case for case in manifest.get("cases", []) if isinstance(case, Mapping)]
    required_types = set(load_stakes_config(profile).required_grounding_types)

    det = _deterministic_metrics(cases)
    ent = _entailment_metrics(cases, required_types, profile=profile, verifier=verifier)
    modalities = sorted({str(case.get("modality", "unspecified")) for case in cases})

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "profile": profile,
        "modalities": modalities,
        "case_count": len(cases),
        "required_grounding_types": sorted(required_types),
        "deterministic": det,
        "entailment": ent,
    }
    report["gates"] = _gates(det, ent)
    report["enforced"] = enforce
    gates_pass = all(gate["passed"] for gate in report["gates"].values())
    report["gates_passed"] = gates_pass
    # Without --enforce the slice is a non-blocking signal: it only fails on a
    # broken/invalid manifest (handled earlier), never on a below-threshold gate.
    report["status"] = "pass" if (not enforce or gates_pass) else "fail"
    return report


def _deterministic_metrics(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    false_pass = 0
    false_fail = 0
    expected_pass = 0
    correct = 0
    by_modality: dict[str, dict[str, int]] = {}
    for case in cases:
        modality = str(case.get("modality", "unspecified"))
        bucket = by_modality.setdefault(modality, {"false_pass": 0, "false_fail": 0})
        result = verify_evidence(
            str(case["chunk_text"]),
            str(case["evidence_quote"]),
            case.get("evidence_char_start"),
            case.get("evidence_char_end"),
        )
        actual = result.deterministic_status
        expected = str(case["expected_deterministic"])
        if expected == "passed":
            expected_pass += 1
        if actual == expected:
            correct += 1
        elif expected == "failed" and actual == "passed":
            false_pass += 1
            bucket["false_pass"] += 1
        elif expected == "passed" and actual == "failed":
            false_fail += 1
            bucket["false_fail"] += 1
    return {
        "case_count": len(cases),
        "false_pass_count": false_pass,
        "false_fail_count": false_fail,
        "false_fail_rate": _rate(false_fail, expected_pass),
        "accuracy": _rate(correct, len(cases)),
        "by_modality": {key: by_modality[key] for key in sorted(by_modality)},
    }


def _entailment_metrics(
    cases: Sequence[Mapping[str, Any]],
    required_types: set[str],
    *,
    profile: str,
    verifier: Any,
) -> dict[str, Any]:
    # Only required-grounding types with a labeled entailment expectation count.
    scoped = [
        case
        for case in cases
        if grounding_mode(str(case["fact_type"]), profile) == "required"
        and case.get("expected_entailment") in _ENTAILMENT_VERDICTS
    ]
    tp = fp = fn = abstained = 0
    for case in scoped:
        expected = case["expected_entailment"]
        predicted = verifier(case)
        if predicted == "abstained":
            abstained += 1
        if predicted == "passed" and expected == "passed":
            tp += 1
        elif predicted == "passed" and expected != "passed":
            fp += 1
        elif predicted != "passed" and expected == "passed":
            fn += 1
    return {
        "required_case_count": len(scoped),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "abstained_count": abstained,
        "precision": _rate(tp, tp + fp),
        "recall": _rate(tp, tp + fn),
        "abstention_rate": _rate(abstained, len(scoped)),
    }


def _gates(det: Mapping[str, Any], ent: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "deterministic_false_pass": _gate(
            "= 0", det["false_pass_count"], det["false_pass_count"] <= DETERMINISTIC_FALSE_PASS_MAX
        ),
        "deterministic_false_fail_rate": _gate(
            f"<= {DETERMINISTIC_FALSE_FAIL_RATE_MAX}",
            det["false_fail_rate"],
            det["false_fail_rate"] <= DETERMINISTIC_FALSE_FAIL_RATE_MAX,
        ),
        "entailment_precision": _gate(
            f">= {ENTAILMENT_PRECISION_MIN}",
            ent["precision"],
            ent["precision"] >= ENTAILMENT_PRECISION_MIN,
        ),
        "entailment_recall": _gate(
            f">= {ENTAILMENT_RECALL_MIN}", ent["recall"], ent["recall"] >= ENTAILMENT_RECALL_MIN
        ),
        "abstention_rate": _gate(
            f"<= {ABSTENTION_RATE_MAX}",
            ent["abstention_rate"],
            ent["abstention_rate"] <= ABSTENTION_RATE_MAX,
        ),
    }


def _gate(threshold: str, value: Any, passed: bool) -> dict[str, Any]:
    return {"threshold": threshold, "value": value, "passed": bool(passed)}


def render_report_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path.name}")
    return cast("dict[str, Any]", payload)


def _resolve_repo_path(repo_root: Path, value: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


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
