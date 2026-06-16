from __future__ import annotations

from grounding import GroundingResult

from worker_extraction import grounding as grnd


def _output(**kwargs):  # type: ignore[no-untyped-def]
    from worker_extraction.extractor import ExtractionOutput

    defaults = dict(
        fact_type="service_price",
        status="ok",
        raw_data={"service_name": "Corte"},
        validated_data={"service_name": "Corte"},
        normalized_content={"service_name": "Corte", "price_amount": 120.0},
        evidence_quote="Corte R$120",
        evidence_char_start=None,
        evidence_char_end=None,
        ambiguities=[],
        model_name="gpt-4o",
        prompt_version="abc123",
        input_tokens=10,
        output_tokens=20,
        raw_response_hash="deadbeef",
        validation_errors=[],
        is_multi=False,
        records=[],
    )
    defaults.update(kwargs)
    return ExtractionOutput(**defaults)


def test_grounding_enabled_reads_flag(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("GROUNDING_ENABLED", raising=False)
    assert grnd.grounding_enabled() is False
    monkeypatch.setenv("GROUNDING_ENABLED", "true")
    assert grnd.grounding_enabled() is True
    monkeypatch.setenv("GROUNDING_ENABLED", "0")
    assert grnd.grounding_enabled() is False


def test_grounding_profile_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("GROUNDING_PROFILE", raising=False)
    assert grnd.grounding_profile() == "default"
    monkeypatch.setenv("GROUNDING_PROFILE", "industrial")
    assert grnd.grounding_profile() == "industrial"


def test_build_claim_single_fact_uses_normalized_content() -> None:
    claim = grnd.build_claim(_output(), "extracted_facts")
    assert claim == {"service_name": "Corte", "price_amount": 120.0}


def test_build_claim_business_rule_uses_condition_action() -> None:
    out = _output(
        validated_data={"condition": {"min": 100}, "action": {"discount_percentage": 10.0}},
    )
    claim = grnd.build_claim(out, "business_rules")
    assert claim == {"condition": {"min": 100}, "action": {"discount_percentage": 10.0}}


def test_build_claim_multi_wraps_records() -> None:
    records = [{"day_of_week": "mon"}, {"day_of_week": "tue"}]
    out = _output(is_multi=True, records=records, normalized_content={})
    claim = grnd.build_claim(out, "extracted_facts")
    assert claim == {"records": records}


def _result(*, required: bool, status: str) -> GroundingResult:
    return GroundingResult(
        grounding_status=status,  # type: ignore[arg-type]
        grounding_required=required,
        grounding_reason="r",
        deterministic_status="passed",
        deterministic_reason="ok",
        match_mode="exact",
        offset_status="offsets_verified",
        entailment_status="failed",
        entailment_reason="contradicted",
        grounding_model="m",
        grounding_prompt_version="gp1",
        grounding_checked_at="2026-06-15T00:00:00+00:00",
        grounding_key="k",
        config_version="stakes_config.v1",
    )


def test_blocks_record_only_when_required_and_not_clean() -> None:
    assert grnd.blocks_record(_result(required=True, status="failed")) is True
    assert grnd.blocks_record(_result(required=True, status="abstained")) is True
    assert grnd.blocks_record(_result(required=True, status="passed")) is False
    assert grnd.blocks_record(_result(required=False, status="failed")) is False


def test_to_payload_has_all_persistence_keys() -> None:
    payload = grnd.to_payload(_result(required=True, status="failed"))
    for key in (
        "grounding_status",
        "grounding_required",
        "grounding_reason",
        "deterministic_status",
        "match_mode",
        "offset_status",
        "entailment_status",
        "grounding_model",
        "grounding_prompt_version",
        "grounding_key",
        "config_version",
        "grounding_checked_at",
    ):
        assert key in payload
