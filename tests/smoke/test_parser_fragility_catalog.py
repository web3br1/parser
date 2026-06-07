from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "docs" / "07-qa" / "PARSER_FRAGILITY_CATALOG.md"

REQUIRED_FIELDS = [
    "fragility_id",
    "affected_layer",
    "severity",
    "failure_hypothesis",
    "minimal_reproducer_idea",
    "expected_red_test",
    "expected_negative_adversarial_assertion",
    "expected_benchmark_signal",
    "current_status",
]

ALLOWED_STATUSES = {
    "discovered",
    "red_test_written",
    "fixed",
    "benchmarked",
    "accepted",
    "known_limit",
}

ALLOWED_SEVERITIES = {
    "critical_publication_risk",
    "high_review_risk",
    "medium_quality_risk",
    "low_diagnostic_risk",
}

GENERIC_WORDING = {
    "make parser better",
    "improve parser",
    "better quality",
    "fix quality",
}


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _table_after_heading(markdown: str, heading: str) -> list[dict[str, str]]:
    lines = markdown.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == heading)
    except StopIteration as exc:
        raise AssertionError(f"Missing heading: {heading}") from exc

    table_lines: list[str] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("## ") and table_lines:
            break
        if stripped.startswith("|"):
            table_lines.append(stripped)
        elif table_lines and not stripped:
            break

    assert len(table_lines) >= 3, f"Missing markdown table under {heading}"
    headers = _cells(table_lines[0])
    divider = _cells(table_lines[1])
    assert headers == REQUIRED_FIELDS
    assert all(set(cell) <= {"-", ":"} and "-" in cell for cell in divider)

    entries: list[dict[str, str]] = []
    for line in table_lines[2:]:
        values = _cells(line)
        assert len(values) == len(headers), f"Wrong column count in row: {line}"
        entries.append(dict(zip(headers, values, strict=True)))
    return entries


def test_fragility_catalog_exists_and_defines_record_shape() -> None:
    assert CATALOG.exists(), "Parser fragility catalog is missing"

    markdown = CATALOG.read_text(encoding="utf-8")
    format_entries = _table_after_heading(markdown, "## Fragility Record Format")
    assert [entry["fragility_id"] for entry in format_entries] == REQUIRED_FIELDS


def test_seed_fragilities_are_testable_and_use_allowed_taxonomy() -> None:
    assert CATALOG.exists(), "Parser fragility catalog is missing"
    markdown = CATALOG.read_text(encoding="utf-8")
    entries = _table_after_heading(markdown, "## Seed Fragilities")

    assert len(entries) >= 8
    assert len({entry["fragility_id"] for entry in entries}) == len(entries)

    for entry in entries:
        missing = [field for field in REQUIRED_FIELDS if not entry[field]]
        assert not missing, f"{entry['fragility_id']} missing fields: {missing}"
        assert entry["severity"] in ALLOWED_SEVERITIES
        assert entry["current_status"] in ALLOWED_STATUSES
        assert entry["expected_red_test"].startswith("tests/")
        assert "assert" in entry["expected_negative_adversarial_assertion"].lower()
        assert entry["expected_benchmark_signal"].startswith("benchmark.")
        hypothesis = entry["failure_hypothesis"].lower()
        assert not any(phrase in hypothesis for phrase in GENERIC_WORDING)
