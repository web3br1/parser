"""Re-grounding cache hash (Task 3).

Before calling the entailment model, the worker deduplicates by a stable hash
of::

    fact_or_rule_type + normalized_claim_payload + verified_quote
        + grounding_prompt_version + grounding_model

so identical claims and evidence do not trigger repeated Check B calls.

IMPORTANT: this key gates **Check B only**. Check A (deterministic evidence) must
always re-run for the current chunk, because it also validates offsets and
source-local evidence integrity that the cache key does not capture.

Canonicalization collapses key-order and whitespace differences in the claim
payload so cosmetically different but semantically identical claims map to the
same key. Changing the type, claim, quote, prompt version, or model changes the
key. Pure, model-free.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")

# Stable separators for the field-join layer. The unit separator (0x1f) cannot
# appear in normal text, so it cleanly delimits the five inputs.
_FIELD_SEP = "\x1f"


def _normalize_str(text: str) -> str:
    """Canonicalize a string: NFC, collapse internal whitespace, trim."""
    normalized = unicodedata.normalize("NFC", text)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()


def _canonicalize(value: Any) -> Any:
    """Recursively canonicalize a JSON-like value for stable serialization.

    - dict: canonicalize each value; key order is normalized later by
      ``json.dumps(sort_keys=True)``.
    - list/tuple: order is significant (ordered data); canonicalize elements.
    - str: NFC + whitespace-collapsed + trimmed.
    - other scalars: returned as-is.
    """
    if isinstance(value, dict):
        return {key: _canonicalize(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, str):
        return _normalize_str(value)
    return value


def _canonical_payload(payload: Any) -> str:
    """Serialize a claim payload to a canonical JSON string.

    Sorted keys + stable separators collapse key-order and formatting
    differences; recursive string normalization collapses whitespace.
    """
    canonical = _canonicalize(payload)
    return json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def grounding_key(
    fact_or_rule_type: str,
    normalized_claim_payload: Any,
    verified_quote: str,
    grounding_prompt_version: str,
    grounding_model: str,
) -> str:
    """Return a stable sha256 hex key for re-grounding deduplication.

    Identical inputs (modulo claim key-order and whitespace) produce identical
    keys; changing any of the five inputs changes the key.
    """
    parts = [
        _normalize_str(fact_or_rule_type),
        _canonical_payload(normalized_claim_payload),
        _normalize_str(verified_quote),
        _normalize_str(grounding_prompt_version),
        _normalize_str(grounding_model),
    ]
    joined = _FIELD_SEP.join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
