from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SOURCE_PACK = Path("C:/tmp/context-builder-sources/compounding-pharmacy-gold")
SCRIPT = Path("scripts/source_pack/compile_context_bundle.py")
pytestmark = pytest.mark.skipif(
    not SOURCE_PACK.exists(),
    reason="compounding pharmacy gold source pack is not available",
)


def test_compile_context_bundle_cli_writes_output(tmp_path: Path) -> None:
    output = tmp_path / "compounding-pharmacy-gold.context_bundle.v1.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(SOURCE_PACK),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output.exists()
    assert "context_bundle.v1" in output.read_text(encoding="utf-8")


def test_compile_context_bundle_cli_accepts_source_dir_flag(tmp_path: Path) -> None:
    output = tmp_path / "compounding-pharmacy-gold.context_bundle.v1.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-dir",
            str(SOURCE_PACK),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output.exists()


def test_compile_context_bundle_cli_check_fails_for_stale_output(tmp_path: Path) -> None:
    output = tmp_path / "compounding-pharmacy-gold.context_bundle.v1.json"
    output.write_text("{}", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(SOURCE_PACK),
            "--output",
            str(output),
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "stale" in result.stderr
