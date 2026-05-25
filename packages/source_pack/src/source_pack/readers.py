from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from source_pack.ids import slug_from_filename, stable_uuid
from source_pack.manifest import SourcePackManifest


@dataclass(frozen=True)
class CsvRow:
    filename: str
    headers: tuple[str, ...]
    row_data: dict[str, str]
    row_number: int  # 1-based data row (header = 0, first data row = 1)

    @property
    def data(self) -> dict[str, str]:
        return self.row_data

    @property
    def line_number(self) -> int:
        return self.row_number + 1


@dataclass(frozen=True)
class MarkdownSection:
    filename: str
    heading: str      # section heading text (stripped of #)
    level: int        # heading level (1, 2, 3...)
    anchor: str       # slug of heading, deterministic
    body: str         # content under heading until next same-or-higher heading
    start_line: int   # 1-based line number of the heading


def read_csv_rows(path: Path) -> list[CsvRow]:
    """Open CSV (UTF-8 with BOM support) and return one CsvRow per data row.

    row_number is 1-based (first data row = 1).
    Skips rows where all values are empty strings.
    headers are the cells from the first row.
    """
    filename = path.name
    rows: list[CsvRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers: tuple[str, ...] = tuple(reader.fieldnames or [])
        for index, row in enumerate(reader, start=1):
            row_data: dict[str, str] = {}
            for key, value in row.items():
                if key is None:
                    # Extra columns beyond defined headers — skip
                    continue
                row_data[key] = str(value or "")
            # Skip completely empty rows
            if all(v == "" for v in row_data.values()):
                continue
            rows.append(
                CsvRow(
                    filename=filename,
                    headers=headers,
                    row_data=row_data,
                    row_number=index,
                )
            )
    return rows


def read_markdown_sections(path: Path) -> list[MarkdownSection]:
    """Parse a Markdown file and return one MarkdownSection per heading.

    - Strips YAML frontmatter (--- delimiters) if present.
    - heading: text after stripping # and surrounding whitespace.
    - anchor: computed as re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
    - body: lines between this heading and next heading at same-or-higher level.
    - start_line: 1-based line number of the heading in the original file.
    """
    filename = path.name
    raw = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    lines = raw.splitlines()

    # Strip YAML frontmatter if present
    content_start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                content_start = i + 1
                break

    heading_pattern = re.compile(r"^(#+)\s+(.+)$")

    # First pass: collect all headings with their positions
    headings: list[tuple[int, int, str]] = []  # (line_index, level, heading_text)
    for i, line in enumerate(lines):
        if i < content_start:
            continue
        m = heading_pattern.match(line)
        if m:
            level = len(m.group(1))
            heading_text = m.group(2).strip()
            headings.append((i, level, heading_text))

    if not headings:
        return []

    sections: list[MarkdownSection] = []
    for pos, (line_idx, level, heading_text) in enumerate(headings):
        anchor = re.sub(r"[^a-z0-9]+", "-", heading_text.lower()).strip("-")

        # Body: lines after this heading until end-of-file or next heading
        body_start = line_idx + 1
        if pos + 1 < len(headings):
            body_end = headings[pos + 1][0]
        else:
            body_end = len(lines)

        body = "\n".join(lines[body_start:body_end]).strip()

        sections.append(
            MarkdownSection(
                filename=filename,
                heading=heading_text,
                level=level,
                anchor=anchor,
                body=body,
                start_line=line_idx + 1,  # convert 0-based index to 1-based
            )
        )

    return sections


def build_sources(
    manifest: SourcePackManifest,
    source_dir: Path,
) -> list[dict[str, Any]]:
    """Return one source dict per DocumentRole in the manifest.

    Each dict follows the ContextBundleSource contract:
      id                  str(UUID) — deterministic from "source:<filename>"
      title               str — display name derived from filename
      original_filename   str — the raw filename from the manifest
      type                "csv" | "markdown"
      source_reliability  "synthetic_approved"
      authority_level     str — document_type from the manifest role
      status              "published"

    README.md is excluded unless explicitly listed in document_roles.
    """
    sources: list[dict[str, Any]] = []
    for dr in manifest.document_roles:
        file_type = "csv" if dr.file.endswith(".csv") else "markdown"
        sources.append(
            {
                "id": str(stable_uuid(f"source:{dr.file}")),
                "title": slug_from_filename(dr.file),
                "original_filename": dr.file,
                "type": file_type,
                "source_reliability": "synthetic_approved",
                "authority_level": dr.document_type,
                "status": "published",
            }
        )
    return sources


# ---------------------------------------------------------------------------
# Legacy helpers kept for backward-compat with other modules in the package.
# ---------------------------------------------------------------------------

def list_numbered_sources(source_dir: Path) -> list[Path]:
    """Return sorted list of numbered source files (01_... to NN_...) excluding manifest."""
    return sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file()
        and re.match(r"^\d{2}_.+\.(?:csv|md)$", path.name)
        and not path.name.startswith("00_")
    )


def read_text(path: Path) -> str:
    """Read a text file normalising line endings."""
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
