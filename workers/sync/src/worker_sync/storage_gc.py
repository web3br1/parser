from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from worker_sync import db
from worker_sync.logging import logger


def collect_orphan_storage_objects(
    *,
    prefix: str = "workspaces",
    older_than_hours: int = 24,
    dry_run: bool = True,
) -> dict[str, Any]:
    logger.info("storage_gc_started", dry_run=dry_run)
    referenced_paths = db.get_source_paths()
    objects = db.list_storage_objects(prefix)
    cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
    orphan_paths = [
        path
        for path, updated_at in (_object_path_and_updated_at(prefix, item) for item in objects)
        if path is not None
        and path not in referenced_paths
        and (updated_at is None or updated_at < cutoff)
    ]

    if not dry_run:
        db.delete_storage_objects(orphan_paths)

    result = {
        "dry_run": dry_run,
        "scanned": len(objects),
        "orphans": len(orphan_paths),
        "deleted": 0 if dry_run else len(orphan_paths),
        "paths": orphan_paths,
    }
    logger.info(
        "storage_gc_finished",
        dry_run=dry_run,
        scanned=len(objects),
        orphans=len(orphan_paths),
        deleted=0 if dry_run else len(orphan_paths),
    )
    return result


def collect_privacy_deleted_storage_objects(
    *,
    older_than_hours: int = 0,
    dry_run: bool = True,
) -> dict[str, Any]:
    logger.info("privacy_storage_gc_started", dry_run=dry_run)
    deleted_source_paths = sorted(db.get_deleted_source_paths(older_than_hours=older_than_hours))

    if not dry_run:
        db.delete_storage_objects(deleted_source_paths)

    result = {
        "dry_run": dry_run,
        "scanned": len(deleted_source_paths),
        "deleted": 0 if dry_run else len(deleted_source_paths),
        "paths": deleted_source_paths,
    }
    logger.info(
        "privacy_storage_gc_finished",
        dry_run=dry_run,
        scanned=len(deleted_source_paths),
        deleted=0 if dry_run else len(deleted_source_paths),
    )
    return result


def build_retention_dry_run_report(*, workspace_id: str) -> dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "sources_to_delete": db.count_sources_for_retention(workspace_id),
        "storage_objects_to_delete": db.count_storage_objects_for_retention(workspace_id),
        "audit_rows_to_anonymize": db.count_audit_rows_for_anonymization(workspace_id),
    }


def _object_path_and_updated_at(
    prefix: str,
    item: dict[str, Any],
) -> tuple[str | None, datetime | None]:
    name = item.get("name")
    if not name:
        return None, None
    path = f"{prefix.rstrip('/')}/{name}"
    updated = item.get("updated_at") or item.get("created_at")
    if not updated:
        return path, None
    try:
        return path, datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
    except ValueError:
        return path, None
