"""Tests for the re-grounding cache hash (Task 3).

``grounding_key`` produces a stable sha256 over::

    fact_or_rule_type + normalized_claim_payload + verified_quote
        + grounding_prompt_version + grounding_model

The key gates Check B only - Check A always re-runs (documented behavior, not
enforced here). Canonicalization collapses key-order and whitespace differences
in the claim payload; changing the type, claim, quote, prompt version, or model
changes the key.
"""

from __future__ import annotations

import re

from grounding.cache import grounding_key

_BASE = dict(
    fact_or_rule_type="service_price",
    normalized_claim_payload={"price": 100, "currency": "BRL", "service": "wash"},
    verified_quote="preço de R$100",
    grounding_prompt_version="v1",
    grounding_model="ollama/llama3",
)


def _key(**overrides):
    args = dict(_BASE)
    args.update(overrides)
    return grounding_key(**args)


# --- shape ------------------------------------------------------------------


def test_returns_sha256_hex():
    key = _key()
    assert isinstance(key, str)
    assert re.fullmatch(r"[0-9a-f]{64}", key)


# --- stability --------------------------------------------------------------


def test_identical_inputs_identical_key():
    assert _key() == _key()


def test_payload_key_order_collapses():
    a = _key(normalized_claim_payload={"price": 100, "currency": "BRL", "service": "wash"})
    b = _key(normalized_claim_payload={"service": "wash", "currency": "BRL", "price": 100})
    assert a == b


def test_payload_whitespace_collapses_in_string_values():
    # Whitespace normalization within payload values collapses to same key.
    a = _key(normalized_claim_payload={"note": "valid until june"})
    b = _key(normalized_claim_payload={"note": "valid   until\tjune"})
    assert a == b


def test_payload_outer_whitespace_collapses():
    a = _key(normalized_claim_payload={"note": "june"})
    b = _key(normalized_claim_payload={"note": "  june  "})
    assert a == b


def test_nested_payload_key_order_collapses():
    a = _key(normalized_claim_payload={"a": {"x": 1, "y": 2}, "b": [1, 2]})
    b = _key(normalized_claim_payload={"b": [1, 2], "a": {"y": 2, "x": 1}})
    assert a == b


# --- sensitivity ------------------------------------------------------------


def test_changing_type_changes_key():
    assert _key(fact_or_rule_type="business_rules") != _key()


def test_changing_claim_changes_key():
    assert _key(normalized_claim_payload={"price": 200}) != _key()


def test_changing_quote_changes_key():
    assert _key(verified_quote="other quote") != _key()


def test_changing_prompt_version_changes_key():
    assert _key(grounding_prompt_version="v2") != _key()


def test_changing_model_changes_key():
    assert _key(grounding_model="openai/gpt-4o") != _key()


def test_list_order_is_significant():
    # Lists are ordered data; reordering is a different claim.
    a = _key(normalized_claim_payload={"items": [1, 2, 3]})
    b = _key(normalized_claim_payload={"items": [3, 2, 1]})
    assert a != b
