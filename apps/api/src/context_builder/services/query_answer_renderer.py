from __future__ import annotations

from typing import Any


def render_fact(row: dict[str, Any]) -> str:
    content = row.get("content")
    if isinstance(content, dict):
        service = content.get("service") or content.get("service_name") or content.get("name")
        price = content.get("price") or content.get("price_amount")
        if service and price:
            return f"{service}: {price}"
        if content:
            return ", ".join(f"{key}: {value}" for key, value in content.items())
    normalized = row.get("normalized_content")
    if isinstance(normalized, dict) and normalized:
        return ", ".join(f"{key}: {value}" for key, value in normalized.items())
    return str(row.get("id", "fato publicado"))


def build_valid_answer(
    facts: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> str:
    parts: list[str] = []
    if facts:
        parts.append("; ".join(render_fact(row) for row in facts))
    if rules:
        parts.append(f"{len(rules)} regra(s) publicada(s) relacionada(s).")
    return "Encontrei nas fontes validadas: " + " ".join(parts)
