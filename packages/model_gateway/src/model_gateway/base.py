import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel

# Canonical Check B placeholders. Substitution is single-pass so a placeholder
# token appearing inside an already-substituted (untrusted) value is never
# re-substituted. Keep this the ONE render path for every gateway client.
_ENTAILMENT_PLACEHOLDER = re.compile(
    r"\{(claim_payload|fact_type|chunk_text|verified_quote|location)\}"
)


def render_entailment_prompt(
    prompt_template: str,
    *,
    claim_payload: dict[str, Any],
    fact_type: str,
    chunk_text: str,
    verified_quote: str,
    location: dict[str, Any],
) -> str:
    """Render the grounding Check B prompt from grounding inputs only.

    The single canonical implementation shared by every provider client and by
    ``grounding.prompt`` so the test path and the live call path are identical by
    construction. Substitution is ONE left-to-right regex pass: hostile
    ``chunk_text`` containing the literal ``{verified_quote}`` / ``{location}``
    cannot forge a second highlighted-quote or location region. No slot exists
    for extractor rationale, chain-of-thought, prompt internals, or self-reported
    confidence - the verifier stays independent of the extractor.
    """
    mapping = {
        "claim_payload": json.dumps(claim_payload, ensure_ascii=False, sort_keys=True),
        "fact_type": fact_type,
        "chunk_text": chunk_text,
        "verified_quote": verified_quote,
        "location": json.dumps(location, ensure_ascii=False, sort_keys=True),
    }
    return _ENTAILMENT_PLACEHOLDER.sub(lambda match: mapping[match.group(1)], prompt_template)


class ModelProvider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class ModelRunConfig(BaseModel):
    provider: Literal["ollama", "openai"]
    model: str
    temperature: float = 0.0
    max_output_tokens: int
    timeout_seconds: float
    allow_external_provider: bool = False


@dataclass(frozen=True)
class ClassificationItem:
    classification: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class ClassificationResponse:
    classifications: list[ClassificationItem]
    model_name: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    raw_response: str
    provider: str = ""
    model: str = ""
    latency_ms: int = 0
    raw_response_hash: str = ""
    estimated_cost_usd: float = 0.0


@dataclass(frozen=True)
class ExtractionResponse:
    model_name: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    raw_response: str
    provider: str = ""
    model: str = ""
    latency_ms: int = 0
    raw_response_hash: str = ""
    estimated_cost_usd: float = 0.0


@dataclass(frozen=True)
class EntailmentResponse:
    model_name: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    raw_response: str
    provider: str = ""
    model: str = ""
    latency_ms: int = 0
    raw_response_hash: str = ""
    estimated_cost_usd: float = 0.0


class ModelGatewayBase(ABC):
    @abstractmethod
    def classify(
        self,
        chunk_text: str,
        prompt_template: str,
        prompt_version: str,
        config: ModelRunConfig | None = None,
    ) -> ClassificationResponse:
        raise NotImplementedError

    @abstractmethod
    def extract(
        self,
        chunk_text: str,
        prompt_template: str,
        prompt_version: str,
        config: ModelRunConfig | None = None,
    ) -> ExtractionResponse:
        raise NotImplementedError

    @abstractmethod
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
        """Independent entailment verification (grounding Check B).

        The verifier is adversarial to the extractor and must stay isolated
        from extraction prompt internals. The signature intentionally accepts
        only grounding inputs: the structured claim, its fact type, the source
        chunk, the deterministically verified quote, and source location
        metadata. It must NOT receive extractor chain-of-thought, extractor
        rationale, extraction prompt internals, or model self-reported
        confidence as an instruction.
        """
        raise NotImplementedError
