from uuid import uuid4

from domain.models import (
    ContextBuildMode,
    ContextBuildRecommendedAction,
    ContextBuildRun,
    ContextBuildStatus,
)


def test_context_build_run_create_sets_initial_domain_state() -> None:
    run_id = uuid4()
    workspace_id = uuid4()
    actor_user_id = uuid4()

    run = ContextBuildRun.create(
        id=run_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        input_mode=ContextBuildMode.SINGLE_DOCUMENT,
        input_fingerprint="single-document:v1",
        input_hash=None,
    )

    assert run.id == run_id
    assert run.workspace_id == workspace_id
    assert run.actor_user_id == actor_user_id
    assert run.input_mode is ContextBuildMode.SINGLE_DOCUMENT
    assert run.input_fingerprint == "single-document:v1"
    assert run.input_hash is None
    assert run.status is ContextBuildStatus.CREATED
    assert run.recommended_action is None


def test_mark_preflighted_returns_new_run_with_recommended_action() -> None:
    run = ContextBuildRun.create(
        id=uuid4(),
        workspace_id=uuid4(),
        actor_user_id=uuid4(),
        input_mode=ContextBuildMode.SOURCE_PACK,
        input_fingerprint="source-pack:v1",
        input_hash="sha256:source-input",
    )

    preflighted = run.mark_preflighted(
        recommended_action=ContextBuildRecommendedAction.COMPILE_AS_SOURCE_PACK
    )

    assert preflighted is not run
    assert run.status is ContextBuildStatus.CREATED
    assert preflighted.status is ContextBuildStatus.PREFLIGHTED
    assert (
        preflighted.recommended_action
        is ContextBuildRecommendedAction.COMPILE_AS_SOURCE_PACK
    )


def test_context_build_run_minimal_lifecycle_transitions() -> None:
    run = ContextBuildRun.create(
        id=uuid4(),
        workspace_id=uuid4(),
        actor_user_id=uuid4(),
        input_mode=ContextBuildMode.MULTI_DOCUMENT_BATCH,
        input_fingerprint="multi-document-batch:v1",
        input_hash="sha256:manual-input",
    )

    queued = run.mark_queued()
    processing = queued.mark_processing()
    compiled = processing.mark_compiled(
        bundle_hash="sha256:bundle",
        context_version="ctx-2026-05-26",
        readiness_status="ready",
    )

    assert queued.status is ContextBuildStatus.QUEUED
    assert processing.status is ContextBuildStatus.PROCESSING
    assert compiled.status is ContextBuildStatus.COMPILED
    assert compiled.bundle_hash == "sha256:bundle"
    assert compiled.context_version == "ctx-2026-05-26"
    assert compiled.readiness_status == "ready"


def test_mark_failed_records_error() -> None:
    run = ContextBuildRun.create(
        id=uuid4(),
        workspace_id=uuid4(),
        actor_user_id=uuid4(),
        input_mode=ContextBuildMode.SINGLE_DOCUMENT,
        input_fingerprint="single-document:v2",
    )

    failed = run.mark_failed(error="preflight failed")

    assert failed.status is ContextBuildStatus.FAILED
    assert failed.error == "preflight failed"
