from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".claude",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".pytest-tmp",
    ".ruff_cache",
    ".run",
    ".uv-cache",
    ".uv-tools",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}

LOCAL_ENV_FILES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.development.local",
    ".env.production",
    ".env.production.local",
}

PATTERNS = [
    re.compile(r"SUPABASE_SERVICE_ROLE_KEY\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{20,}"),
    re.compile(r"OPENAI_API_KEY\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{20,}"),
    re.compile(r"(^|[^A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(
        r"[Bb]earer\s+"
        r"(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]{20,})"
    ),
]
GENERIC_SECRET_ASSIGNMENT = re.compile(
    r"(?P<key>[A-Z0-9_.-]*(?:SECRET|PASSWORD|PRIVATE_KEY|SERVICE_ROLE_KEY|API_KEY|ACCESS_KEY|AUTH_KEY)[A-Z0-9_.-]*)"
    r"\s*[:=]\s*"
    r"[\"']?(?P<value>[A-Za-z0-9_./+=:@$!-]{24,})[\"']?",
    re.IGNORECASE,
)
PLACEHOLDER_VALUES = {
    "changeme",
    "example",
    "placeholder",
    "replace_me",
    "replace-with-real-value",
    "your-api-key",
    "your-token",
    "your-secret",
}


def iter_files(root: Path, *, include_local_env: bool) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not include_local_env and path.name in LOCAL_ENV_FILES:
            continue
        if path.is_file():
            files.append(path)
    return files


def scan_file(path: Path, root: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    findings: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for pattern in PATTERNS:
            if pattern.search(line):
                relative = path.relative_to(root)
                findings.append(f"{relative}:{line_number}: potential secret material")
                break
        else:
            match = GENERIC_SECRET_ASSIGNMENT.search(line)
            if match and not _looks_like_placeholder(match.group("value")):
                relative = path.relative_to(root)
                findings.append(f"{relative}:{line_number}: potential secret assignment")
    return findings


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip("\"'").strip().lower()
    if normalized in PLACEHOLDER_VALUES:
        return True
    if normalized.startswith(("your_", "your-", "example_", "example-", "test_", "test-")):
        return True
    if normalized.startswith(("<", "${", "$", "{{")):
        return True
    return set(normalized) <= {"x", "0", "_", "-"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan repository text files for leaked secrets.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument(
        "--include-local-env",
        action="store_true",
        help="Include .env files. CI enables this automatically.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    include_local_env = args.include_local_env or os.getenv("CI") == "true"
    findings: list[str] = []
    for path in iter_files(root, include_local_env=include_local_env):
        findings.extend(scan_file(path, root))

    if findings:
        for finding in findings:
            print(finding)
        print("Potential secret material found.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
