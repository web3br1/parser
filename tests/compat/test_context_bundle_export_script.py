from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "context_bundle" / "export_golden_bundle.py"
FIXTURE_DIR = ROOT / "examples" / "context_bundle"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "export_golden_bundle_under_test",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_fixture(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8")),
    )


def test_export_script_generates_committed_fixtures() -> None:
    module = _load_script()

    for variant, filename in module.FIXTURE_FILENAMES.items():
        assert module.build_fixture_payload(variant) == _read_fixture(filename)


def test_export_script_check_accepts_committed_fixtures() -> None:
    module = _load_script()

    assert module.main(["--check"]) == 0


def test_export_script_writes_selected_fixture(tmp_path: Path) -> None:
    module = _load_script()
    output_dir = tmp_path / "context_bundle"

    assert module.main([
        "--variant",
        "golden",
        "--output-dir",
        str(output_dir),
    ]) == 0

    assert (output_dir / "golden-context-bundle.v1.json").exists()
    assert not (output_dir / "blocked-context-bundle.v1.json").exists()
    assert json.loads(
        (output_dir / "golden-context-bundle.v1.json").read_text(encoding="utf-8")
    ) == _read_fixture("golden-context-bundle.v1.json")


def test_export_script_check_detects_fixture_drift(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    output_dir = tmp_path / "context_bundle"
    assert module.main(["--output-dir", str(output_dir)]) == 0

    golden_path = output_dir / "golden-context-bundle.v1.json"
    fixture = json.loads(golden_path.read_text(encoding="utf-8"))
    fixture["readiness"]["score"] = 99
    golden_path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")

    assert module.main(["--output-dir", str(output_dir), "--check"]) == 1
    captured = capsys.readouterr()

    assert "Fixture drift detected: golden-context-bundle.v1.json" in captured.err
    assert "Limpeza de pele" not in captured.err


def test_export_script_check_accepts_crlf_fixture(tmp_path: Path) -> None:
    module = _load_script()
    output_dir = tmp_path / "context_bundle"
    assert module.main(["--variant", "golden", "--output-dir", str(output_dir)]) == 0

    golden_path = output_dir / "golden-context-bundle.v1.json"
    golden_path.write_bytes(
        golden_path.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
    )

    assert module.main([
        "--variant",
        "golden",
        "--output-dir",
        str(output_dir),
        "--check",
    ]) == 0
