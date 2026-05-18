from __future__ import annotations

from typing import Any

from context_builder.services.query_redaction import context_row
from context_builder.services.query_response_builder import estimate_json_tokens


def fit_budget(
    rows: list[dict[str, Any]],
    *,
    budget_tokens: int,
    user_role: str,
) -> tuple[list[dict[str, Any]], int]:
    selected: list[dict[str, Any]] = []
    current_tokens = 0
    for row in rows:
        visible = context_row(row, user_role=user_role)
        row_tokens = estimate_json_tokens(visible)
        if current_tokens + row_tokens > budget_tokens:
            continue
        selected.append(visible)
        current_tokens += row_tokens
    return selected, current_tokens
