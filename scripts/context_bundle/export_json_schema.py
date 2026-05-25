from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from context_builder.schemas.context_bundle import ContextBundleResponse

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_PATH = ROOT / "examples" / "context_bundle" / "context-bundle.v1.schema.json"
JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID = "https://context-builder.local/schemas/context-bundle.v1.schema.json"


def build_schema() -> dict[str, Any]:
    raw_schema = ContextBundleResponse.model_json_schema(mode="serialization")
    raw_schema.pop("title", None)
    raw_schema["required"] = list(raw_schema["properties"])
    return {
        "$schema": JSON_SCHEMA_DRAFT,
        "$id": SCHEMA_ID,
        "title": "context_bundle.v1",
        "description": (
            "Shared contract for transferring compiled, reviewed context from "
            "the Parser upstream project into a runtime chatbot/importer."
        ),
        **raw_schema,
    }


def render_schema() -> str:
    return json.dumps(build_schema(), indent=2) + "\n"


def write_or_check_schema(*, output_path: Path, check: bool) -> bool:
    expected = render_schema()

    if check:
        if not output_path.exists():
            print(f"Missing schema: {_display_path(output_path)}", file=sys.stderr)
            return False
        current = _normalize_newlines(output_path.read_text(encoding="utf-8"))
        if current != expected:
            print(f"Schema drift detected: {_display_path(output_path)}", file=sys.stderr)
            return False
        print(f"Schema is current: {_display_path(output_path)}")
        return True

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(expected, encoding="utf-8")
    print(f"Wrote schema: {_display_path(output_path)}")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or check the context_bundle.v1 JSON Schema artifact.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help="Destination JSON Schema path.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated schema differs from the committed artifact.",
    )
    args = parser.parse_args(argv)

    return 0 if write_or_check_schema(output_path=args.output_path, check=args.check) else 1


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


if __name__ == "__main__":
    raise SystemExit(main())
