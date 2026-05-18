from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def semantic_metrics_module():
    return load_module(
        ROOT / "scripts" / "pilot" / "semantic_metrics.py",
        "semantic_metrics_under_test",
    )


def test_semantic_metrics_detect_missing_expected_items(tmp_path: Path) -> None:
    module = semantic_metrics_module()
    manifest = {
        "documents": [
            {
                "filename": "sample.csv",
                "expected": [
                    {
                        "kind": "fact",
                        "type": "service_price",
                        "canonical": "corte|50|BRL",
                    },
                ],
            },
        ],
    }
    predictions: list[dict[str, str]] = []

    result = module.compute_semantic_metrics(manifest, predictions)

    assert result["recall"] == 0.0
    assert result["missing_count"] == 1


def test_semantic_metrics_accepts_matching_prediction() -> None:
    module = semantic_metrics_module()
    manifest = {
        "documents": [
            {
                "filename": "sample.csv",
                "expected": [
                    {
                        "kind": "fact",
                        "type": "service_price",
                        "canonical": "corte|50|BRL",
                    },
                ],
            },
        ],
    }
    predictions = [
        {
            "source_filename": "sample.csv",
            "record_kind": "fact",
            "type": "service_price",
            "content": "Corte R$ 50",
            "normalized_content": "corte|50|BRL",
            "evidence_quote": "Corte R$ 50",
            "status": "published",
        },
    ]

    result = module.compute_semantic_metrics(manifest, predictions)

    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["f1"] == 1.0
    assert result["false_positive_count"] == 0
    assert result["missing_count"] == 0
    assert result["semantic_gate"]["passed"] is True


def test_semantic_gate_rejects_negative_category_false_positive() -> None:
    module = semantic_metrics_module()
    manifest = {
        "documents": [
            {
                "filename": "expired.csv",
                "expected": [
                    {
                        "kind": "fact",
                        "type": "expired_rule",
                        "canonical": "pix 20 encerrada",
                    },
                ],
            },
        ],
    }
    predictions = [
        {
            "source_filename": "expired.csv",
            "record_kind": "rule",
            "type": "discount_rule",
            "content": "Pix 20%",
            "normalized_content": "pix 20 encerrada",
            "evidence_quote": "Campanha antiga Pix 20 encerrada",
            "status": "published",
        },
    ]

    result = module.compute_semantic_metrics(manifest, predictions)

    assert result["negative_test_false_positives"] == 1
    assert result["semantic_gate"]["gates"]["negative_test_false_positives"]["passed"] is False
    assert result["semantic_gate"]["passed"] is False


def test_semantic_metrics_accepts_real_manifest_expected_dict_format() -> None:
    module = semantic_metrics_module()
    manifest = {
        "documents": [
            {
                "filename": "05_centro_promocoes.xlsx",
                "expected": {
                    "discount_rule": ["Pix 5%"],
                    "expired_rule": ["Campanha antiga Pix 20 encerrada"],
                    "service_price": ["Corte feminino R$ 120"],
                },
            },
        ],
    }
    predictions = [
        {
            "source_filename": "05_centro_promocoes.xlsx",
            "record_kind": "rule",
            "type": "discount_rule",
            "canonical": "Pix 5%",
            "status": "published",
        },
        {
            "source_filename": "05_centro_promocoes.xlsx",
            "record_kind": "fact",
            "type": "service_price",
            "canonical": "Corte feminino 120 BRL",
            "status": "published",
        },
    ]

    result = module.compute_semantic_metrics(manifest, predictions)

    assert result["by_type"]["discount_rule"]["recall"] == 1.0
    assert result["missing_count"] == 0
    assert result["negative_test_false_positives"] == 0


def test_export_predictions_from_pilot_tables_has_comparison_shape() -> None:
    module = semantic_metrics_module()
    tables = {
        "sources": [
            {"id": "source-2", "original_filename": "b.csv"},
            {"id": "source-1", "original_filename": "a.csv"},
        ],
        "published_facts": [
            {
                "id": "fact-1",
                "source_id": "source-1",
                "fact_type": "service_price",
                "status": "published",
                "content": {"service_name": "Corte feminino", "price": 120, "currency": "BRL"},
                "normalized_content": {"service_name": "Corte feminino", "price": 120, "currency": "BRL"},
            },
        ],
        "published_rules": [
            {
                "id": "rule-1",
                "source_id": "source-2",
                "rule_type": "discount_rule",
                "status": "published",
                "condition": {"method": "Pix"},
                "action": {"discount": "5%"},
            },
        ],
    }

    predictions = module.export_predictions_from_tables(tables)

    assert predictions == [
        {
            "id": "fact-1",
            "source_id": "source-1",
            "source_filename": "a.csv",
            "record_kind": "fact",
            "type": "service_price",
            "content": {"service_name": "Corte feminino", "price": 120, "currency": "BRL"},
            "normalized_content": {"service_name": "Corte feminino", "price": 120, "currency": "BRL"},
            "canonical": "Corte feminino 120 BRL",
            "evidence_quote": "",
            "status": "published",
        },
        {
            "id": "rule-1",
            "source_id": "source-2",
            "source_filename": "b.csv",
            "record_kind": "rule",
            "type": "discount_rule",
            "content": {"condition": {"method": "Pix"}, "action": {"discount": "5%"}},
            "normalized_content": {},
            "canonical": "Pix 5%",
            "evidence_quote": "",
            "status": "published",
        },
    ]


def test_semantic_metrics_marks_table_report_without_payload_as_not_evaluable(tmp_path: Path) -> None:
    module = semantic_metrics_module()
    report_path = tmp_path / "pilot-report.json"
    report_path.write_text(
        json.dumps(
            {
                "tables": {
                    "sources": [{"id": "source-1", "original_filename": "sample.csv"}],
                    "published_facts": [
                        {
                            "id": "fact-1",
                            "source_id": "source-1",
                            "fact_type": "service_price",
                            "status": "published",
                        }
                    ],
                    "published_rules": [],
                }
            }
        ),
        encoding="utf-8",
    )

    predictions = module.load_predictions_from_pilot_report(report_path)

    assert predictions == []


def test_export_predictions_includes_open_unknown_review_signals() -> None:
    module = semantic_metrics_module()
    tables = {
        "sources": [{"id": "source-1", "original_filename": "injection.docx"}],
        "published_facts": [],
        "published_rules": [],
        "unknowns": [
            {
                "id": "unknown-1",
                "source_id": "source-1",
                "status": "open",
                "suggested_fact_type": None,
                "metadata": {
                    "reason": "prompt_injection",
                    "injection_patterns": ["ignore previous instructions"],
                },
            }
        ],
    }

    predictions = module.export_predictions_from_tables(tables)

    assert predictions == [
        {
            "id": "unknown-1",
            "source_id": "source-1",
            "source_filename": "injection.docx",
            "record_kind": "review_signal",
            "type": "unknown_facts_queue",
            "content": {
                "reason": "prompt_injection",
                "suggested_fact_type": "",
                "status": "open",
            },
            "normalized_content": {},
            "canonical": "prompt_injection",
            "evidence_quote": "",
            "status": "published",
        }
    ]


def test_semantic_gate_rejects_actual_manifest_deprecated_contact_false_positive() -> None:
    module = semantic_metrics_module()
    manifest = {
        "documents": [
            {
                "filename": "old-contact.pdf",
                "expected": {"deprecated_contact": ["telefone antigo 1111-1111"]},
            }
        ],
    }
    predictions = [
        {
            "source_filename": "old-contact.pdf",
            "record_kind": "fact",
            "type": "contact_info",
            "canonical": "telefone antigo 1111-1111",
            "status": "published",
        }
    ]

    result = module.compute_semantic_metrics(manifest, predictions)

    assert result["negative_test_false_positives"] == 1
    assert result["semantic_gate"]["passed"] is False


def test_semantic_metrics_cli_without_predictions_is_not_evaluated(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "filename": "sample.csv",
                        "expected": {"service_price": ["Corte feminino R$ 120"]},
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "pilot" / "semantic_metrics.py"),
            "--workspace-id",
            "workspace-id",
            "--manifest",
            str(manifest_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)

    assert report["status"] == "not_evaluated"
    assert report["semantic_pass"] is None
    assert report["prediction_count"] == 0
    assert "No predictions supplied" in report["warning"]


def test_semantic_metrics_cli_writes_output_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "semantic-report.json"
    manifest_path.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "filename": "sample.csv",
                        "expected": {"service_price": ["Corte feminino R$ 120"]},
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "pilot" / "semantic_metrics.py"),
            "--workspace-id",
            "workspace-id",
            "--manifest",
            str(manifest_path),
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "not_evaluated"
    assert report["workspace_id"] == "workspace-id"
