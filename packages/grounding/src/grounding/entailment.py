"""Grounding Check B - independent entailment verification.

``verify_entailment_claim`` builds the versioned entailment prompt, calls the
model gateway's ``verify_entailment`` contract, and maps the verifier's verdict
to an :class:`~grounding.types.EntailmentResult`.

The function is deliberately thin and adversarial: it never feeds extractor
rationale, chain-of-thought, prompt internals, or self-reported confidence to
the verifier. Any malformed response or an "unsure" verdict maps to
``abstained`` so that ambiguity is never silently treated as support.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from model_gateway.base import EntailmentResponse, ModelRunConfig

from .prompt import ENTAILMENT_PROMPT, get_grounding_prompt_version
from .types import EntailmentResult, EntailmentStatus

# Map the verifier verdict vocabulary to grounding entailment statuses.
# Anything outside this map (missing field, unknown token, malformed JSON,
# explicit "unsure") is treated as an abstention.
_SUPPORTED_VERDICTS = {"supported", "support", "entailed", "yes", "true"}
_NOT_SUPPORTED_VERDICTS = {
    "not_supported",
    "unsupported",
    "contradicted",
    "no",
    "false",
}


class _EntailmentGateway(Protocol):
    """Structural type for the slice of the gateway Check B needs."""

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
    ) -> EntailmentResponse: ...


def _parse_verdict(raw_response: str) -> tuple[EntailmentStatus, str]:
    """Map a raw verifier response to an entailment status and reason.

    A malformed payload or an unrecognized / "unsure" verdict abstains.
    """
    text = (raw_response or "").strip()
    if not text:
        return "abstained", "empty verifier response"

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return "abstained", "verifier response was not valid JSON"

    if not isinstance(parsed, dict):
        return "abstained", "verifier response was not a JSON object"

    verdict_raw = parsed.get("verdict")
    if not isinstance(verdict_raw, str):
        return "abstained", "verifier response missing verdict"

    verdict = verdict_raw.strip().lower()
    reason = parsed.get("reason")
    reason_text = reason.strip() if isinstance(reason, str) and reason.strip() else ""

    if verdict in _SUPPORTED_VERDICTS:
        return "passed", reason_text or "source supports the claim"
    if verdict in _NOT_SUPPORTED_VERDICTS:
        return "failed", reason_text or "source does not support the claim"
    # "unsure" and any unknown verdict token abstain.
    return "abstained", reason_text or f"verifier was unsure (verdict={verdict!r})"


def verify_entailment_claim(
    *,
    gateway: _EntailmentGateway,
    claim_payload: dict[str, Any],
    fact_type: str,
    chunk_text: str,
    verified_quote: str,
    location: dict[str, Any] | None = None,
    config: ModelRunConfig | None = None,
) -> EntailmentResult:
    """Run grounding Check B for a single claim.

    Builds the versioned entailment prompt, invokes the gateway, and maps the
    verdict to an :class:`EntailmentResult`. Malformed or "unsure" verdicts map
    to ``abstained``.
    """
    prompt_version = get_grounding_prompt_version()
    response = gateway.verify_entailment(
        claim_payload=claim_payload,
        fact_type=fact_type,
        chunk_text=chunk_text,
        verified_quote=verified_quote,
        location=location or {},
        prompt_template=ENTAILMENT_PROMPT,
        prompt_version=prompt_version,
        config=config,
    )

    status, reason = _parse_verdict(response.raw_response)

    return EntailmentResult(
        entailment_status=status,
        entailment_reason=reason,
        grounding_model=response.model_name or response.model or None,
        grounding_prompt_version=response.prompt_version or prompt_version,
        latency_ms=response.latency_ms,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        estimated_cost_usd=response.estimated_cost_usd,
    )
