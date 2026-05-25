from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from source_pack.manifest import parse_manifest
from source_pack.readers import (
    CsvRow,
    MarkdownSection,
    build_sources,
    read_csv_rows,
    read_markdown_sections,
)

GOLD_DIR = Path(r"C:\tmp\context-builder-sources\compounding-pharmacy-gold")


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestReadCsvRows:
    def test_returns_list_of_csv_row(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "02_active_ingredients_catalog.csv")
        assert len(rows) > 0
        assert all(isinstance(r, CsvRow) for r in rows)

    def test_row_numbers_are_1_based(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "02_active_ingredients_catalog.csv")
        assert rows[0].row_number == 1
        assert rows[1].row_number == 2

    def test_headers_are_non_empty(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "02_active_ingredients_catalog.csv")
        assert len(rows[0].headers) > 0

    def test_row_data_contains_header_keys(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "02_active_ingredients_catalog.csv")
        for row in rows:
            assert set(row.row_data.keys()) == set(row.headers)

    def test_filename_stored_on_row(self) -> None:
        rows = read_csv_rows(GOLD_DIR / "02_active_ingredients_catalog.csv")
        assert rows[0].filename == "02_active_ingredients_catalog.csv"


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestReadMarkdownSections:
    def test_returns_list_of_markdown_section(self) -> None:
        sections = read_markdown_sections(GOLD_DIR / "05_sales_triage_rules.md")
        assert len(sections) > 0
        assert all(isinstance(s, MarkdownSection) for s in sections)

    def test_heading_stripped(self) -> None:
        sections = read_markdown_sections(GOLD_DIR / "05_sales_triage_rules.md")
        for s in sections:
            assert not s.heading.startswith("#")

    def test_anchor_is_slug(self) -> None:
        sections = read_markdown_sections(GOLD_DIR / "05_sales_triage_rules.md")
        for s in sections:
            assert s.anchor == s.anchor.lower()
            assert " " not in s.anchor

    def test_start_line_is_1_based(self) -> None:
        sections = read_markdown_sections(GOLD_DIR / "05_sales_triage_rules.md")
        assert all(s.start_line >= 1 for s in sections)

    def test_filename_stored_on_section(self) -> None:
        sections = read_markdown_sections(GOLD_DIR / "05_sales_triage_rules.md")
        assert all(s.filename == "05_sales_triage_rules.md" for s in sections)


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestBuildSources:
    def test_returns_64_sources(self) -> None:
        manifest = parse_manifest(GOLD_DIR / "00_source_manifest.md")
        sources = build_sources(manifest, GOLD_DIR)
        assert len(sources) == 64

    def test_all_sources_published(self) -> None:
        manifest = parse_manifest(GOLD_DIR / "00_source_manifest.md")
        sources = build_sources(manifest, GOLD_DIR)
        assert all(s["status"] == "published" for s in sources)

    def test_source_type_csv(self) -> None:
        manifest = parse_manifest(GOLD_DIR / "00_source_manifest.md")
        sources = build_sources(manifest, GOLD_DIR)
        csv_sources = [s for s in sources if s["original_filename"].endswith(".csv")]
        assert all(s["type"] == "csv" for s in csv_sources)

    def test_source_type_markdown(self) -> None:
        manifest = parse_manifest(GOLD_DIR / "00_source_manifest.md")
        sources = build_sources(manifest, GOLD_DIR)
        md_sources = [s for s in sources if s["original_filename"].endswith(".md")]
        assert all(s["type"] == "markdown" for s in md_sources)

    def test_source_ids_are_deterministic(self) -> None:
        manifest = parse_manifest(GOLD_DIR / "00_source_manifest.md")
        sources1 = build_sources(manifest, GOLD_DIR)
        sources2 = build_sources(manifest, GOLD_DIR)
        assert [s["id"] for s in sources1] == [s["id"] for s in sources2]

    def test_source_id_is_uuid_string(self) -> None:
        manifest = parse_manifest(GOLD_DIR / "00_source_manifest.md")
        sources = build_sources(manifest, GOLD_DIR)
        for s in sources:
            UUID(s["id"])  # must not raise

    def test_readme_not_in_sources(self) -> None:
        manifest = parse_manifest(GOLD_DIR / "00_source_manifest.md")
        sources = build_sources(manifest, GOLD_DIR)
        filenames = [s["original_filename"] for s in sources]
        assert "README.md" not in filenames
