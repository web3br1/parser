from __future__ import annotations

from typing import Any

from context_builder.services.query_retrieval import (
    filter_relevant,
    rank_rows,
    relevant_contradictions,
    tokens,
)


def _price_fact(
    fact_id: str,
    *,
    service: str,
    confidence: float = 0.9,
    published_at: str = "2026-05-01T10:00:00Z",
) -> dict[str, Any]:
    return {
        "id": fact_id,
        "fact_type": "service_price",
        "content": {"service": service, "price": "R$ 50"},
        "normalized_content": {"service": service, "price": 50, "currency": "BRL"},
        "confidence": confidence,
        "published_at": published_at,
        "status": "published",
    }


def test_tokens_normalize_portuguese_diacritics_for_intents() -> None:
    assert {"precos", "servicos", "promocao", "cartao"} <= tokens(
        "Precos servicos promocao cartao"
    )
    assert {"precos", "servicos", "promocao", "cartao"} <= tokens(
        "Preços serviços promoção cartão"
    )


def test_filter_relevant_matches_accented_question_to_unaccented_entity() -> None:
    rows = [_price_fact("fact_corte", service="corte")]

    relevant = filter_relevant(rows, "Qual e o preço do córte?")

    assert [row["id"] for row in relevant] == ["fact_corte"]


def test_rank_rows_prefers_exact_entity_match_for_accented_question() -> None:
    rows = [
        _price_fact("fact_generic", service="servicos", confidence=0.99),
        _price_fact("fact_corte", service="corte", confidence=0.8),
    ]

    ranked = rank_rows(filter_relevant(rows, "Preço do córte"), "Preço do córte")

    assert ranked[0]["id"] == "fact_corte"
    assert "fact_generic" in {row["id"] for row in ranked}


def test_relevant_contradictions_filters_by_considered_fact_or_rule_ids() -> None:
    contradictions = [
        {"id": "c_fact", "fact_ids": ["fact_1"], "rule_ids": []},
        {"id": "c_rule", "fact_ids": [], "rule_ids": ["rule_1"]},
        {"id": "c_irrelevant", "fact_ids": ["fact_2"], "rule_ids": ["rule_2"]},
    ]

    relevant = relevant_contradictions(
        contradictions,
        fact_ids={"fact_1"},
        rule_ids={"rule_1"},
    )

    assert [row["id"] for row in relevant] == ["c_fact", "c_rule"]
