from __future__ import annotations

from source_pack.validators import sanitize_text, validate_no_forbidden_payload


def test_sanitize_text_redacts_private_paths_and_tokens() -> None:
    text = r"Bearer abcdefghijklmnop C:\Users\Katz\secret raw_prompt Traceback"

    sanitized = sanitize_text(text)

    assert "Bearer " not in sanitized
    assert r"C:\Users" not in sanitized
    assert "raw_prompt" not in sanitized
    assert "Traceback" not in sanitized


def test_validate_no_forbidden_payload_blocks_sensitive_payloads() -> None:
    errors = validate_no_forbidden_payload({"quote": "provider_response: secret"})

    assert errors == ["forbidden_marker:provider_response"]


def test_validate_no_forbidden_payload_blocks_local_paths_and_raw_prompt_labels() -> None:
    errors = validate_no_forbidden_payload(
        {"quote": r"SYSTEM PROMPT: x C:\Users\Katz\secret /home/katz/secret"}
    )

    assert "forbidden_marker:SYSTEM PROMPT" in errors
    assert any(error.startswith("forbidden_pattern:") for error in errors)
