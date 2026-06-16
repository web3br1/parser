from __future__ import annotations

from grounding.evidence_check import _normalize, verify_evidence


def test_exact_raw_match_passes_with_exact_mode() -> None:
    chunk = "O preco do servico e R$ 100,00 por hora."
    quote = "R$ 100,00 por hora"
    start = chunk.index(quote)
    end = start + len(quote)

    result = verify_evidence(chunk, quote, start, end)

    assert result.deterministic_status == "passed"
    assert result.match_mode == "exact"
    assert result.offset_status == "offsets_verified"
    assert result.verified_quote == quote
    assert result.char_start == start
    assert result.char_end == end


def test_normalized_match_with_curly_quotes_passes_with_normalized_mode() -> None:
    # Chunk uses curly quotes; evidence uses straight quotes.
    chunk = "A politica diz “desconto de 20%” para clientes novos."
    quote = 'desconto de 20%'

    result = verify_evidence(chunk, quote, None, None)

    assert result.deterministic_status == "passed"
    assert result.match_mode == "normalized"


def test_normalized_match_with_nbsp_and_collapsed_whitespace() -> None:
    chunk = "Horario: das  09h00   as  18h00."
    quote = "das 09h00 as 18h00"

    result = verify_evidence(chunk, quote, None, None)

    assert result.deterministic_status == "passed"
    assert result.match_mode == "normalized"


def test_nfc_normalization_match() -> None:
    # Decomposed (NFD) "cafe" with combining acute vs precomposed in quote.
    chunk = "Servimos café da manha gratis."
    quote = "café da manha"

    result = verify_evidence(chunk, quote, None, None)

    assert result.deterministic_status == "passed"
    assert result.match_mode == "normalized"


def test_empty_quote_fails() -> None:
    result = verify_evidence("algum texto", "", None, None)

    assert result.deterministic_status == "failed"
    assert "empty" in result.deterministic_reason.lower()
    assert result.match_mode is None


def test_whitespace_only_quote_fails_as_empty() -> None:
    result = verify_evidence("algum texto", "      ", None, None)

    assert result.deterministic_status == "failed"
    assert "empty" in result.deterministic_reason.lower()


def test_reversed_offsets_fail() -> None:
    chunk = "abcdefg"
    result = verify_evidence(chunk, "cde", 5, 2)

    assert result.deterministic_status == "failed"
    assert "offset" in result.deterministic_reason.lower()


def test_negative_offsets_fail() -> None:
    chunk = "abcdefg"
    result = verify_evidence(chunk, "abc", -1, 3)

    assert result.deterministic_status == "failed"
    assert "offset" in result.deterministic_reason.lower()


def test_equal_offsets_fail_as_invalid_ordering() -> None:
    chunk = "abcdefg"
    result = verify_evidence(chunk, "abc", 3, 3)

    assert result.deterministic_status == "failed"
    assert "offset" in result.deterministic_reason.lower()


def test_out_of_range_offsets_fail() -> None:
    chunk = "abcdefg"
    result = verify_evidence(chunk, "fg", 6, 99)

    assert result.deterministic_status == "failed"
    assert "range" in result.deterministic_reason.lower()


def test_offsets_present_but_slice_mismatch_fails() -> None:
    chunk = "preco e R$ 100,00 hoje"
    # offsets point at a different span than the quote
    result = verify_evidence(chunk, "R$ 100,00", 0, 5)

    assert result.deterministic_status == "failed"
    assert "match" in result.deterministic_reason.lower()


def test_substring_without_offsets_passes_and_records_status() -> None:
    chunk = "Aceitamos pagamento via Pix e cartao de credito."
    quote = "pagamento via Pix"

    result = verify_evidence(chunk, quote, None, None)

    assert result.deterministic_status == "passed"
    assert result.offset_status == "substring_without_offsets"
    # canonical offsets recovered when derivable
    assert result.char_start is not None
    assert result.char_end is not None
    assert chunk[result.char_start : result.char_end] == quote


def test_ambiguous_repeated_substring_passes_but_flagged() -> None:
    chunk = "preco preco preco"
    quote = "preco"

    result = verify_evidence(chunk, quote, None, None)

    assert result.deterministic_status == "passed"
    assert result.offset_status == "ambiguous_substring_without_offsets"


def test_substring_not_found_without_offsets_fails() -> None:
    chunk = "Texto totalmente diferente."
    quote = "nao existe aqui"

    result = verify_evidence(chunk, quote, None, None)

    assert result.deterministic_status == "failed"
    assert result.offset_status == "no_match"


def test_verified_quote_is_canonical_normalized_form() -> None:
    chunk = "valor:  R$ 50,00  total"
    quote = "R$  50,00"  # raw quote has extra whitespace

    result = verify_evidence(chunk, quote, None, None)

    assert result.deterministic_status == "passed"
    # verified_quote is the normalized canonical form
    assert result.verified_quote == "R$ 50,00"


def test_normalize_helper_is_idempotent_and_canonical() -> None:
    raw = "  “Hello”  world  "
    once = _normalize(raw)
    assert once == _normalize(once)
    assert "  " not in once  # no repeated whitespace
    assert "“" not in once
    assert once == '"Hello" world'
