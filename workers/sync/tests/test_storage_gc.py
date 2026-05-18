from datetime import UTC, datetime, timedelta

from worker_sync import storage_gc


def test_storage_gc_dry_run_does_not_delete(monkeypatch) -> None:
    deleted: list[list[str]] = []
    old = (datetime.now(UTC) - timedelta(hours=25)).isoformat()

    monkeypatch.setattr(storage_gc.db, "get_source_paths", lambda: set())
    monkeypatch.setattr(
        storage_gc.db,
        "list_storage_objects",
        lambda prefix: [{"name": "orphan.pdf", "updated_at": old}],
    )
    monkeypatch.setattr(
        storage_gc.db,
        "delete_storage_objects",
        lambda paths: deleted.append(paths),
    )

    result = storage_gc.collect_orphan_storage_objects(dry_run=True)

    assert result["orphans"] == 1
    assert result["deleted"] == 0
    assert deleted == []


def test_storage_gc_deletes_old_orphans(monkeypatch) -> None:
    deleted: list[list[str]] = []
    old = (datetime.now(UTC) - timedelta(hours=25)).isoformat()

    monkeypatch.setattr(storage_gc.db, "get_source_paths", lambda: {"workspaces/kept.pdf"})
    monkeypatch.setattr(
        storage_gc.db,
        "list_storage_objects",
        lambda prefix: [
            {"name": "kept.pdf", "updated_at": old},
            {"name": "orphan.pdf", "updated_at": old},
        ],
    )
    monkeypatch.setattr(
        storage_gc.db,
        "delete_storage_objects",
        lambda paths: deleted.append(paths),
    )

    result = storage_gc.collect_orphan_storage_objects(dry_run=False)

    assert result["deleted"] == 1
    assert deleted == [["workspaces/orphan.pdf"]]


def test_privacy_storage_gc_deletes_soft_deleted_source_objects(monkeypatch) -> None:
    deleted: list[list[str]] = []
    monkeypatch.setattr(
        storage_gc.db,
        "get_deleted_source_paths",
        lambda older_than_hours: {
            "workspaces/ws_1/sources/source_1/original.pdf",
            "workspaces/ws_1/sources/source_2/original.pdf",
        },
    )
    monkeypatch.setattr(
        storage_gc.db,
        "delete_storage_objects",
        lambda paths: deleted.append(paths),
    )

    result = storage_gc.collect_privacy_deleted_storage_objects(
        older_than_hours=1,
        dry_run=False,
    )

    assert result["scanned"] == 2
    assert result["deleted"] == 2
    assert deleted == [[
        "workspaces/ws_1/sources/source_1/original.pdf",
        "workspaces/ws_1/sources/source_2/original.pdf",
    ]]


def test_privacy_storage_gc_dry_run_keeps_soft_deleted_source_objects(monkeypatch) -> None:
    deleted: list[list[str]] = []
    monkeypatch.setattr(
        storage_gc.db,
        "get_deleted_source_paths",
        lambda older_than_hours: {"workspaces/ws_1/sources/source_1/original.pdf"},
    )
    monkeypatch.setattr(storage_gc.db, "delete_storage_objects", lambda paths: deleted.append(paths))

    result = storage_gc.collect_privacy_deleted_storage_objects(dry_run=True)

    assert result["deleted"] == 0
    assert result["paths"] == ["workspaces/ws_1/sources/source_1/original.pdf"]
    assert deleted == []


def test_retention_dry_run_report_has_lgpd_shape(monkeypatch) -> None:
    monkeypatch.setattr(storage_gc.db, "count_sources_for_retention", lambda workspace_id: 2)
    monkeypatch.setattr(storage_gc.db, "count_storage_objects_for_retention", lambda workspace_id: 3)
    monkeypatch.setattr(storage_gc.db, "count_audit_rows_for_anonymization", lambda workspace_id: 4)

    result = storage_gc.build_retention_dry_run_report(workspace_id="ws_1")

    assert result == {
        "workspace_id": "ws_1",
        "sources_to_delete": 2,
        "storage_objects_to_delete": 3,
        "audit_rows_to_anonymize": 4,
    }
