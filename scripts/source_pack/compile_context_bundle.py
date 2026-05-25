from __future__ import annotations

import argparse
import sys
from pathlib import Path

from source_pack.compiler import compile_source_pack
from source_pack.writer import write_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile a normalized source pack into context_bundle.v1 JSON.",
    )
    parser.add_argument("source_dir", nargs="?", type=Path)
    parser.add_argument("--source-dir", dest="source_dir_flag", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    source_dir: Path = args.source_dir_flag or args.source_dir
    if source_dir is None:
        parser.error("source_dir is required (positional or --source-dir)")
    output: Path = args.output or (
        source_dir / f"{source_dir.name}.context_bundle.v1.json"
    )
    bundle = compile_source_pack(source_dir)
    result = write_bundle(bundle, output, check=args.check)
    if args.check and result.changed:
        print(f"stale context bundle: {output}", file=sys.stderr)
        return 1
    print(
        f"{bundle.schema_version} {bundle.integrity.bundle_hash} "
        f"sources={bundle.integrity.source_count} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
