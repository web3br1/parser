from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from grounding import (
    EvidenceInput,
    GroundingResult,
    run_grounding,
)
from grounding.cache import grounding_key
from grounding.prompt import get_grounding_prompt_version
from model_gateway.base import EntailmentResponse, ModelRunConfig

# --- Fake gateway -----------------------------------------------------------


@dataclass
class _FakeGateway:
    """Returns a scripted verdict and counts how often Check B is invoked."""

    verdict: str
    calls: list[dict[str, Any]] = field(default_factory=list)

    def verify_entailment(
        self,
        claim_payload: dict[str, Any],
        fact_type: str,
        chunk_text: str,
        verified_quote: str,
        location: dict[str, Any],
        prompt_template: str,
        prompt_version: str,
        config: ModelRunConfig | None = None,
    ) -> EntailmentResponse:
        self.calls.append(
            {
                "claim_payload": claim_payload,
                "fact_type": fact_type,
                "verified_quote": verified_quote,
            }
        )
        return EntailmentResponse(
            model_name="fake-model",
            prompt_version=prompt_version,
            input_tokens=11,
            output_tokens=7,
            raw_response=self.verdict,
            provider="ollama",
            model="fake-model",
            latency_ms=42,
            raw_response_hash="hash",
            estimated_cost_usd=0.0,
        )


def _verdict(value: str, reason: str = "r") -> str:
    import json

    return json.dumps({"verdict": value, "reason": reason})


# A counting fake whose Check A re-runs are observable through chunk_text passes.
def _make_evidence(quote: str = "R$ 50", char_start: int | None = 16, char_end: int | None = 21) -> EvidenceInput:
    return EvidenceInput(
        evidence_quote=quote,
        char_start=char_start,
        char_end=char_end,
        location={"chunk_id": "c1"},
    )


_CHUNK = "Corte de cabelo R$ 50 hoje."
_CLAIM = {"service_name": "corte", "price_amount": 50}

# A ModelRunConfig whose model identifier the runner uses to compute the
# (pre-call) cache key, so dedup does not depend on the response.
_CONFIG = ModelRunConfig(
    provider="ollama",
    model="fake-model",
    max_output_tokens=256,
    timeout_seconds=30.0,
)


# --- not_required branch ----------------------------------------------------


def test_type_not_in_config_is_not_required_and_skips_check_b() -> None:
    gateway = _FakeGateway(verdict=_verdict("supported"))
    result = run_grounding(
        claim=_CLAIM,
        fact_type="totally_unknown_type",
        chunk_text=_CHUNK,
        evidence=_make_evidence(),
        profile="default",
        gateway=gateway,
    )
    assert isinstance(result, GroundingResult)
    assert result.grounding_status == "not_required"
    assert result.grounding_required is False
    # Check B never runs for unconfigured types.
    assert gateway.calls == []
    # Check A still ran and recorded its outcome.
    assert result.deterministic_status == "passed"


# --- required: Check A failure ---------------------------------------------


def test_required_check_a_failure_routes_failed_and_skips_check_b() -> None:
    gateway = _FakeGateway(verdict=_verdict("supported"))
    result = run_grounding(
        claim=_CLAIM,
        fact_type="service_price",  # required in default profile
        chunk_text=_CHUNK,
        evidence=_make_evidence(quote="this quote is not present at all", char_start=None, char_end=None),
        profile="default",
        gateway=gateway,
    )
    assert result.grounding_required is True
    assert result.grounding_status == "failed"
    assert result.grounding_reason == "grounding_evidence_not_literal"
    assert result.deterministic_status == "failed"
    assert result.entailment_status is None
    # Check B must be skipped when Check A fails.
    assert gateway.calls == []


# --- required: Check A passes, Check B fails --------------------------------


def test_required_check_b_failure_routes_failed() -> None:
    gateway = _FakeGateway(verdict=_verdict("not_supported"))
    result = run_grounding(
        claim=_CLAIM,
        fact_type="service_price",
        chunk_text=_CHUNK,
        evidence=_make_evidence(),
        profile="default",
        gateway=gateway,
    )
    assert result.grounding_required is True
    assert result.deterministic_status == "passed"
    assert result.grounding_status == "failed"
    assert result.grounding_reason == "grounding_entailment_failed"
    assert result.entailment_status == "failed"
    assert len(gateway.calls) == 1


# --- required: Check B abstains ---------------------------------------------


def test_required_check_b_abstain_routes_abstained() -> None:
    gateway = _FakeGateway(verdict=_verdict("unsure"))
    result = run_grounding(
        claim=_CLAIM,
        fact_type="service_price",
        chunk_text=_CHUNK,
        evidence=_make_evidence(),
        profile="default",
        gateway=gateway,
    )
    assert result.grounding_required is True
    assert result.grounding_status == "abstained"
    assert result.grounding_reason == "grounding_abstained"
    assert result.entailment_status == "abstained"


# --- required: everything passes --------------------------------------------


def test_required_all_pass_routes_passed() -> None:
    gateway = _FakeGateway(verdict=_verdict("supported"))
    result = run_grounding(
        claim=_CLAIM,
        fact_type="service_price",
        chunk_text=_CHUNK,
        evidence=_make_evidence(),
        profile="default",
        gateway=gateway,
    )
    assert result.grounding_status == "passed"
    assert result.grounding_required is True
    assert result.deterministic_status == "passed"
    assert result.entailment_status == "passed"
    assert result.grounding_reason == "grounding_passed"
    assert result.grounding_model == "fake-model"
    assert result.grounding_prompt_version == get_grounding_prompt_version()
    assert result.grounding_checked_at is not None
    assert result.config_version is not None
    assert result.grounding_key is not None


# --- warn-only --------------------------------------------------------------


def test_warn_only_check_b_failure_records_warning_not_unreliable() -> None:
    gateway = _FakeGateway(verdict=_verdict("not_supported"))
    result = run_grounding(
        claim={"contact": "a@b.com"},
        fact_type="contact_info",  # warn_only in default profile
        chunk_text="Email: a@b.com",
        evidence=EvidenceInput(
            evidence_quote="a@b.com",
            char_start=None,
            char_end=None,
            location={},
        ),
        profile="default",
        gateway=gateway,
    )
    assert result.grounding_required is False
    # The warn-only failure is recorded but the overall status is not a hard fail.
    assert result.grounding_status == "passed"
    assert result.entailment_status == "failed"
    assert result.grounding_reason == "grounding_warn_only"


def test_warn_only_check_a_failure_records_warning_not_unreliable() -> None:
    gateway = _FakeGateway(verdict=_verdict("supported"))
    result = run_grounding(
        claim={"contact": "missing"},
        fact_type="contact_info",
        chunk_text="Email: a@b.com",
        evidence=EvidenceInput(
            evidence_quote="not in the chunk",
            char_start=None,
            char_end=None,
            location={},
        ),
        profile="default",
        gateway=gateway,
    )
    assert result.grounding_required is False
    assert result.grounding_status == "passed"
    assert result.deterministic_status == "failed"
    # Check B skipped because Check A failed, even for warn-only.
    assert gateway.calls == []
    assert result.grounding_reason == "grounding_warn_only"


# --- cache ------------------------------------------------------------------


def test_cache_hit_runs_check_b_once_check_a_twice() -> None:
    gateway = _FakeGateway(verdict=_verdict("supported"))
    cache: dict[str, Any] = {}

    first = run_grounding(
        claim=_CLAIM,
        fact_type="service_price",
        chunk_text=_CHUNK,
        evidence=_make_evidence(),
        profile="default",
        gateway=gateway,
        cache=cache,
        config=_CONFIG,
    )
    second = run_grounding(
        claim=_CLAIM,
        fact_type="service_price",
        chunk_text=_CHUNK,
        evidence=_make_evidence(),
        profile="default",
        gateway=gateway,
        cache=cache,
        config=_CONFIG,
    )
    # Check B (gateway) invoked exactly once despite two runs.
    assert len(gateway.calls) == 1
    # Both runs produced a passed result (Check A re-ran both times).
    assert first.grounding_status == "passed"
    assert second.grounding_status == "passed"
    assert first.grounding_key == second.grounding_key
    assert first.grounding_key in cache


def test_cache_key_matches_grounding_key_helper() -> None:
    gateway = _FakeGateway(verdict=_verdict("supported"))
    cache: dict[str, Any] = {}
    result = run_grounding(
        claim=_CLAIM,
        fact_type="service_price",
        chunk_text=_CHUNK,
        evidence=_make_evidence(),
        profile="default",
        gateway=gateway,
        cache=cache,
        config=_CONFIG,
    )
    # The runner keys Check B on the canonical verified_quote produced by Check A,
    # not the raw model name (which is unknown before the call). The grounding_key
    # the runner stored is the one persisted on the result and present in cache.
    expected = grounding_key(
        "service_price",
        _CLAIM,
        "R$ 50",
        get_grounding_prompt_version(),
        "fake-model",
    )
    assert result.grounding_key in cache
    assert result.grounding_key == expected
