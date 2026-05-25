from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from context_builder.schemas.context_bundle import ContextBundleResponse


@dataclass(frozen=True)
class WriteResult:
    path: Path
    changed: bool
    checked: bool


def bundle_json(bundle: ContextBundleResponse) -> str:
    return json.dumps(
        bundle.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def write_bundle(
    bundle: ContextBundleResponse,
    output_path: Path,
    *,
    check: bool = False,
) -> WriteResult:
    rendered = bundle_json(bundle)
    existing = output_path.read_text(encoding="utf-8") if output_path.exists() else None
    changed = existing != rendered
    if not check:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8", newline="\n")
    return WriteResult(path=output_path, changed=changed, checked=check)
