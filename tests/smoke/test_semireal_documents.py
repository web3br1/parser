from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_semireal_dataset_has_20_documents_across_supported_formats() -> None:
    module = load_module(
        ROOT / "scripts" / "pilot" / "generate_semireal_documents.py",
        "generate_semireal_documents_under_test",
    )

    documents = module.build_documents()

    assert len(documents) == 20
    assert len({document.filename for document in documents}) == 20
    assert {document.format for document in documents} == {"csv", "docx", "pdf", "txt", "xlsx"}
    assert all(document.expected for document in documents)


def test_semireal_generator_writes_manifest_and_files(tmp_path: Path) -> None:
    module = load_module(
        ROOT / "scripts" / "pilot" / "generate_semireal_documents.py",
        "generate_semireal_documents_write_under_test",
    )

    module.generate(tmp_path)

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["document_count"] == 20
    assert len(manifest["documents"]) == 20
    for item in manifest["documents"]:
        assert (tmp_path / item["filename"]).exists()
