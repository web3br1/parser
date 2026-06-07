from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "examples" / "parser_fragility"
MANIFEST = FIXTURE_DIR / "manifest.json"
CATALOG = ROOT / "docs" / "07-qa" / "PARSER_FRAGILITY_CATALOG.md"
DOC = ROOT / "docs" / "07-qa" / "PARSER_FIXTURE_FACTORY.md"
ADVERSARIAL_TEST = ROOT / "packages" / "parsers" / "tests" / "test_industrial_negative_adversarial.py"

REQUIRED_TOP_LEVEL_FIELDS = {
    "fixture_pack_id",
    "language",
    "documents",
}

REQUIRED_DOCUMENT_FIELDS = {
    "filename",
    "scenario",
    "fragility_ids",
    "fixture_kind",
    "positive_expectations",
    "negative_expectations",
    "invariant_expectations",
}

EXPECTED_SCENARIOS = {
    "multi_document_appendix_code_ambiguity",
    "toc_requirement_contamination",
    "repeated_header_footer_contamination",
    "figure_reference_without_visual_evidence",
    "sparse_image_placeholder_review_risk",
    "section_hierarchy_gap",
    "evidence_quote_boundary_drift",
    "split_document_stress_surrogate",
}

NEGATIVE_PREFIXES = ("must_not_promote", "must_not_claim")
MAX_FIXTURE_BYTES = 2_500


def _catalog_ids() -> set[str]:
    markdown = CATALOG.read_text(encoding="utf-8")
    return {
        line.split("|", maxsplit=2)[1].strip()
        for line in markdown.splitlines()
        if line.startswith("| PF-")
    }


def _manifest() -> dict[str, object]:
    assert MANIFEST.exists(), "Parser fragility fixture manifest is missing"
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_parser_fragility_fixture_manifest_has_required_schema() -> None:
    manifest = _manifest()
    missing = REQUIRED_TOP_LEVEL_FIELDS - set(manifest)
    assert not missing, f"Fixture manifest missing fields: {sorted(missing)}"
    assert manifest["fixture_pack_id"] == "parser_fragility.v1"
    assert manifest["language"] == "pt-BR"
    assert isinstance(manifest["documents"], list)
    assert len(manifest["documents"]) == len(EXPECTED_SCENARIOS)

    scenarios = {document["scenario"] for document in manifest["documents"]}
    assert scenarios == EXPECTED_SCENARIOS


def test_parser_fragility_fixture_documents_are_linked_to_catalog_ids() -> None:
    manifest = _manifest()
    allowed_ids = _catalog_ids()

    for document in manifest["documents"]:
        missing = REQUIRED_DOCUMENT_FIELDS - set(document)
        assert not missing, f"{document.get('filename')} missing fields: {sorted(missing)}"
        assert document["fixture_kind"] == "synthetic_text"

        fragility_ids = document["fragility_ids"]
        assert isinstance(fragility_ids, list)
        assert fragility_ids, f"{document['filename']} has no fragility_ids"
        assert set(fragility_ids) <= allowed_ids

        positive = document["positive_expectations"]
        negative = document["negative_expectations"]
        invariants = document["invariant_expectations"]
        assert isinstance(positive, dict)
        assert isinstance(negative, dict)
        assert isinstance(invariants, dict)
        assert positive or negative, f"{document['filename']} has no positive or negative expectations"
        assert all(key.startswith(NEGATIVE_PREFIXES) for key in negative), document["filename"]
        assert invariants, f"{document['filename']} has no invariant expectations"


def test_parser_fragility_fixture_files_exist_and_stay_compact() -> None:
    manifest = _manifest()

    for document in manifest["documents"]:
        fixture_path = FIXTURE_DIR / document["filename"]
        assert fixture_path.exists(), document["filename"]
        assert fixture_path.suffix == ".txt"

        content = fixture_path.read_text(encoding="utf-8")
        assert content.strip() == content.rstrip()
        assert len(content.encode("utf-8")) <= MAX_FIXTURE_BYTES
        assert ".run" not in content
        assert "http://" not in content
        assert "https://" not in content


def test_fixture_factory_documentation_explains_promotion_boundary() -> None:
    assert DOC.exists(), "Parser fixture factory documentation is missing"
    markdown = DOC.read_text(encoding="utf-8")

    assert "manifest.json" in markdown
    assert "synthetic_text" in markdown
    assert "Promote" in markdown
    assert "PDF" in markdown


def test_negative_adversarial_parser_tests_reference_manifest_fixtures() -> None:
    assert ADVERSARIAL_TEST.exists(), "Negative adversarial parser test file is missing"
    test_source = ADVERSARIAL_TEST.read_text(encoding="utf-8")

    for document in _manifest()["documents"]:
        assert document["filename"] in test_source
