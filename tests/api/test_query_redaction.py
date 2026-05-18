from __future__ import annotations

from context_builder.services.query_redaction import (
    can_expose_sensitive_fields,
    context_row,
    redact_sensitive,
    redact_sensitive_quote,
)


def test_redact_sensitive_removes_nested_internal_fields() -> None:
    payload = {
        "content": {
            "public_price": "R$ 50",
            "cost": "R$ 20",
            "nested": {"margin": "60%", "visible": True},
        },
        "rules": [
            {"discount": "5%", "internal_notes": "nao mencionar"},
            {"payment_method": "pix"},
        ],
    }

    assert redact_sensitive(payload) == {
        "content": {
            "public_price": "R$ 50",
            "nested": {"visible": True},
        },
        "rules": [
            {"discount": "5%"},
            {"payment_method": "pix"},
        ],
    }


def test_redact_sensitive_matches_case_camel_case_and_key_fragments() -> None:
    payload = {
        "Cost": "R$ 20",
        "gross_margin": "60%",
        "secret_key": "hidden",
        "access_token": "hidden",
        "apiKey": "hidden",
        "content": {
            "public_price": "R$ 50",
            "custo": "R$ 20",
            "margem": "60%",
        },
    }

    assert redact_sensitive(payload) == {
        "content": {
            "public_price": "R$ 50",
        },
    }


def test_redact_sensitive_preserves_public_customer_and_custom_fields() -> None:
    payload = {
        "customer_name": "Ana",
        "customers": 12,
        "custom_field": "public",
        "content": {"customer_note": "prefers morning"},
    }

    assert redact_sensitive(payload) == payload
    assert (
        redact_sensitive_quote(
            "Can customers pay with Pix? Custom plan is public.",
            user_role="staff",
        )
        == "Can customers pay with Pix? Custom plan is public."
    )


def test_context_row_redacts_sensitive_fields_for_all_query_roles() -> None:
    row = {
        "id": "fact_1",
        "content": {"public_price": "R$ 50", "cost": "R$ 20"},
        "normalized_content": {"public_price": 50, "margin": 0.6},
    }

    for role in ("staff", "reviewer", "manager", "owner", "unknown"):
        visible = context_row(row, user_role=role)

        assert visible == {
            "id": "fact_1",
            "content": {"public_price": "R$ 50"},
            "normalized_content": {"public_price": 50},
        }


def test_redact_sensitive_quote_blocks_quotes_containing_internal_keys() -> None:
    assert (
        redact_sensitive_quote(
            "Preco publico R$ 50; internal_notes negociar com gerente",
            user_role="owner",
        )
        is None
    )
    assert redact_sensitive_quote("Preco publico R$ 50", user_role="staff") == "Preco publico R$ 50"
    assert redact_sensitive_quote(None, user_role="staff") is None


def test_redact_sensitive_quote_blocks_portuguese_sensitive_labels() -> None:
    assert (
        redact_sensitive_quote(
            "Corte publico R$ 50; custo R$ 20; margem 60%",
            user_role="staff",
        )
        is None
    )


def test_no_query_role_can_expose_sensitive_fields() -> None:
    for role in ("staff", "reviewer", "manager", "owner", "unknown"):
        assert can_expose_sensitive_fields(role) is False
