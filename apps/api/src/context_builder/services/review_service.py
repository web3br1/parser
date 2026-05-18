from __future__ import annotations

import re
from typing import Any, cast

from fastapi import HTTPException
from normalizers.pre_extract import pre_normalize
from observability.events import agent_event
from observability.logging import get_logger
from schema_registry.validators import validate_extraction

from supabase import Client

logger = get_logger("api")
AGENT = "review-agent"
STAGE = "review"

_RULE_TYPES = frozenset({"discount_rule", "cancellation_policy"})
_FACT_TYPES = frozenset({
    "service_price", "business_hours", "payment_method",
    "contact_info", "faq_item",
})


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


def _rpc_exception_to_http(exc: Exception) -> HTTPException:
    msg = str(exc)
    if "has_open_contradiction" in msg:
        match = re.search(r"([a-z_]+_has_open_contradiction)", msg)
        code = match.group(1) if match else "has_open_contradiction"
        return HTTPException(status_code=409, detail={"code": code})
    if "not_found" in msg:
        return HTTPException(status_code=404, detail=msg.split(":")[-1].strip())
    if "permission_denied" in msg:
        return HTTPException(status_code=403, detail="permission_denied")
    if "already_superseded" in msg:
        return HTTPException(status_code=409, detail={"code": "already_superseded"})
    if "invalid_" in msg:
        match = re.search(r"(invalid_[a-z_]+)", msg)
        code = match.group(1) if match else "invalid_transition"
        return HTTPException(status_code=409, detail={"code": code, "detail": msg})
    return HTTPException(status_code=500, detail="rpc_error")


def _emit_review_event(
    action: str,
    *,
    workspace_id: str,
    resource_type: str,
    resource_id: str,
    actor_user_id: str | None,
    outcome: str,
    previous_resource_id: str | None = None,
) -> None:
    fields: dict[str, Any] = {
        "workspace_id": workspace_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
    }
    if actor_user_id:
        fields["actor_user_id"] = actor_user_id
    if previous_resource_id:
        fields["previous_resource_id"] = previous_resource_id
    event, event_fields = agent_event(
        AGENT,
        STAGE,
        action,
        outcome,
        **fields,
    )
    logger.info(event, **event_fields)


def _validate_rule_edit(
    rule_type: str,
    condition: dict[str, Any],
    action: dict[str, Any],
) -> None:
    if rule_type == "discount_rule":
        raw: dict[str, Any] = {"condition": condition, "action": action}
    elif rule_type == "cancellation_policy":
        raw = {**condition, **action}
    else:
        raw = {**condition, **action}

    vr = validate_extraction(rule_type, raw)
    if not vr.valid:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "rule_type": rule_type, "errors": vr.errors[:5]},
        )


# ── Review queue ─────────────────────────────────────────────────────────────

def get_review_queue(
    db: Client,
    *,
    workspace_id: str,
    page: int,
    per_page: int,
    fact_type: str | None = None,
    source_id: str | None = None,
) -> dict[str, Any]:
    pending_statuses = ["extracted", "needs_review"]
    offset = (page - 1) * per_page
    end = offset + per_page - 1

    facts_q = (
        cast(Any, db.table("extracted_facts"))
        .select("chunk_id, fact_type, source_id, status, created_at", count="exact")
        .eq("workspace_id", workspace_id)
        .in_("status", pending_statuses)
        .order("created_at")
    )
    if fact_type:
        facts_q = facts_q.eq("fact_type", fact_type)
    if source_id:
        facts_q = facts_q.eq("source_id", source_id)
    if fact_type:
        facts_q = facts_q.range(offset, end)
    facts_result = facts_q.execute()
    pending_facts = _rows(facts_result.data)
    facts_count = getattr(facts_result, "count", None)

    pending_rules: list[dict[str, Any]] = []
    if not fact_type:
        rules_q = (
            cast(Any, db.table("business_rules"))
            .select("chunk_id, rule_type, source_id, status, created_at", count="exact")
            .eq("workspace_id", workspace_id)
            .in_("status", pending_statuses)
            .order("created_at")
        )
        if source_id:
            rules_q = rules_q.eq("source_id", source_id)
        pending_rules = _rows(rules_q.execute().data)

    seen: dict[str, Any] = {}
    for item in pending_facts + pending_rules:
        cid = item["chunk_id"]
        if cid not in seen:
            seen[cid] = item

    chunk_ids_all = list(seen.keys())
    total = int(facts_count) if fact_type and facts_count is not None else len(chunk_ids_all)
    pages = (total + per_page - 1) // per_page if total else 0

    if not chunk_ids_all:
        return {"items": [], "total": total, "page": page, "per_page": per_page, "pages": pages}

    page_chunk_ids = chunk_ids_all if fact_type else chunk_ids_all[offset : offset + per_page]

    chunks_result = (
        db.table("chunks")
        .select("id, source_id, chunk_index, content, created_at")
        .eq("workspace_id", workspace_id)
        .in_("id", page_chunk_ids)
        .execute()
    )
    chunks_by_id = {
        str(c["id"]): c
        for c in _rows(chunks_result.data)
        if c.get("id") is not None
    }

    source_ids = [
        str(source_id)
        for source_id in {c.get("source_id") for c in chunks_by_id.values()}
        if source_id is not None
    ]
    sources_by_id: dict[str, Any] = {}
    if source_ids:
        sources_result = (
            db.table("sources")
            .select("id, original_filename")
            .in_("id", source_ids)
            .execute()
        )
        sources_by_id = {
            str(s["id"]): s
            for s in _rows(sources_result.data)
            if s.get("id") is not None
        }

    all_facts_data = (
        db.table("extracted_facts")
        .select("id, chunk_id, status")
        .eq("workspace_id", workspace_id)
        .in_("chunk_id", page_chunk_ids)
        .execute()
        .data
    )
    all_facts = _rows(all_facts_data)
    all_rules_data = (
        db.table("business_rules")
        .select("id, chunk_id, status")
        .eq("workspace_id", workspace_id)
        .in_("chunk_id", page_chunk_ids)
        .execute()
        .data
    )
    all_rules = _rows(all_rules_data)
    unknowns_data = (
        db.table("unknown_facts_queue")
        .select("id, chunk_id")
        .eq("workspace_id", workspace_id)
        .in_("chunk_id", page_chunk_ids)
        .eq("status", "open")
        .execute()
        .data
    )
    unknowns = _rows(unknowns_data)

    def _count_by_chunk(rows: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            cid = row.get("chunk_id")
            if cid is not None:
                key = str(cid)
                counts[key] = counts.get(key, 0) + 1
        return counts

    facts_total_by_chunk = _count_by_chunk(all_facts)
    rules_total_by_chunk = _count_by_chunk(all_rules)
    unknown_total_by_chunk = _count_by_chunk(unknowns)
    pending_facts_by_chunk = _count_by_chunk([
        f for f in all_facts if f.get("status") in pending_statuses
    ])
    pending_rules_by_chunk = _count_by_chunk([
        r for r in all_rules if r.get("status") in pending_statuses
    ])

    items = []
    for cid in page_chunk_ids:
        chunk = chunks_by_id.get(cid)
        if not chunk:
            continue

        source = sources_by_id.get(str(chunk.get("source_id"))) or {}
        content: str = chunk.get("content") or ""

        items.append({
            "chunk_id": cid,
            "source_id": chunk.get("source_id"),
            "source_name": source.get("original_filename") or "",
            "chunk_index": chunk.get("chunk_index", 0),
            "content_preview": content[:200],
            "facts_total": facts_total_by_chunk.get(cid, 0),
            "facts_pending": pending_facts_by_chunk.get(cid, 0),
            "rules_total": rules_total_by_chunk.get(cid, 0),
            "rules_pending": pending_rules_by_chunk.get(cid, 0),
            "unknown_total": unknown_total_by_chunk.get(cid, 0),
            "has_ambiguities": False,
            "created_at": chunk.get("created_at"),
        })

    return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": pages}


def get_chunk_detail(
    db: Client,
    *,
    workspace_id: str,
    chunk_id: str,
) -> dict[str, Any]:
    chunk_result = cast(Any, (
        db.table("chunks")
        .select("id, source_id, chunk_index, content")
        .eq("id", chunk_id)
        .eq("workspace_id", workspace_id)
        .maybe_single()
        .execute()
    ))
    chunk = _row(chunk_result.data)
    if not chunk:
        raise HTTPException(status_code=404, detail="chunk_not_found")

    source_result = cast(Any, (
        db.table("sources")
        .select("original_filename")
        .eq("id", chunk["source_id"])
        .maybe_single()
        .execute()
    ))
    source_row = _row(source_result.data) or {}
    source_name: str = source_row.get("original_filename") or ""

    facts_result = (
        db.table("extracted_facts")
        .select(
            "id, fact_type, schema_version, content, normalized_content, status, "
            "confidence, model_name, prompt_version, reviewed_by, reviewed_at, "
            "supersedes, superseded_by, created_at, "
            "evidence_spans(id, quote, char_start, char_end, page_number, sheet_name, row_number)"
        )
        .eq("chunk_id", chunk_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )
    facts_raw = _rows(facts_result.data)

    rules_result = (
        db.table("business_rules")
        .select(
            "id, rule_type, schema_version, condition, action, status, "
            "confidence, model_name, prompt_version, reviewed_by, reviewed_at, "
            "supersedes, superseded_by, created_at, "
            "evidence_spans(id, quote, char_start, char_end, page_number, sheet_name, row_number)"
        )
        .eq("chunk_id", chunk_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )
    rules_raw = _rows(rules_result.data)

    def _extract_evidence(row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        ev = row.pop("evidence_spans", None)
        if isinstance(ev, list) and ev:
            ev = ev[0]
        elif not isinstance(ev, dict):
            ev = None
        row["evidence_span"] = ev
        return row

    return {
        "chunk_id": chunk_id,
        "source_id": chunk["source_id"],
        "source_name": source_name,
        "chunk_index": chunk.get("chunk_index", 0),
        "content": chunk.get("content") or "",
        "facts": [_extract_evidence(f) for f in facts_raw],
        "rules": [_extract_evidence(r) for r in rules_raw],
    }


# ── Approve ──────────────────────────────────────────────────────────────────

def approve_fact(
    db: Client,
    *,
    workspace_id: str,
    fact_id: str,
    actor_user_id: str,
    note: str | None,
) -> dict[str, Any]:
    result = cast(Any, (
        db.table("extracted_facts")
        .select("id, workspace_id, status")
        .eq("id", fact_id)
        .maybe_single()
        .execute()
    ))
    fact = _row(result.data)
    if not fact:
        raise HTTPException(status_code=404, detail="extracted_fact_not_found")
    if fact["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="extracted_fact_not_found")

    if fact["status"] == "approved":
        _emit_review_event(
            "approve",
            workspace_id=workspace_id,
            resource_type="extracted_fact",
            resource_id=fact_id,
            actor_user_id=actor_user_id,
            outcome="skipped",
        )
        return {"status": "approved", "resource_id": fact_id, "resource_type": "extracted_fact"}

    try:
        db.rpc(
            "approve_fact",
            {"target_fact_id": fact_id, "reason": note, "actor_user_id": actor_user_id},
        ).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    _emit_review_event(
        "approve",
        workspace_id=workspace_id,
        resource_type="extracted_fact",
        resource_id=fact_id,
        actor_user_id=actor_user_id,
        outcome="succeeded",
    )
    return {"status": "approved", "resource_id": fact_id, "resource_type": "extracted_fact"}


def approve_rule(
    db: Client,
    *,
    workspace_id: str,
    rule_id: str,
    actor_user_id: str,
    note: str | None,
) -> dict[str, Any]:
    result = cast(Any, (
        db.table("business_rules")
        .select("id, workspace_id, status")
        .eq("id", rule_id)
        .maybe_single()
        .execute()
    ))
    rule = _row(result.data)
    if not rule:
        raise HTTPException(status_code=404, detail="business_rule_not_found")
    if rule["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="business_rule_not_found")

    if rule["status"] == "approved":
        _emit_review_event(
            "approve",
            workspace_id=workspace_id,
            resource_type="business_rule",
            resource_id=rule_id,
            actor_user_id=actor_user_id,
            outcome="skipped",
        )
        return {"status": "approved", "resource_id": rule_id, "resource_type": "business_rule"}

    try:
        db.rpc(
            "approve_rule",
            {"target_rule_id": rule_id, "reason": note, "actor_user_id": actor_user_id},
        ).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    _emit_review_event(
        "approve",
        workspace_id=workspace_id,
        resource_type="business_rule",
        resource_id=rule_id,
        actor_user_id=actor_user_id,
        outcome="succeeded",
    )
    return {"status": "approved", "resource_id": rule_id, "resource_type": "business_rule"}


# ── Reject ───────────────────────────────────────────────────────────────────

def reject_fact(
    db: Client,
    *,
    workspace_id: str,
    fact_id: str,
    actor_user_id: str,
    reason: str,
    note: str | None,
) -> dict[str, Any]:
    result = cast(Any, (
        db.table("extracted_facts")
        .select("id, workspace_id, status")
        .eq("id", fact_id)
        .maybe_single()
        .execute()
    ))
    fact = _row(result.data)
    if not fact or fact["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="extracted_fact_not_found")

    combined_reason = reason + (f" | {note}" if note else "")
    try:
        db.rpc(
            "reject_fact",
            {
                "target_fact_id": fact_id,
                "reason": combined_reason,
                "actor_user_id": actor_user_id,
            },
        ).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    _emit_review_event(
        "reject",
        workspace_id=workspace_id,
        resource_type="extracted_fact",
        resource_id=fact_id,
        actor_user_id=actor_user_id,
        outcome="succeeded",
    )
    return {"status": "rejected", "resource_id": fact_id, "resource_type": "extracted_fact"}


def reject_rule(
    db: Client,
    *,
    workspace_id: str,
    rule_id: str,
    actor_user_id: str,
    reason: str,
    note: str | None,
) -> dict[str, Any]:
    result = cast(Any, (
        db.table("business_rules")
        .select("id, workspace_id, status")
        .eq("id", rule_id)
        .maybe_single()
        .execute()
    ))
    rule = _row(result.data)
    if not rule or rule["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="business_rule_not_found")

    combined_reason = reason + (f" | {note}" if note else "")
    try:
        db.rpc(
            "reject_rule",
            {
                "target_rule_id": rule_id,
                "reason": combined_reason,
                "actor_user_id": actor_user_id,
            },
        ).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    _emit_review_event(
        "reject",
        workspace_id=workspace_id,
        resource_type="business_rule",
        resource_id=rule_id,
        actor_user_id=actor_user_id,
        outcome="succeeded",
    )
    return {"status": "rejected", "resource_id": rule_id, "resource_type": "business_rule"}


# ── Edit (nova versão) ────────────────────────────────────────────────────────

def edit_fact(
    db: Client,
    *,
    workspace_id: str,
    fact_id: str,
    actor_user_id: str,
    new_content: dict[str, Any],
    note: str | None,
) -> dict[str, Any]:
    result = cast(Any, (
        db.table("extracted_facts")
        .select("id, workspace_id, fact_type")
        .eq("id", fact_id)
        .maybe_single()
        .execute()
    ))
    fact = _row(result.data)
    if not fact or fact["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="extracted_fact_not_found")

    fact_type = str(fact["fact_type"])
    normalized = pre_normalize(fact_type, new_content)
    vr = validate_extraction(fact_type, normalized)
    if not vr.valid:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "fact_type": fact_type, "errors": vr.errors[:5]},
        )

    try:
        rpc_result = db.rpc("create_fact_version", {
            "old_fact_id": fact_id,
            "new_content": new_content,
            "new_normalized_content": normalized,
            "reason": note,
            "actor_user_id": actor_user_id,
        }).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    new_fact_id = str(rpc_result.data)
    _emit_review_event(
        "edit",
        workspace_id=workspace_id,
        resource_type="extracted_fact",
        resource_id=new_fact_id,
        actor_user_id=actor_user_id,
        outcome="succeeded",
        previous_resource_id=fact_id,
    )
    return {"status": "superseded", "resource_id": new_fact_id, "resource_type": "extracted_fact"}


def edit_rule(
    db: Client,
    *,
    workspace_id: str,
    rule_id: str,
    actor_user_id: str,
    new_condition: dict[str, Any],
    new_action: dict[str, Any],
    note: str | None,
) -> dict[str, Any]:
    result = cast(Any, (
        db.table("business_rules")
        .select("id, workspace_id, rule_type")
        .eq("id", rule_id)
        .maybe_single()
        .execute()
    ))
    rule = _row(result.data)
    if not rule or rule["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="business_rule_not_found")

    rule_type = str(rule["rule_type"])
    _validate_rule_edit(rule_type, new_condition, new_action)

    try:
        rpc_result = db.rpc("create_rule_version", {
            "old_rule_id": rule_id,
            "new_condition": new_condition,
            "new_action": new_action,
            "reason": note,
            "actor_user_id": actor_user_id,
        }).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    new_rule_id = str(rpc_result.data)
    _emit_review_event(
        "edit",
        workspace_id=workspace_id,
        resource_type="business_rule",
        resource_id=new_rule_id,
        actor_user_id=actor_user_id,
        outcome="succeeded",
        previous_resource_id=rule_id,
    )
    return {"status": "superseded", "resource_id": new_rule_id, "resource_type": "business_rule"}


def publish_fact(
    db: Client,
    *,
    workspace_id: str,
    fact_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    result = cast(Any, (
        db.table("extracted_facts")
        .select("id, workspace_id, status")
        .eq("id", fact_id)
        .maybe_single()
        .execute()
    ))
    fact = _row(result.data)
    if not fact or fact["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="extracted_fact_not_found")

    if fact["status"] == "published":
        _emit_review_event(
            "publish",
            workspace_id=workspace_id,
            resource_type="extracted_fact",
            resource_id=fact_id,
            actor_user_id=actor_user_id,
            outcome="skipped",
        )
        return {"status": "published", "resource_id": fact_id, "resource_type": "extracted_fact"}

    try:
        db.rpc(
            "publish_fact",
            {"target_fact_id": fact_id, "actor_user_id": actor_user_id},
        ).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    _emit_review_event(
        "publish",
        workspace_id=workspace_id,
        resource_type="extracted_fact",
        resource_id=fact_id,
        actor_user_id=actor_user_id,
        outcome="succeeded",
    )
    return {"status": "published", "resource_id": fact_id, "resource_type": "extracted_fact"}


def publish_rule(
    db: Client,
    *,
    workspace_id: str,
    rule_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    result = cast(Any, (
        db.table("business_rules")
        .select("id, workspace_id, status")
        .eq("id", rule_id)
        .maybe_single()
        .execute()
    ))
    rule = _row(result.data)
    if not rule or rule["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="business_rule_not_found")

    if rule["status"] == "published":
        _emit_review_event(
            "publish",
            workspace_id=workspace_id,
            resource_type="business_rule",
            resource_id=rule_id,
            actor_user_id=actor_user_id,
            outcome="skipped",
        )
        return {"status": "published", "resource_id": rule_id, "resource_type": "business_rule"}

    try:
        db.rpc(
            "publish_rule",
            {"target_rule_id": rule_id, "actor_user_id": actor_user_id},
        ).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    _emit_review_event(
        "publish",
        workspace_id=workspace_id,
        resource_type="business_rule",
        resource_id=rule_id,
        actor_user_id=actor_user_id,
        outcome="succeeded",
    )
    return {"status": "published", "resource_id": rule_id, "resource_type": "business_rule"}
