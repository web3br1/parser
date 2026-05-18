import os
from dataclasses import dataclass
from hashlib import sha256

from model_gateway import ClassificationResponse, get_model_gateway
from security.injection_detector import InjectionCheckResult, check_injection

from worker_classification.prompt import get_prompt_template, get_prompt_version

CONFIDENCE_THRESHOLD: float = 0.75
UNKNOWN_MIN_CONFIDENCE: float = 0.30

FACT_TYPES: set[str] = {
    "service_price",
    "business_hours",
    "payment_method",
    "contact_info",
    "faq_item",
}
RULE_TYPES: set[str] = {
    "discount_rule",
    "cancellation_policy",
}
ALLOWED_CLASSIFICATIONS: set[str] = FACT_TYPES | RULE_TYPES | {"unknown"}


@dataclass
class ClassificationDecision:
    fact_type: str
    confidence: float
    reason: str
    destination: str
    passes_threshold: bool


@dataclass
class ChunkClassificationResult:
    injection_check: InjectionCheckResult
    raw_response: ClassificationResponse | None
    decisions: list[ClassificationDecision]
    prompt_version: str
    model_name: str
    model_provider: str
    input_tokens: int
    output_tokens: int
    raw_response_hash: str
    latency_ms: int = 0
    estimated_cost_usd: float = 0.0


def classify_chunk(chunk_text: str) -> ChunkClassificationResult:
    injection = check_injection(chunk_text)
    prompt_version = get_prompt_version()
    provider = _get_provider()

    if injection.injection_suspected:
        return ChunkClassificationResult(
            injection_check=injection,
            raw_response=None,
            decisions=[
                ClassificationDecision(
                    fact_type="unknown",
                    confidence=0.0,
                    reason="injection_suspected",
                    destination="unknown_facts_queue",
                    passes_threshold=False,
                )
            ],
            prompt_version=prompt_version,
            model_name="none",
            model_provider="none",
            input_tokens=0,
            output_tokens=0,
            raw_response_hash="",
            latency_ms=0,
            estimated_cost_usd=0.0,
        )

    gateway = get_model_gateway(provider)
    response = gateway.classify(
        chunk_text=chunk_text,
        prompt_template=get_prompt_template(),
        prompt_version=prompt_version,
    )

    return ChunkClassificationResult(
        injection_check=injection,
        raw_response=response,
        decisions=_build_decisions(response),
        prompt_version=prompt_version,
        model_name=response.model_name,
        model_provider=response.provider or provider,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        raw_response_hash=response.raw_response_hash or sha256(response.raw_response.encode()).hexdigest(),
        latency_ms=response.latency_ms,
        estimated_cost_usd=response.estimated_cost_usd,
    )


def _build_decisions(response: ClassificationResponse) -> list[ClassificationDecision]:
    if not response.classifications:
        return [
            ClassificationDecision(
                fact_type="unknown",
                confidence=0.0,
                reason="empty_classifications",
                destination="unknown_facts_queue",
                passes_threshold=False,
            )
        ]

    decisions: list[ClassificationDecision] = []
    for item in response.classifications:
        if item.classification not in ALLOWED_CLASSIFICATIONS:
            decisions.append(
                ClassificationDecision(
                    fact_type=item.classification,
                    confidence=item.confidence,
                    reason=f"unsupported_classification: {item.reason}",
                    destination="unknown_facts_queue",
                    passes_threshold=False,
                )
            )
            continue

        passes = item.confidence >= CONFIDENCE_THRESHOLD and item.classification != "unknown"
        if not passes and item.classification != "unknown" and item.confidence < UNKNOWN_MIN_CONFIDENCE:
            continue
        decisions.append(
            ClassificationDecision(
                fact_type=item.classification,
                confidence=item.confidence,
                reason=item.reason,
                destination=_route(item.classification, passes),
                passes_threshold=passes,
            )
        )

    return decisions


def _route(fact_type: str, passes_threshold: bool) -> str:
    if not passes_threshold:
        return "unknown_facts_queue"
    if fact_type in FACT_TYPES:
        return "extracted_facts"
    if fact_type in RULE_TYPES:
        return "business_rules"
    return "unknown_facts_queue"


def _get_provider() -> str:
    return os.getenv("MODEL_PROVIDER", "ollama")


def aggregate_chunk_status(decisions: list[ClassificationDecision]) -> str:
    if any(decision.passes_threshold for decision in decisions):
        return "classified"
    return "needs_review"
