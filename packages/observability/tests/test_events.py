from __future__ import annotations

from observability.events import agent_event
from observability.logging import get_logger


def test_agent_event_returns_dotted_event_name_and_fields() -> None:
    event, fields = agent_event(
        "Review",
        "Review",
        "Fact Approved",
        "Succeeded",
        workspace_id="workspace-1",
        source_id="source-1",
        chunk_id="chunk-1",
        job_id="job-1",
        request_id="request-1",
        workflow_id="workflow-1",
        resource_type="fact",
        resource_id="fact-1",
        reason="accepted",
        counts={"facts": 1},
    )

    assert event == "review.review.fact_approved.succeeded"
    assert fields == {
        "agent": "Review",
        "stage": "Review",
        "action": "Fact Approved",
        "outcome": "Succeeded",
        "workspace_id": "workspace-1",
        "source_id": "source-1",
        "chunk_id": "chunk-1",
        "job_id": "job-1",
        "request_id": "request-1",
        "workflow_id": "workflow-1",
        "resource_type": "fact",
        "resource_id": "fact-1",
        "reason": "accepted",
        "counts": {"facts": 1},
    }


def test_agent_event_normalizes_symbols_without_rejecting_values() -> None:
    event, fields = agent_event(
        " API Agent ",
        " Ingest/File ",
        "Enqueue+Upload",
        "Queued!",
        custom_field="kept",
    )

    assert event == "api_agent.ingest_file.enqueue_upload.queued_"
    assert fields["agent"] == " API Agent "
    assert fields["stage"] == " Ingest/File "
    assert fields["action"] == "Enqueue+Upload"
    assert fields["outcome"] == "Queued!"
    assert fields["custom_field"] == "kept"


def test_agent_event_is_easy_to_pass_to_json_logger(capsys) -> None:
    logger = get_logger("test-service")
    event, fields = agent_event("api", "ingest", "enqueue", "queued", job_id="job-1")

    logger.info(event, **fields)

    output = capsys.readouterr().out
    assert '"event": "api.ingest.enqueue.queued"' in output
    assert '"agent": "api"' in output
    assert '"job_id": "job-1"' in output


def test_agent_event_never_raises_for_bad_stringification() -> None:
    class BadString:
        def __str__(self) -> str:
            raise RuntimeError("boom")

    event, fields = agent_event(BadString(), "stage", "action", "outcome")

    assert event == "unknown.stage.action.outcome"
    assert fields["agent"] == "<unprintable>"
