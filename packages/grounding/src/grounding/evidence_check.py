"""Check A - deterministic evidence verification.

Pure, model-free code. Proves that ``evidence_quote`` is literal source text
inside ``chunk_text`` after a fixed set of typographic normalizations, and that
any provided offsets actually point at the quote.

No model imports may be added to this module.
"""

from __future__ import annotations

import re
import unicodedata

from grounding.types import DeterministicResult, MatchMode, OffsetStatus

# Canonical quote-character folding. Curly / typographic quotes are folded to
# their straight ASCII equivalents so quotes copied with different keyboards or
# autocorrect still match.
_QUOTE_MAP = {
    "‘": "'",  # left single quotation mark
    "’": "'",  # right single quotation mark
    "‚": "'",  # single low-9 quotation mark
    "‛": "'",  # single high-reversed-9 quotation mark
    "′": "'",  # prime
    "“": '"',  # left double quotation mark
    "”": '"',  # right double quotation mark
    "„": '"',  # double low-9 quotation mark
    "‟": '"',  # double high-reversed-9 quotation mark
    "″": '"',  # double prime
    "«": '"',  # left-pointing double angle quotation mark
    "»": '"',  # right-pointing double angle quotation mark
}

_QUOTE_TABLE = {ord(k): v for k, v in _QUOTE_MAP.items()}

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Canonicalize text for deterministic comparison.

    Steps (in order):
    1. Unicode NFC.
    2. Canonical quote characters (curly -> straight ASCII).
    3. Non-breaking spaces (and related) converted to regular spaces.
    4. Repeated whitespace collapsed to a single space.
    5. Leading/trailing whitespace removed.
    """
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.translate(_QUOTE_TABLE)
    # NBSP and narrow NBSP -> regular space before whitespace collapse.
    normalized = normalized.replace(" ", " ").replace(" ", " ")
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()


def _fail(reason: str, offset_status: OffsetStatus = "no_match") -> DeterministicResult:
    return DeterministicResult(
        deterministic_status="failed",
        deterministic_reason=reason,
        match_mode=None,
        offset_status=offset_status,
        verified_quote=None,
        char_start=None,
        char_end=None,
    )


def verify_evidence(
    chunk_text: str,
    evidence_quote: str,
    char_start: int | None,
    char_end: int | None,
) -> DeterministicResult:
    """Verify that ``evidence_quote`` is literal source text in ``chunk_text``.

    Returns a :class:`DeterministicResult`. Never raises on bad input.
    """
    # Empty / whitespace-only evidence is an automatic failure.
    if evidence_quote is None or _normalize(evidence_quote) == "":
        return _fail("empty evidence quote")

    norm_quote = _normalize(evidence_quote)

    offsets_provided = char_start is not None or char_end is not None

    if offsets_provided:
        return _verify_with_offsets(chunk_text, evidence_quote, norm_quote, char_start, char_end)
    return _verify_substring(chunk_text, norm_quote)


def _verify_with_offsets(
    chunk_text: str,
    raw_quote: str,
    norm_quote: str,
    char_start: int | None,
    char_end: int | None,
) -> DeterministicResult:
    # Both offsets must be present and integers when either is provided.
    if char_start is None or char_end is None:
        return _fail("incomplete offsets: both char_start and char_end are required")

    # Invalid ordering / negative offsets.
    if char_start < 0 or char_end < 0:
        return _fail("invalid offsets: negative char_start or char_end")
    if char_start >= char_end:
        return _fail("invalid offset ordering: char_start must be < char_end")

    # Out-of-range offsets.
    if char_start > len(chunk_text) or char_end > len(chunk_text):
        return _fail("offsets out of range for chunk_text")

    sliced = chunk_text[char_start:char_end]
    norm_sliced = _normalize(sliced)

    if norm_sliced != norm_quote:
        return _fail("offset slice does not match evidence quote")

    # Exact when raw slice equals raw quote with no normalization needed.
    match_mode: MatchMode = "exact" if sliced == raw_quote else "normalized"

    return DeterministicResult(
        deterministic_status="passed",
        deterministic_reason="evidence verified against offsets",
        match_mode=match_mode,
        offset_status="offsets_verified",
        verified_quote=norm_quote,
        char_start=char_start,
        char_end=char_end,
    )


def _verify_substring(chunk_text: str, norm_quote: str) -> DeterministicResult:
    norm_chunk = _normalize(chunk_text)

    occurrences = _count_occurrences(norm_chunk, norm_quote)
    if occurrences == 0:
        return _fail("evidence quote not found as substring of chunk_text")

    # Try to recover canonical offsets against the raw chunk when the raw quote
    # appears verbatim; otherwise leave offsets None but still pass.
    recovered_start, recovered_end = _recover_raw_offsets(chunk_text, norm_quote)

    offset_status: OffsetStatus = (
        "ambiguous_substring_without_offsets"
        if occurrences > 1
        else "substring_without_offsets"
    )

    return DeterministicResult(
        deterministic_status="passed",
        deterministic_reason="evidence verified as substring without offsets",
        match_mode="normalized",
        offset_status=offset_status,
        verified_quote=norm_quote,
        char_start=recovered_start,
        char_end=recovered_end,
    )


def _count_occurrences(haystack: str, needle: str) -> int:
    if not needle:
        return 0
    count = 0
    idx = haystack.find(needle)
    while idx != -1:
        count += 1
        idx = haystack.find(needle, idx + 1)
    return count


def _recover_raw_offsets(chunk_text: str, norm_quote: str) -> tuple[int | None, int | None]:
    """Recover offsets into the raw chunk when the normalized quote appears
    verbatim in the raw chunk. Returns ``(None, None)`` when not recoverable.

    Only recovers when there is exactly one verbatim occurrence in the raw
    chunk, so the returned offsets are unambiguous.
    """
    first = chunk_text.find(norm_quote)
    if first == -1:
        return (None, None)
    second = chunk_text.find(norm_quote, first + 1)
    if second != -1:
        return (None, None)
    return (first, first + len(norm_quote))
