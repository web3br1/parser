from __future__ import annotations

from typing import Any, cast

from supabase import Client


def _count_from_result(result: Any, rows: list[dict[str, Any]]) -> int:
    count = getattr(result, "count", None)
    return int(count) if count is not None else len(rows)


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def list_published_records(
    db: Client,
    *,
    workspace_id: str,
    record_type: str = "all",
    kind_filter: str | None = None,
    source_id: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> dict[str, Any]:
    offset = (page - 1) * per_page
    end = offset + per_page - 1
    facts: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []
    facts_count = 0
    rules_count = 0

    if record_type in ("all", "facts"):
        q = (
            cast(Any, db.table("published_facts"))
            .select(
                "id, fact_type, schema_version, normalized_content, confidence, "
                "source_id, chunk_id, published_at, reviewed_by",
                count="exact",
            )
            .eq("workspace_id", workspace_id)
            .order("published_at", desc=True)
        )
        if kind_filter:
            q = q.eq("fact_type", kind_filter)
        if source_id:
            q = q.eq("source_id", source_id)
        if record_type == "facts":
            q = q.range(offset, end)
        else:
            q = q.range(0, end)
        result = q.execute()
        facts = _rows(result.data)
        facts_count = _count_from_result(result, facts)

    if record_type in ("all", "rules"):
        q = (
            cast(Any, db.table("published_rules"))
            .select(
                "id, rule_type, schema_version, condition, action, priority, "
                "confidence, source_id, chunk_id, published_at, reviewed_by",
                count="exact",
            )
            .eq("workspace_id", workspace_id)
            .order("published_at", desc=True)
        )
        if kind_filter:
            q = q.eq("rule_type", kind_filter)
        if source_id:
            q = q.eq("source_id", source_id)
        if record_type == "rules":
            q = q.range(offset, end)
        else:
            q = q.range(0, end)
        result = q.execute()
        rules = _rows(result.data)
        rules_count = _count_from_result(result, rules)

    items: list[dict[str, Any]] = (
        [{"kind": "fact", **f} for f in facts]
        + [{"kind": "rule", **r} for r in rules]
    )
    items.sort(key=lambda x: x.get("published_at") or "", reverse=True)

    total = facts_count + rules_count
    page_items = items if record_type != "all" else items[offset : offset + per_page]
    pages = (total + per_page - 1) // per_page if total else 0

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "facts_count": facts_count,
        "rules_count": rules_count,
    }
