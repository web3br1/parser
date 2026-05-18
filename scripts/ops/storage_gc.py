from __future__ import annotations

import argparse
import json

from worker_sync.storage_gc import (
    collect_orphan_storage_objects,
    collect_privacy_deleted_storage_objects,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run storage garbage collection.")
    parser.add_argument(
        "--mode",
        choices=["privacy-deleted", "orphans"],
        default="privacy-deleted",
        help="privacy-deleted removes objects from soft-deleted sources; orphans removes unreferenced old objects.",
    )
    parser.add_argument("--apply", action="store_true", help="Delete objects. Default is dry-run.")
    parser.add_argument("--prefix", default="workspaces", help="Storage prefix for orphan scans.")
    parser.add_argument("--older-than-hours", type=int, default=24)
    args = parser.parse_args()

    if args.mode == "privacy-deleted":
        report = collect_privacy_deleted_storage_objects(
            older_than_hours=args.older_than_hours,
            dry_run=not args.apply,
        )
    else:
        report = collect_orphan_storage_objects(
            prefix=args.prefix,
            older_than_hours=args.older_than_hours,
            dry_run=not args.apply,
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
