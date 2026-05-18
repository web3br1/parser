from worker_sync import reenqueue


def test_reenqueue_ignores_empty_queue(monkeypatch) -> None:
    monkeypatch.setattr(reenqueue.db, "get_queued_jobs_for_reenqueue", lambda **kwargs: [])

    result = reenqueue.reenqueue_queued_jobs()

    assert result == {"scanned": 0, "dispatched": 0, "skipped": 0}


def test_reenqueue_dispatches_ingest(monkeypatch) -> None:
    dispatched: list[dict] = []

    monkeypatch.setattr(
        reenqueue.db,
        "get_queued_jobs_for_reenqueue",
        lambda **kwargs: [
            {
                "id": "job-1",
                "job_type": "ingest",
                "workspace_id": "workspace-1",
                "source_id": "source-1",
                "chunk_id": None,
                "metadata": {
                    "storage_path": "path.pdf",
                    "declared_mime": "application/pdf",
                    "file_hash": "hash",
                },
            }
        ],
    )
    monkeypatch.setattr(reenqueue, "_enqueue_ingest_source", lambda **kwargs: dispatched.append(kwargs))

    result = reenqueue.reenqueue_queued_jobs()

    assert result["dispatched"] == 1
    assert dispatched[0]["storage_path"] == "path.pdf"
