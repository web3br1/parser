from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_artificial_fixture_generation_covers_expected_formats(tmp_path: Path) -> None:
    module = load_module(
        ROOT / "scripts" / "pilot" / "artificial_pilot_suite.py",
        "artificial_pilot_suite_under_test",
    )

    fixtures = module.create_artificial_fixtures(tmp_path)

    assert set(fixtures) >= {
        "baseline.txt",
        "role_upload.txt",
        "services.csv",
        "services.docx",
        "services.xlsx",
        "services.pdf",
        "prompt_injection.txt",
        "fake.pdf",
        "empty.txt",
        "unsupported.epub",
    }
    assert fixtures["baseline.txt"].mime_type == "text/plain"
    assert fixtures["services.pdf"].mime_type == "application/pdf"
    assert fixtures["unsupported.epub"].expected == "rejected"


def test_suite_report_marks_required_gates() -> None:
    module = load_module(
        ROOT / "scripts" / "pilot" / "artificial_pilot_suite.py",
        "artificial_pilot_suite_report_under_test",
    )
    report = module.ArtificialSuiteReport()

    report.ok("dataset_baseline", "ok")
    report.fail("roles", "staff upload unexpectedly allowed")

    payload = report.to_dict()

    assert payload["status"] == "failed"
    assert payload["checks"][0]["name"] == "dataset_baseline"
    assert payload["checks"][1]["status"] == "failed"
