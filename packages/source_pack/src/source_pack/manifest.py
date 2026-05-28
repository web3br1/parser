from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocumentRole:
    file: str
    document_type: str
    expected_extraction: str


@dataclass(frozen=True)
class OfficialReference:
    source_id: str
    authority: str
    title: str
    role: str
    url: str


@dataclass(frozen=True)
class SourcePackManifest:
    source_pack_id: str
    source_pack_version: str
    language: str
    intended_consumer: str
    publication_status: str
    official_references: list[OfficialReference]
    document_roles: list[DocumentRole]

    def document_role_by_file(self, filename: str) -> DocumentRole | None:
        """Return the DocumentRole for *filename*, or None if not listed."""
        for role in self.document_roles:
            if role.file == filename:
                return role
        return None


# ---------------------------------------------------------------------------
# Legacy alias kept for compiler backward-compat during migration.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SourceManifest:
    source_pack_id: str
    source_pack_version: str
    language: str
    intended_consumer: str
    publication_status: str
    document_roles: dict[str, DocumentRole]
    official_references: dict[str, OfficialReference]


@dataclass(frozen=True)
class SourcePackPreflight:
    manifest: SourcePackManifest
    numbered_source_count: int
    missing_listed_files: list[str]
    extra_unlisted_files: list[str]
    readme_present: bool
    ok: bool


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_manifest(path: Path) -> SourcePackManifest:
    text = path.read_text(encoding="utf-8-sig")
    frontmatter = _frontmatter(text)
    return SourcePackManifest(
        source_pack_id=frontmatter.get("source_pack_id", ""),
        source_pack_version=frontmatter.get("source_pack_version", ""),
        language=frontmatter.get("language", ""),
        intended_consumer=frontmatter.get("intended_consumer", ""),
        publication_status=frontmatter.get("publication_status", ""),
        official_references=_official_references(text),
        document_roles=_document_roles(text),
    )


def preflight_source_pack(source_dir: Path) -> SourcePackPreflight:
    manifest_path = source_dir / "00_source_manifest.md"
    manifest = parse_manifest(manifest_path)

    _numbered = re.compile(r"^\d+_")
    all_files = {p.name for p in source_dir.iterdir() if p.is_file()}
    numbered_files = {name for name in all_files if _numbered.match(name)}
    # Exclude the manifest itself (00_source_manifest.md is numbered but not a source)
    numbered_sources = {
        name for name in numbered_files if name != "00_source_manifest.md"
    }

    listed_files = {dr.file for dr in manifest.document_roles}

    missing_listed_files = sorted(
        dr.file for dr in manifest.document_roles if dr.file not in all_files
    )
    extra_unlisted_files = sorted(numbered_sources - listed_files)

    return SourcePackPreflight(
        manifest=manifest,
        numbered_source_count=len(numbered_sources),
        missing_listed_files=missing_listed_files,
        extra_unlisted_files=extra_unlisted_files,
        readme_present=(source_dir / "README.md").exists(),
        ok=len(missing_listed_files) == 0,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _frontmatter(text: str) -> dict[str, str]:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}
    _, body = normalized.split("---\n", 1)
    yaml_text, _rest = body.split("---\n", 1)
    values: dict[str, str] = {}
    for line in yaml_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def _document_roles(text: str) -> list[DocumentRole]:
    rows = _table_rows_after_heading(text, "## Document Roles")
    roles: list[DocumentRole] = []
    for row in rows:
        if len(row) < 3 or row[0] == "file":
            continue
        roles.append(
            DocumentRole(
                file=row[0],
                document_type=row[1],
                expected_extraction=row[2],
            )
        )
    return roles


def _official_references(text: str) -> list[OfficialReference]:
    rows = _table_rows_after_heading(text, "## Official Source References")
    references: list[OfficialReference] = []
    for row in rows:
        if len(row) < 5 or row[0] == "source_id":
            continue
        references.append(
            OfficialReference(
                source_id=row[0],
                authority=row[1],
                title=row[2],
                role=row[3],
                url=row[4],
            )
        )
    return references


def _table_rows_after_heading(text: str, heading: str) -> list[list[str]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if heading not in normalized:
        return []
    section = normalized.split(heading, 1)[1]
    lines: list[str] = []
    for line in section.splitlines()[1:]:
        if line.startswith("## "):
            break
        if line.strip().startswith("|"):
            lines.append(line.strip())
    rows: list[list[str]] = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        rows.append(cells)
    return rows
