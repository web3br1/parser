from __future__ import annotations

from pathlib import Path

import pytest
from source_pack.extractors import ExtractedDocument, extract_document
from source_pack.ids import stable_uuid
from source_pack.readers import CsvRow, read_csv_rows, read_markdown_sections

GOLD_DIR = Path(r"C:\tmp\context-builder-sources\compounding-pharmacy-gold")

FAKE_SOURCE = {
    "id": str(stable_uuid("source:test.csv")),
    "original_filename": "test.csv",
    "type": "csv",
    "status": "published",
}


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestExtractCatalog:
    """02_active_ingredients_catalog.csv -> facts"""

    def test_returns_extracted_document(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "02_active_ingredients_catalog.csv")
        source = {**FAKE_SOURCE, "original_filename": "02_active_ingredients_catalog.csv"}
        result = extract_document("catalog", source, rows, None)
        assert isinstance(result, ExtractedDocument)

    def test_produces_facts(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "02_active_ingredients_catalog.csv")
        source = {**FAKE_SOURCE, "original_filename": "02_active_ingredients_catalog.csv"}
        result = extract_document("catalog", source, rows, None)
        assert len(result.facts) > 0

    def test_facts_have_required_fields(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "02_active_ingredients_catalog.csv")
        source = {**FAKE_SOURCE, "original_filename": "02_active_ingredients_catalog.csv"}
        result = extract_document("catalog", source, rows, None)
        for fact in result.facts:
            for f in (
                "id",
                "fact_type",
                "schema_version",
                "normalized_content",
                "source_id",
                "chunk_id",
                "evidence_span_ids",
            ):
                assert f in fact, f"Missing field: {f}"

    def test_fact_ids_are_deterministic(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "02_active_ingredients_catalog.csv")
        source = {**FAKE_SOURCE, "original_filename": "02_active_ingredients_catalog.csv"}
        r1 = extract_document("catalog", source, rows, None)
        r2 = extract_document("catalog", source, rows, None)
        assert [f["id"] for f in r1.facts] == [f["id"] for f in r2.facts]

    def test_evidence_spans_generated(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "02_active_ingredients_catalog.csv")
        source = {**FAKE_SOURCE, "original_filename": "02_active_ingredients_catalog.csv"}
        result = extract_document("catalog", source, rows, None)
        assert len(result.evidence) > 0


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestExtractRules:
    """05_sales_triage_rules.md -> rules"""

    def test_produces_rules(self) -> None:
        sections = read_markdown_sections(GOLD_DIR / "05_sales_triage_rules.md")
        source = {**FAKE_SOURCE, "original_filename": "05_sales_triage_rules.md"}
        result = extract_document("rules", source, None, sections)
        assert len(result.rules) > 0

    def test_rules_have_required_fields(self) -> None:
        sections = read_markdown_sections(GOLD_DIR / "05_sales_triage_rules.md")
        source = {**FAKE_SOURCE, "original_filename": "05_sales_triage_rules.md"}
        result = extract_document("rules", source, None, sections)
        for rule in result.rules:
            for f in (
                "id",
                "rule_type",
                "schema_version",
                "condition",
                "action",
                "priority",
                "source_id",
                "chunk_id",
                "evidence_span_ids",
            ):
                assert f in rule, f"Missing: {f}"

    def test_rule_ids_are_deterministic(self) -> None:
        sections = read_markdown_sections(GOLD_DIR / "05_sales_triage_rules.md")
        source = {**FAKE_SOURCE, "original_filename": "05_sales_triage_rules.md"}
        r1 = extract_document("rules", source, None, sections)
        r2 = extract_document("rules", source, None, sections)
        assert [r["id"] for r in r1.rules] == [r["id"] for r in r2.rules]


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestExtractGaps:
    """14_known_gaps_and_publish_gates.csv -> gaps"""

    def test_produces_gaps(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "14_known_gaps_and_publish_gates.csv")
        source = {**FAKE_SOURCE, "original_filename": "14_known_gaps_and_publish_gates.csv"}
        result = extract_document("readiness", source, rows, None)
        assert len(result.gaps) > 0

    def test_gaps_have_required_fields(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "14_known_gaps_and_publish_gates.csv")
        source = {**FAKE_SOURCE, "original_filename": "14_known_gaps_and_publish_gates.csv"}
        result = extract_document("readiness", source, rows, None)
        for gap in result.gaps:
            for f in ("id", "kind", "description", "severity", "status"):
                assert f in gap, f"Missing: {f}"


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestExtractTests:
    """59_synthetic_customer_query_eval_set.csv -> tests"""

    def test_produces_tests(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "59_synthetic_customer_query_eval_set.csv")
        source = {**FAKE_SOURCE, "original_filename": "59_synthetic_customer_query_eval_set.csv"}
        result = extract_document("eval_set", source, rows, None)
        assert len(result.tests) > 0

    def test_tests_have_required_fields(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "59_synthetic_customer_query_eval_set.csv")
        source = {**FAKE_SOURCE, "original_filename": "59_synthetic_customer_query_eval_set.csv"}
        result = extract_document("eval_set", source, rows, None)
        for t in result.tests:
            for f in ("id", "name", "status", "prompt", "expected_behavior"):
                assert f in t, f"Missing: {f}"


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestExtractMemoryPolicy:
    """16_memory_and_tool_policy.md -> memory_policy_patch + tool_recommendations"""

    def test_produces_memory_policy_patch(self) -> None:
        sections = read_markdown_sections(GOLD_DIR / "16_memory_and_tool_policy.md")
        source = {**FAKE_SOURCE, "original_filename": "16_memory_and_tool_policy.md"}
        result = extract_document("memory_tool_policy", source, None, sections)
        assert isinstance(result.memory_policy_patch, dict)

    def test_produces_tool_recommendations(self) -> None:
        sections = read_markdown_sections(GOLD_DIR / "16_memory_and_tool_policy.md")
        source = {**FAKE_SOURCE, "original_filename": "16_memory_and_tool_policy.md"}
        result = extract_document("memory_tool_policy", source, None, sections)
        # May be empty if file has no tool sections, but type must be list
        assert isinstance(result.tool_recommendations, list)


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestExtractQuoteRules:
    """40_quote_rules_matrix.csv -> rules"""

    def test_produces_rules(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "40_quote_rules_matrix.csv")
        source = {**FAKE_SOURCE, "original_filename": "40_quote_rules_matrix.csv"}
        result = extract_document("quote_rules", source, rows, None)
        assert len(result.rules) > 0


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestExtractToolPolicy:
    """53_tool_calling_policy_matrix.csv -> rules"""

    def test_produces_rules(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "53_tool_calling_policy_matrix.csv")
        source = {**FAKE_SOURCE, "original_filename": "53_tool_calling_policy_matrix.csv"}
        result = extract_document("tool_policy", source, rows, None)
        assert len(result.rules) > 0


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestExtractToolTraces:
    """54_tool_calling_expected_traces.csv -> tests"""

    def test_produces_tests(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "54_tool_calling_expected_traces.csv")
        source = {**FAKE_SOURCE, "original_filename": "54_tool_calling_expected_traces.csv"}
        result = extract_document("tool_trace_eval", source, rows, None)
        assert len(result.tests) > 0


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestExtractReleaseGate:
    """63_release_gate_eval_suite.md -> tests"""

    def test_produces_tests(self) -> None:
        sections = read_markdown_sections(GOLD_DIR / "63_release_gate_eval_suite.md")
        source = {**FAKE_SOURCE, "original_filename": "63_release_gate_eval_suite.md"}
        result = extract_document("release_gate", source, None, sections)
        assert len(result.tests) > 0


class TestExtractorDeterminism:
    def test_same_input_same_output(self) -> None:
        rows = [CsvRow(filename="test.csv", headers=("a",), row_data={"a": "v"}, row_number=1)]
        source = {**FAKE_SOURCE, "original_filename": "test.csv"}
        r1 = extract_document("catalog", source, rows, None)
        r2 = extract_document("catalog", source, rows, None)
        assert r1.facts == r2.facts
        assert r1.evidence == r2.evidence
