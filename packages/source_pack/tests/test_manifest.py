from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from source_pack.manifest import (
    SourcePackManifest,
    SourcePackPreflight,
    parse_manifest,
    preflight_source_pack,
)

GOLD_DIR = Path(r"C:\tmp\context-builder-sources\compounding-pharmacy-gold")
MANIFEST_PATH = GOLD_DIR / "00_source_manifest.md"


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestManifestParser:
    def test_parse_returns_manifest(self) -> None:
        m = parse_manifest(MANIFEST_PATH)
        assert isinstance(m, SourcePackManifest)

    def test_source_pack_id(self) -> None:
        m = parse_manifest(MANIFEST_PATH)
        assert m.source_pack_id == "compounding-pharmacy-gold-source-pack"

    def test_source_pack_version_present(self) -> None:
        m = parse_manifest(MANIFEST_PATH)
        assert m.source_pack_version  # non-empty

    def test_language(self) -> None:
        m = parse_manifest(MANIFEST_PATH)
        assert m.language == "pt-BR"

    def test_intended_consumer(self) -> None:
        m = parse_manifest(MANIFEST_PATH)
        assert m.intended_consumer == "context_builder"

    def test_official_references_non_empty(self) -> None:
        m = parse_manifest(MANIFEST_PATH)
        assert len(m.official_references) >= 5

    def test_document_roles_count(self) -> None:
        m = parse_manifest(MANIFEST_PATH)
        # 64 numbered files listed
        assert len(m.document_roles) == 64

    def test_document_role_fields(self) -> None:
        m = parse_manifest(MANIFEST_PATH)
        first = m.document_roles[0]
        assert first.file == "01_regulatory_scope_and_safety_policy.md"
        assert first.document_type == "policy"

    def test_official_reference_fields(self) -> None:
        m = parse_manifest(MANIFEST_PATH)
        anvisa = next(r for r in m.official_references if r.source_id == "anvisa_dcb_2026")
        assert "anvisa" in anvisa.url.lower() or "gov.br" in anvisa.url.lower()


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
class TestPreflightSourcePack:
    def test_preflight_returns_preflight(self) -> None:
        pf = preflight_source_pack(GOLD_DIR)
        assert isinstance(pf, SourcePackPreflight)

    def test_numbered_source_count_is_64(self) -> None:
        pf = preflight_source_pack(GOLD_DIR)
        assert pf.numbered_source_count == 64

    def test_no_missing_listed_files(self) -> None:
        pf = preflight_source_pack(GOLD_DIR)
        assert pf.missing_listed_files == []

    def test_readme_is_present(self) -> None:
        pf = preflight_source_pack(GOLD_DIR)
        assert pf.readme_present is True

    def test_preflight_ok(self) -> None:
        pf = preflight_source_pack(GOLD_DIR)
        assert pf.ok is True

    def test_readme_not_counted_as_numbered_source(self) -> None:
        pf = preflight_source_pack(GOLD_DIR)
        # README.md should not appear in numbered sources
        assert pf.numbered_source_count == 64  # not 65

    def test_extra_unlisted_detection(self, tmp_path: Path) -> None:
        # Copy manifest to tmp and add an extra numbered file
        shutil.copy(MANIFEST_PATH, tmp_path / "00_source_manifest.md")
        # Create all listed files
        m = parse_manifest(MANIFEST_PATH)
        for dr in m.document_roles:
            (tmp_path / dr.file).touch()
        # Add an extra unlisted numbered file
        (tmp_path / "99_unlisted_extra.csv").touch()
        pf = preflight_source_pack(tmp_path)
        assert "99_unlisted_extra.csv" in pf.extra_unlisted_files

    def test_missing_file_detection(self, tmp_path: Path) -> None:
        shutil.copy(MANIFEST_PATH, tmp_path / "00_source_manifest.md")
        # Create all listed files except the last
        m = parse_manifest(MANIFEST_PATH)
        for dr in m.document_roles[:-1]:
            (tmp_path / dr.file).touch()
        pf = preflight_source_pack(tmp_path)
        assert m.document_roles[-1].file in pf.missing_listed_files
        assert pf.ok is False
