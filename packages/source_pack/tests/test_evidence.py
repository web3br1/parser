from __future__ import annotations

from uuid import UUID

from source_pack.evidence import (
    _safe_quote,
    evidence_from_csv_row,
    evidence_from_markdown_section,
)
from source_pack.ids import stable_uuid
from source_pack.readers import CsvRow, MarkdownSection

FAKE_SOURCE_ID = stable_uuid("source:test_file.csv")

def make_csv_row(row_number: int = 1) -> CsvRow:
    return CsvRow(
        filename="02_active_ingredients_catalog.csv",
        headers=("name", "dcb", "risk"),
        row_data={"name": "Omeprazol", "dcb": "OMEPRAZOL", "risk": "low"},
        row_number=row_number,
    )

def make_markdown_section(anchor: str = "safety-rules") -> MarkdownSection:
    return MarkdownSection(
        filename="05_sales_triage_rules.md",
        heading="Safety Rules",
        level=2,
        anchor=anchor,
        body="Rule 1: Always refer to pharmacist.",
        start_line=10,
    )

class TestEvidenceFromCsvRow:
    def test_returns_dict(self):
        ev = evidence_from_csv_row(FAKE_SOURCE_ID, make_csv_row())
        assert isinstance(ev, dict)

    def test_id_is_uuid(self):
        ev = evidence_from_csv_row(FAKE_SOURCE_ID, make_csv_row())
        UUID(str(ev["id"]))  # must not raise

    def test_id_is_deterministic(self):
        ev1 = evidence_from_csv_row(FAKE_SOURCE_ID, make_csv_row(1))
        ev2 = evidence_from_csv_row(FAKE_SOURCE_ID, make_csv_row(1))
        assert ev1["id"] == ev2["id"]

    def test_id_changes_with_row_number(self):
        ev1 = evidence_from_csv_row(FAKE_SOURCE_ID, make_csv_row(1))
        ev2 = evidence_from_csv_row(FAKE_SOURCE_ID, make_csv_row(2))
        assert ev1["id"] != ev2["id"]

    def test_row_number_preserved(self):
        ev = evidence_from_csv_row(FAKE_SOURCE_ID, make_csv_row(5))
        assert ev["row_number"] == 5

    def test_source_id_preserved(self):
        ev = evidence_from_csv_row(FAKE_SOURCE_ID, make_csv_row())
        assert ev["source_id"] == FAKE_SOURCE_ID

    def test_chunk_id_is_deterministic_uuid(self):
        ev = evidence_from_csv_row(FAKE_SOURCE_ID, make_csv_row())
        UUID(str(ev["chunk_id"]))  # must not raise

    def test_quote_is_str_or_none(self):
        ev = evidence_from_csv_row(FAKE_SOURCE_ID, make_csv_row())
        assert ev["quote"] is None or isinstance(ev["quote"], str)

    def test_quote_max_length(self):
        row = CsvRow(
            filename="test.csv",
            headers=("col",),
            row_data={"col": "x" * 1000},
            row_number=1,
        )
        ev = evidence_from_csv_row(FAKE_SOURCE_ID, row)
        assert ev["quote"] is None or len(ev["quote"]) <= 500

    def test_no_extra_fields(self):
        ev = evidence_from_csv_row(FAKE_SOURCE_ID, make_csv_row())
        allowed = {"id", "source_id", "chunk_id", "quote", "page_number", "sheet_name", "row_number"}
        assert set(ev.keys()) == allowed

class TestEvidenceFromMarkdownSection:
    def test_returns_dict(self):
        ev = evidence_from_markdown_section(FAKE_SOURCE_ID, make_markdown_section())
        assert isinstance(ev, dict)

    def test_id_is_deterministic(self):
        ev1 = evidence_from_markdown_section(FAKE_SOURCE_ID, make_markdown_section("anchor-a"))
        ev2 = evidence_from_markdown_section(FAKE_SOURCE_ID, make_markdown_section("anchor-a"))
        assert ev1["id"] == ev2["id"]

    def test_id_changes_with_anchor(self):
        ev1 = evidence_from_markdown_section(FAKE_SOURCE_ID, make_markdown_section("anchor-a"))
        ev2 = evidence_from_markdown_section(FAKE_SOURCE_ID, make_markdown_section("anchor-b"))
        assert ev1["id"] != ev2["id"]

    def test_row_number_is_none(self):
        ev = evidence_from_markdown_section(FAKE_SOURCE_ID, make_markdown_section())
        assert ev["row_number"] is None

    def test_quote_contains_heading(self):
        ev = evidence_from_markdown_section(FAKE_SOURCE_ID, make_markdown_section())
        assert ev["quote"] is not None
        assert "Safety Rules" in ev["quote"]

    def test_quote_max_length(self):
        section = MarkdownSection(
            filename="test.md",
            heading="H",
            level=1,
            anchor="h",
            body="y" * 1000,
            start_line=1,
        )
        ev = evidence_from_markdown_section(FAKE_SOURCE_ID, section)
        assert ev["quote"] is None or len(ev["quote"]) <= 500

    def test_no_extra_fields(self):
        ev = evidence_from_markdown_section(FAKE_SOURCE_ID, make_markdown_section())
        allowed = {"id", "source_id", "chunk_id", "quote", "page_number", "sheet_name", "row_number"}
        assert set(ev.keys()) == allowed

class TestSafeQuote:
    def test_redacts_secret(self):
        result = _safe_quote("key: " + "sk-" + "abcdefghijklmnopqrstuvwxyz123456")
        assert "sk-" not in result

    def test_redacts_bearer_token(self):
        token = "Bearer " + "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9xxxyyy"
        result = _safe_quote("Authorization: " + token)
        assert "Bearer" not in result

    def test_redacts_windows_path(self):
        result = _safe_quote(r"See C:\Users\admin\secrets.txt for details")
        assert r"C:\Users" not in result

    def test_none_returns_none(self):
        assert _safe_quote(None) is None

    def test_truncates_to_500(self):
        result = _safe_quote("a" * 1000)
        assert len(result) <= 500
