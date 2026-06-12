from __future__ import annotations

import json
from pathlib import Path

FIXTURE_DIR = Path("examples/industrial_qms")


def test_industrial_qms_fixture_manifest_covers_required_scenarios() -> None:
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    scenarios = {item["scenario"] for item in manifest["documents"]}

    assert scenarios == {
        "vigent_pop_revision",
        "obsolete_pop_revision",
        "work_instruction",
        "form",
        "record_log",
        "faq",
        "table",
        "missing_revision",
        "duplicate_revision_conflict",
        "prompt_injection",
        "ocr_required",
    }


def test_industrial_qms_fixture_files_exist() -> None:
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))

    for item in manifest["documents"]:
        assert (FIXTURE_DIR / item["filename"]).exists(), item["filename"]


def test_industrial_qms_fixture_marks_ocr_required_document() -> None:
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    ocr_items = [item for item in manifest["documents"] if item.get("ocr_required")]

    assert len(ocr_items) == 1
    assert ocr_items[0]["scenario"] == "ocr_required"
