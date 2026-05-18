from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

PRECISION_MIN = 0.85
RECALL_MIN = 0.75
NEGATIVE_TYPES = {
    "expired_rule",
    "deprecated",
    "deprecated_contact",
    "deprecated_payment_method",
    "suspended",
    "suspended_service",
    "prompt_injection",
    "product_price",
}
RULE_TYPES = {"discount_rule", "cancellation_policy"}


def compute_semantic_metrics(
    manifest: dict[str, Any],
    predictions: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = _expected_items(manifest)
    predicted = _prediction_items(predictions)

    expected_keys = {item["key"] for item in expected if item["type"] not in NEGATIVE_TYPES}
    negative_keys = {item["key"] for item in expected if item["type"] in NEGATIVE_TYPES}
    negative_source_values = {
        f"{item['source_filename']}|{item['canonical']}"
        for item in expected
        if item["type"] in NEGATIVE_TYPES
    }
    predicted_keys = {item["key"] for item in predicted}

    matched = expected_keys & predicted_keys
    false_positives = predicted_keys - expected_keys
    missing = expected_keys - predicted_keys
    negative_false_positives = len(false_positives & negative_keys) + sum(
        1
        for item in predicted
        if item["key"] in false_positives
        and f"{item['source_filename']}|{item['canonical']}" in negative_source_values
    )

    precision = _rate(len(matched), len(predicted_keys))
    recall = _rate(len(matched), len(expected_keys))
    f1 = 0.0 if precision + recall == 0 else round(2 * precision * recall / (precision + recall), 4)

    result = {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_count": len(false_positives),
        "missing_count": len(missing),
        "critical_false_positives": negative_false_positives,
        "negative_test_false_positives": negative_false_positives,
        "by_type": _group_metrics(expected, predicted, "type"),
        "by_source": _group_metrics(expected, predicted, "source_filename"),
        "missing": sorted(missing),
        "false_positives": sorted(false_positives),
    }
    result["semantic_gate"] = _semantic_gate(result)
    return result


def build_not_evaluated_report(manifest: dict[str, Any], reason: str) -> dict[str, Any]:
    expected = _expected_items(manifest)
    return {
        "status": "not_evaluated",
        "warning": reason,
        "expected_count": len([item for item in expected if item["type"] not in NEGATIVE_TYPES]),
        "negative_expected_count": len([item for item in expected if item["type"] in NEGATIVE_TYPES]),
        "mechanical_pass": None,
        "semantic_pass": None,
        "semantic_gate": {"passed": None, "gates": {}},
    }


def load_predictions(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    if isinstance(payload, dict):
        for key in ("predictions", "items", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value]
    raise ValueError("Predictions file must be a list or contain predictions/items/records")


def load_predictions_from_pilot_report(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Pilot report must be a JSON object")
    predictions = payload.get("semantic_predictions")
    if isinstance(predictions, list):
        return [dict(item) for item in predictions]
    tables = payload.get("tables")
    if isinstance(tables, dict):
        return export_predictions_from_tables(tables)
    raise ValueError("Pilot report must contain semantic_predictions or tables")


def export_predictions_from_tables(tables: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    sources_by_id = {
        str(source.get("id")): str(source.get("original_filename") or source.get("filename") or "")
        for source in tables.get("sources", [])
    }
    predictions = [
        _prediction_from_fact(row, sources_by_id)
        for row in _published_rows(tables, "published_facts", "facts")
        if _has_fact_payload(row)
    ]
    predictions.extend(
        _prediction_from_rule(row, sources_by_id)
        for row in _published_rows(tables, "published_rules", "rules")
        if _has_rule_payload(row)
    )
    predictions.extend(
        _prediction_from_unknown(row, sources_by_id)
        for row in tables.get("unknowns", [])
        if row.get("status") in {"open", "schema_requested"}
    )
    return sorted(
        predictions,
        key=lambda item: (
            item["source_filename"],
            item["record_kind"],
            item["type"],
            item["canonical"],
            item["id"],
        ),
    )


def _has_fact_payload(row: dict[str, Any]) -> bool:
    return bool(row.get("normalized_content") or row.get("content") or row.get("evidence_quote"))


def _has_rule_payload(row: dict[str, Any]) -> bool:
    return bool(row.get("condition") or row.get("action") or row.get("evidence_quote"))


def _published_rows(
    tables: dict[str, list[dict[str, Any]]],
    published_key: str,
    fallback_key: str,
) -> list[dict[str, Any]]:
    rows = tables.get(published_key) or []
    if rows:
        return rows
    return [row for row in tables.get(fallback_key, []) if row.get("status") == "published"]


def _prediction_from_fact(row: dict[str, Any], sources_by_id: dict[str, str]) -> dict[str, Any]:
    normalized_content = row.get("normalized_content") or {}
    content = row.get("content") or {}
    canonical = _canonical_from_payload(normalized_content) or _canonical_from_payload(content)
    return {
        "id": str(row.get("id", "")),
        "source_id": str(row.get("source_id", "")),
        "source_filename": sources_by_id.get(str(row.get("source_id")), ""),
        "record_kind": "fact",
        "type": str(row.get("fact_type", "")),
        "content": content,
        "normalized_content": normalized_content,
        "canonical": canonical,
        "evidence_quote": str(row.get("evidence_quote") or ""),
        "status": str(row.get("status", "published")),
    }


def _prediction_from_unknown(row: dict[str, Any], sources_by_id: dict[str, str]) -> dict[str, Any]:
    metadata = row.get("metadata") or {}
    reason = str(metadata.get("reason") or row.get("suggested_fact_type") or "unknown")
    suggested_fact_type = str(row.get("suggested_fact_type") or "")
    return {
        "id": str(row.get("id", "")),
        "source_id": str(row.get("source_id", "")),
        "source_filename": sources_by_id.get(str(row.get("source_id")), ""),
        "record_kind": "review_signal",
        "type": "unknown_facts_queue",
        "content": {
            "reason": reason,
            "suggested_fact_type": suggested_fact_type,
            "status": str(row.get("status", "")),
        },
        "normalized_content": {},
        "canonical": reason,
        "evidence_quote": "",
        "status": "published",
    }


def _prediction_from_rule(row: dict[str, Any], sources_by_id: dict[str, str]) -> dict[str, Any]:
    condition = row.get("condition") or {}
    action = row.get("action") or {}
    canonical = _canonical_from_payload({"condition": condition, "action": action})
    return {
        "id": str(row.get("id", "")),
        "source_id": str(row.get("source_id", "")),
        "source_filename": sources_by_id.get(str(row.get("source_id")), ""),
        "record_kind": "rule",
        "type": str(row.get("rule_type", "")),
        "content": {"condition": condition, "action": action},
        "normalized_content": {},
        "canonical": canonical,
        "evidence_quote": str(row.get("evidence_quote") or ""),
        "status": str(row.get("status", "published")),
    }


def _canonical_from_payload(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bool | int | float):
        return str(payload)
    if isinstance(payload, list):
        return " ".join(filter(None, (_canonical_from_payload(item) for item in payload)))
    if isinstance(payload, dict):
        preferred = [
            "canonical",
            "service_name",
            "service",
            "name",
            "amount",
            "price",
            "currency",
            "value",
            "method",
            "channel",
            "weekday",
            "day",
            "open_time",
            "close_time",
            "condition",
            "action",
            "discount",
            "text",
        ]
        keys = [key for key in preferred if key in payload]
        keys.extend(sorted(key for key in payload if key not in keys))
        return " ".join(filter(None, (_canonical_from_payload(payload[key]) for key in keys)))
    return str(payload)


def _semantic_gate(metrics: dict[str, Any]) -> dict[str, Any]:
    gates = {
        "precision": {
            "threshold": f">= {PRECISION_MIN}",
            "value": metrics["precision"],
            "passed": metrics["precision"] >= PRECISION_MIN,
        },
        "recall": {
            "threshold": f">= {RECALL_MIN}",
            "value": metrics["recall"],
            "passed": metrics["recall"] >= RECALL_MIN,
        },
        "critical_false_positives": {
            "threshold": "= 0",
            "value": metrics["critical_false_positives"],
            "passed": metrics["critical_false_positives"] == 0,
        },
        "negative_test_false_positives": {
            "threshold": "= 0",
            "value": metrics["negative_test_false_positives"],
            "passed": metrics["negative_test_false_positives"] == 0,
        },
    }
    return {"passed": all(gate["passed"] for gate in gates.values()), "gates": gates}


def _expected_items(manifest: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for document in manifest.get("documents", []):
        filename = str(document.get("filename", ""))
        expected = document.get("expected", [])
        if isinstance(expected, list):
            for entry in expected:
                items.append(
                    _item(
                        filename,
                        str(entry.get("kind", "fact")),
                        str(entry.get("type", "")),
                        str(entry.get("canonical", "")),
                    )
                )
        elif isinstance(expected, dict):
            for record_type, values in expected.items():
                if not isinstance(values, list):
                    continue
                for value in values:
                    kind = "rule" if _is_rule_type(str(record_type)) else "fact"
                    items.append(_item(filename, kind, str(record_type), str(value)))
    return items


def _prediction_items(predictions: list[dict[str, Any]]) -> list[dict[str, str]]:
    items = []
    for prediction in predictions:
        if prediction.get("status") and prediction.get("status") != "published":
            continue
        canonical = (
            prediction.get("canonical")
            or prediction.get("normalized_content")
            or prediction.get("content")
            or prediction.get("evidence_quote")
            or ""
        )
        items.append(
            _item(
                str(prediction.get("source_filename", "")),
                str(prediction.get("record_kind", "fact")),
                str(prediction.get("type", "")),
                _canonical_from_payload(canonical),
            )
        )
    return items


def _is_rule_type(record_type: str) -> bool:
    return record_type in RULE_TYPES or record_type.endswith("_rule")


def _item(source_filename: str, record_kind: str, record_type: str, canonical: str) -> dict[str, str]:
    canonical_value = _canonicalize(canonical)
    return {
        "source_filename": source_filename,
        "record_kind": record_kind,
        "type": record_type,
        "canonical": canonical_value,
        "key": f"{source_filename}|{record_kind}|{record_type}|{canonical_value}",
    }


def _canonicalize(value: str) -> str:
    normalized = value.strip().lower()
    normalized = "".join(
        char for char in unicodedata.normalize("NFKD", normalized) if not unicodedata.combining(char)
    )
    normalized = normalized.replace("r$", "")
    normalized = re.sub(r"\bbrl\b", "", normalized)
    normalized = normalized.replace("cartão", "cartao").replace("crédito", "credito")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _group_metrics(
    expected: list[dict[str, str]],
    predicted: list[dict[str, str]],
    field: str,
) -> dict[str, dict[str, float | int]]:
    expected_by_group: dict[str, set[str]] = defaultdict(set)
    predicted_by_group: dict[str, set[str]] = defaultdict(set)
    for item in expected:
        if item["type"] not in NEGATIVE_TYPES:
            expected_by_group[item[field]].add(item["key"])
    for item in predicted:
        predicted_by_group[item[field]].add(item["key"])

    groups = set(expected_by_group) | set(predicted_by_group)
    return {
        group: {
            "precision": _rate(
                len(expected_by_group[group] & predicted_by_group[group]),
                len(predicted_by_group[group]),
            ),
            "recall": _rate(
                len(expected_by_group[group] & predicted_by_group[group]),
                len(expected_by_group[group]),
            ),
            "expected_count": len(expected_by_group[group]),
            "predicted_count": len(predicted_by_group[group]),
        }
        for group in sorted(groups)
    }


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute semantic pilot acceptance metrics.")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--predictions")
    parser.add_argument("--pilot-report", help="Pilot JSON report containing semantic_predictions or tables.")
    parser.add_argument("--export-predictions", help="Write deterministic predictions JSON to this path.")
    parser.add_argument("--output", help="Write semantic metrics JSON report to this path.")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if args.predictions:
        predictions = load_predictions(Path(args.predictions))
    elif args.pilot_report:
        predictions = load_predictions_from_pilot_report(Path(args.pilot_report))
    else:
        predictions = []

    if args.export_predictions:
        output_path = Path(args.export_predictions)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(predictions, indent=2, sort_keys=True), encoding="utf-8")

    if predictions:
        report = compute_semantic_metrics(manifest, predictions)
        report["status"] = "evaluated"
        report["mechanical_pass"] = None
        report["semantic_pass"] = report["semantic_gate"]["passed"]
    else:
        report = build_not_evaluated_report(
            manifest,
            "No predictions supplied. Use --predictions or --pilot-report before claiming semantic acceptance.",
        )
    report["workspace_id"] = args.workspace_id
    report["prediction_count"] = len(predictions)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
