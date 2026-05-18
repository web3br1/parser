from __future__ import annotations

from typing import Any

from context_builder.services.query_budget import fit_budget
from context_builder.services.query_evidence import build_evidence_for_outcome
from context_builder.services.query_redaction import context_row
from context_builder.services.query_response_builder import estimate_json_tokens


def _fact(fact_id: str, **overrides: Any) -> dict[str, Any]:
    row = {
        "id": fact_id,
        "source_id": "source_1",
        "chunk_id": f"chunk_{fact_id}",
        "evidence_span_id": None,
        "fact_type": "service_price",
        "content": {"service": fact_id, "price": "R$ 50"},
        "normalized_content": {"service": fact_id, "price": 50, "currency": "BRL"},
        "confidence": 0.9,
        "status": "published",
    }
    row.update(overrides)
    return row


def test_fit_budget_skips_oversized_rows_and_keeps_later_rows_that_fit() -> None:
    small_a = _fact("small_a")
    oversized = _fact(
        "oversized",
        content={"service": "oversized", "price": "R$ 999", "description": "longo " * 500},
    )
    small_b = _fact("small_b")
    budget = (
        estimate_json_tokens(context_row(small_a, user_role="staff"))
        + estimate_json_tokens(context_row(small_b, user_role="staff"))
    )

    selected, selected_tokens = fit_budget(
        [small_a, oversized, small_b],
        budget_tokens=budget,
        user_role="staff",
    )

    assert [row["id"] for row in selected] == ["small_a", "small_b"]
    assert selected_tokens <= budget


def test_build_evidence_for_outcome_does_not_call_loader_without_span_ids() -> None:
    calls: list[list[str]] = []

    evidence = build_evidence_for_outcome(
        facts=[_fact("fact_without_span")],
        rules=[],
        sources_by_id={"source_1": {"id": "source_1", "original_filename": "catalogo.pdf"}},
        user_role="staff",
        include_evidence=True,
        evidence_span_loader=lambda span_ids: calls.append(span_ids) or [],
    )

    assert calls == []
    assert evidence == [
        {
            "source_id": "source_1",
            "source_name": "catalogo.pdf",
            "evidence_span_id": None,
            "quote": None,
            "page_number": None,
            "sheet_name": None,
            "row_number": None,
            "chunk_id": "chunk_fact_without_span",
            "fact_id": "fact_without_span",
            "rule_id": None,
        }
    ]


def test_build_evidence_for_outcome_truncates_long_public_quotes() -> None:
    quote = "Corte: R$ 50. " + ("detalhe publico " * 100)

    evidence = build_evidence_for_outcome(
        facts=[_fact("fact_with_span", evidence_span_id="span_1")],
        rules=[],
        sources_by_id={"source_1": {"id": "source_1", "original_filename": "catalogo.pdf"}},
        user_role="staff",
        include_evidence=True,
        evidence_span_loader=lambda _span_ids: [
            {
                "id": "span_1",
                "quote": quote,
                "page_number": 1,
                "sheet_name": None,
                "row_number": None,
            }
        ],
    )

    assert evidence[0]["quote"].startswith("Corte: R$ 50")
    assert evidence[0]["quote"].endswith("...")
    assert len(evidence[0]["quote"]) <= 500
