from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from grounding.entailment import verify_entailment_claim
from grounding.prompt import (
    ENTAILMENT_PROMPT,
    get_grounding_prompt_version,
    render_entailment_prompt,
)
from grounding.types import EntailmentResult
from model_gateway.base import EntailmentResponse, ModelRunConfig

# --- Fake gateway -----------------------------------------------------------


@dataclass
class _FakeGateway:
    """Records the inputs it receives and returns a scripted verdict.

    The fake renders the prompt exactly the way the real gateway does so that
    tests can inspect the prompt string actually handed to the model.
    """

    verdict: str
    calls: list[dict[str, Any]] = field(default_factory=list)
    rendered_prompts: list[str] = field(default_factory=list)

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
        rendered = render_entailment_prompt(
            prompt_template,
            claim_payload=claim_payload,
            fact_type=fact_type,
            chunk_text=chunk_text,
            verified_quote=verified_quote,
            location=location,
        )
        self.calls.append(
            {
                "claim_payload": claim_payload,
                "fact_type": fact_type,
                "chunk_text": chunk_text,
                "verified_quote": verified_quote,
                "location": location,
                "prompt_template": prompt_template,
                "prompt_version": prompt_version,
            }
        )
        self.rendered_prompts.append(rendered)
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
    return json.dumps({"verdict": value, "reason": reason})


def _run(verdict: str, **overrides: Any) -> tuple[EntailmentResult, _FakeGateway]:
    gateway = _FakeGateway(verdict=verdict)
    kwargs: dict[str, Any] = {
        "claim_payload": {"service_name": "corte", "price_amount": 50},
        "fact_type": "service_price",
        "chunk_text": "Corte de cabelo custa R$ 50.",
        "verified_quote": "R$ 50",
        "location": {"chunk_id": "c1"},
    }
    kwargs.update(overrides)
    result = verify_entailment_claim(gateway=gateway, **kwargs)
    return result, gateway


# --- Status mapping ---------------------------------------------------------


def test_supported_claim_passes() -> None:
    result, _ = _run(_verdict("supported"))
    assert isinstance(result, EntailmentResult)
    assert result.entailment_status == "passed"
    assert result.grounding_model == "fake-model"
    assert result.grounding_prompt_version == get_grounding_prompt_version()
    assert result.latency_ms == 42
    assert result.input_tokens == 11
    assert result.output_tokens == 7


# NOTE: the two tests below assert only the verdict -> status MAPPING for a
# negation/condition-shaped case. They do NOT prove the verifier actually catches
# negation or scope in a real model call — that guarantee can only be proven with
# a live verifier and is measured by the grounding gold slice
# (examples/grounding_gold/manifest.json: rule-discount-negated,
# rule-scope-exception, rule-conditional-future). Do not read these as
# entailment-quality coverage.


def test_not_supported_verdict_for_negation_case_maps_to_failed() -> None:
    # The quote "desconto de 20%" exists, but the chunk says it is not offered.
    # Mapping check only: a "not_supported" verdict must become "failed".
    result, _ = _run(
        _verdict("not_supported", reason="discount is explicitly not offered"),
        claim_payload={"discount_percentage": 20},
        fact_type="discount_rule",
        chunk_text=(
            "Nao ha desconto de 20% para esse servico. "
            "O desconto de 20% nao e oferecido."
        ),
        verified_quote="desconto de 20%",
    )
    assert result.entailment_status == "failed"


def test_not_supported_verdict_for_conditional_case_maps_to_failed() -> None:
    # Mapping check only (see NOTE above): conditional-shaped chunk + a
    # "not_supported" verdict must become "failed".
    result, _ = _run(
        _verdict("not_supported", reason="claim holds only under a condition"),
        chunk_text=(
            "O preco e R$ 50 apenas para clientes do plano premium. "
            "Para os demais, consulte a tabela."
        ),
    )
    assert result.entailment_status == "failed"


def test_normalized_iso_date_semantically_supported_passes() -> None:
    # The normalized claim carries an ISO date derived from "junho"; the ISO
    # string never appears literally, but the month-level meaning is supported.
    result, _ = _run(
        _verdict("supported", reason="june is supported at the month level"),
        claim_payload={"valid_from": "2026-06-01"},
        fact_type="service_price",
        chunk_text="A promocao vale a partir de junho.",
        verified_quote="a partir de junho",
    )
    assert result.entailment_status == "passed"


@pytest.mark.parametrize(
    "raw",
    [
        "not json at all",
        json.dumps({"verdict": "maybe"}),
        json.dumps({"verdict": "unsure"}),
        json.dumps({"reason": "missing verdict field"}),
        "",
    ],
)
def test_malformed_or_unsure_verdict_abstains(raw: str) -> None:
    result, _ = _run(raw)
    assert result.entailment_status == "abstained"


# --- Prompt isolation -------------------------------------------------------


def test_rendered_prompt_excludes_rationale_and_confidence() -> None:
    _, gateway = _run(_verdict("supported"))
    assert gateway.rendered_prompts, "gateway must have been called"
    rendered = gateway.rendered_prompts[0].lower()
    for forbidden in (
        "rationale",
        "chain-of-thought",
        "chain of thought",
        "self-reported",
        "extractor confidence",
        "confidence",
    ):
        assert forbidden not in rendered, f"prompt leaked: {forbidden}"


def test_rendered_prompt_carries_grounding_inputs() -> None:
    _, gateway = _run(
        _verdict("supported"),
        chunk_text="Corte custa R$ 50.",
        verified_quote="R$ 50",
        claim_payload={"price_amount": 50},
    )
    rendered = gateway.rendered_prompts[0]
    assert "Corte custa R$ 50." in rendered
    assert "R$ 50" in rendered
    assert "price_amount" in rendered


def test_prompt_template_has_no_extractor_internals() -> None:
    template = ENTAILMENT_PROMPT.lower()
    for forbidden in ("rationale", "chain-of-thought", "confidence", "self-reported"):
        assert forbidden not in template


def test_prompt_version_is_stable_hash() -> None:
    v1 = get_grounding_prompt_version()
    v2 = get_grounding_prompt_version()
    assert v1 == v2
    assert isinstance(v1, str)
    assert len(v1) == 16
