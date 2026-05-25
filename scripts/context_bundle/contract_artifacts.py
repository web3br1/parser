from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def read_text_normalized(path: Path) -> str:
    return normalize_newlines(path.read_text(encoding="utf-8"))


def sha256_normalized_text(value: str) -> str:
    return hashlib.sha256(normalize_newlines(value).encode("utf-8")).hexdigest()


def sha256_normalized_file(path: Path) -> str:
    return sha256_normalized_text(path.read_text(encoding="utf-8"))


def display_path(path: Path, *, root: Path = ROOT) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name
