from __future__ import annotations

from typing import Any, cast

from fastapi import HTTPException
from observability.events import agent_event
from observability.logging import get_logger

from supabase import Client

logger = get_logger("api")
AGENT = "review-agent"
STAGE = "unknown"

_MVP_FACT_TYPES = frozenset({
    "service_price", "business_hours", "payment_method",
    "contact_info", "faq_item", "discount_rule", "cancellation_policy",
})
_FACT_DESTINATION = "extracted_facts"
_RULE_DESTINATION = "business_rules"
_FACT_TYPES = frozenset({
    "service_price", "business_hours", "payment_method", "contact_info", "faq_item",
})
_RULE_TYPES = frozenset({"discount_rule", "cancellation_policy"})
_DESTINATIONS = frozenset({_FACT_DESTINATION, _RULE_DESTINATION})


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _row(data: Any) -> dict[str, Any] | None:
    if isinstance(data, dict):
        return data
    return None


def _rpc_unknown_exception_to_http(exc: Exception) -> HTTPException:
    msg = str(exc)
    if "not_found" in msg:
        return HTTPException(status_code=404, detail="unknown_item_not_found")
    if "permission_denied" in msg:
        return HTTPException(status_code=403, detail="permission_denied")
    if "already_mapped" in msg:
        return HTTPException(status_code=409, detail={"code": "already_mapped"})
    if "already_ignored" in msg:
        return HTTPException(status_code=409, detail={"code": "already_ignored"})
    return HTTPException(status_code=500, detail="rpc_error")


def _emit_unknown_event(
    action: str,
    *,
    workspace_id: str,
    resource_id: str,
    actor_user_id: str | None,
    outcome: str,
    job_id: str | None = None,
    fact_type: str | None = None,
    destination: str | None = None,
) -> None:
    fields: dict[str, Any] = {
        "workspace_id": workspace_id,
        "resource_type": "unknown_fact",
        "resource_id": resource_id,
        "item_id": resource_id,
    }
    if actor_user_id:
        fields["actor_user_id"] = actor_user_id
    if job_id:
        fields["job_id"] = job_id
    if fact_type:
        fields["fact_type"] = fact_type
    if destination:
        fields["destination"] = destination
    event, event_fields = agent_event(
        AGENT,
        STAGE,
        action,
        outcome,
        **fields,
    )
    logger.info(event, **event_fields)


def get_unknown_queue(
    db: Client,
    *,
    workspace_id: str,
    page: int,
    per_page: int,
    status_filter: str | None = None,
) -> dict[str, Any]:
    offset = (page - 1) * per_page
    end = offset + per_page - 1
    query = (
        cast(Any, db.table("unknown_facts_queue"))
        .select("*", count="exact")
        .eq("workspace_id", workspace_id)
        .order("created_at", desc=True)
    )
    if status_filter:
        query = query.eq("status", status_filter)

    result = query.range(offset, end).execute()
    page_items = _rows(result.data)
    count = getattr(result, "count", None)
    total = int(count) if count is not None else len(page_items)
    pages = (total + per_page - 1) // per_page if total > 0 else 0

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


def reclassify_unknown(
    db: Client,
    *,
    workspace_id: str,
    item_id: str,
    fact_type: str,
    destination: str,
    reviewer_id: str,
    note: str | None,
) -> dict[str, Any]:
    """
    Delega ao RPC reclassify_unknown_item (028_review_functions.sql).
    O RPC cria o processing_job + atualiza o item + insere validation_event atomicamente.
    Python só despacha o job para o Celery após o RPC confirmar.

    Se dispatch falhar: job permanece queued no DB, item está mapped, evento existe.
    O scheduler re-enfileira jobs queued — zero inconsistência.
    """
    if fact_type not in _MVP_FACT_TYPES:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_fact_type", "valid": sorted(_MVP_FACT_TYPES)},
        )
    if destination not in _DESTINATIONS:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_destination", "valid": sorted(_DESTINATIONS)},
        )
    expected_destination = (
        _FACT_DESTINATION if fact_type in _FACT_TYPES else _RULE_DESTINATION
    )
    if destination != expected_destination:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_destination_for_fact_type",
                "expected": expected_destination,
                "current": destination,
            },
        )

    result = cast(Any, (
        db.table("unknown_facts_queue")
        .select("id, workspace_id, chunk_id, source_id")
        .eq("id", item_id)
        .maybe_single()
        .execute()
    ))
    item = _row(result.data)
    if not item or item.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="unknown_item_not_found")

    try:
        rpc_result = db.rpc("reclassify_unknown_item", {
            "p_item_id":     item_id,
            "p_fact_type":   fact_type,
            "p_destination": destination,
            "p_chunk_id":    item["chunk_id"],
            "p_source_id":   item["source_id"],
            "p_confidence":  0.5,
            "p_reason":      note,
            "p_actor_user_id": reviewer_id,
        }).execute()
    except Exception as exc:
        raise _rpc_unknown_exception_to_http(exc) from exc

    job_id = str(rpc_result.data)

    # dispatch_extraction_job is a late import: worker package may not be installed
    # in all environments. The job is already queued in DB; dispatch is best-effort.
    try:
        from worker_classification.extraction_queue import dispatch_extraction_job  # noqa: PLC0415
        dispatch_extraction_job(job_id)
    except Exception:
        # If dispatch fails the job stays queued and the scheduler will retry.
        event, fields = agent_event(
            AGENT,
            STAGE,
            "dispatch",
            "skipped",
            workspace_id=workspace_id,
            resource_type="unknown_fact",
            resource_id=item_id,
            item_id=item_id,
            actor_user_id=reviewer_id,
            job_id=job_id,
            fact_type=fact_type,
            destination=destination,
        )
        logger.warning(
            event,
            **fields,
        )

    _emit_unknown_event(
        "reclassify",
        workspace_id=workspace_id,
        resource_id=item_id,
        actor_user_id=reviewer_id,
        outcome="succeeded",
        job_id=job_id,
        fact_type=fact_type,
        destination=destination,
    )
    return {"status": "mapped", "extraction_job_id": job_id}


def ignore_unknown(
    db: Client,
    *,
    workspace_id: str,
    item_id: str,
    reviewer_id: str,
    note: str | None,
) -> dict[str, Any]:
    """
    Delega ao RPC ignore_unknown_item (028_review_functions.sql).
    O RPC atualiza o item + insere validation_event atomicamente.
    Idempotente: já ignored → RPC retorna sem erro.
    """
    result = cast(Any, (
        db.table("unknown_facts_queue")
        .select("id, workspace_id")
        .eq("id", item_id)
        .maybe_single()
        .execute()
    ))
    item = _row(result.data)
    if not item or item.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="unknown_item_not_found")

    try:
        db.rpc("ignore_unknown_item", {
            "p_item_id": item_id,
            "p_reason":  note,
            "p_actor_user_id": reviewer_id,
        }).execute()
    except Exception as exc:
        raise _rpc_unknown_exception_to_http(exc) from exc

    _emit_unknown_event(
        "ignore",
        workspace_id=workspace_id,
        resource_id=item_id,
        actor_user_id=reviewer_id,
        outcome="succeeded",
    )
    return {"status": "ignored"}
