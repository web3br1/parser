from hashlib import sha256

from worker_classification import extraction_queue


def test_enqueue_extraction_job_uses_db_outbox_contract(monkeypatch) -> None:
    calls: list[dict] = []

    monkeypatch.setenv("EXTRACTION_MODEL", "extract-model")
    monkeypatch.setattr(
        extraction_queue,
        "get_extraction_prompt_version",
        lambda fact_type: f"{fact_type}-prompt",
    )
    monkeypatch.setattr(
        extraction_queue.db,
        "insert_extraction_job",
        lambda **kwargs: calls.append(kwargs) or "job-123",
    )

    job_id = extraction_queue.enqueue_extraction_job(
        chunk_id="chunk-1",
        workspace_id="workspace-1",
        source_id="source-1",
        fact_type="service_price",
        destination="extracted_facts",
        confidence=0.91,
        prompt_version="classification-prompt",
        model_name="classification-model",
    )

    expected_key = sha256(
        b"extraction:chunk-1:service_price:service_price-prompt:extract-model"
    ).hexdigest()

    assert job_id == "job-123"
    assert calls == [
        {
            "workspace_id": "workspace-1",
            "source_id": "source-1",
            "chunk_id": "chunk-1",
            "idempotency_key": expected_key,
            "metadata": {
                "fact_type": "service_price",
                "destination": "extracted_facts",
                "classification_confidence": 0.91,
                "classification_prompt_version": "classification-prompt",
                "classification_model": "classification-model",
                "extraction_prompt_version": "service_price-prompt",
                "extraction_model": "extract-model",
                "request_id": None,
            },
        }
    ]
