import json
import os
from hashlib import sha256
from time import perf_counter
from typing import Any

from openai import OpenAI

from model_gateway.base import (
    ClassificationItem,
    ClassificationResponse,
    EntailmentResponse,
    ExtractionResponse,
    ModelGatewayBase,
    ModelRunConfig,
    render_entailment_prompt,
)

CLASSIFICATION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "classification": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["classification", "confidence", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["classifications"],
    "additionalProperties": False,
}


class OpenAIModelGateway(ModelGatewayBase):
    def __init__(self, model: str | None = None) -> None:
        self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self._model = model or os.environ["CLASSIFICATION_MODEL"]

    def classify(
        self,
        chunk_text: str,
        prompt_template: str,
        prompt_version: str,
        config: ModelRunConfig | None = None,
    ) -> ClassificationResponse:
        run_config = config or _default_config(self._model)
        _ensure_openai(run_config)
        prompt = prompt_template.replace("{chunk_text}", chunk_text)
        started = perf_counter()
        response = self._client.chat.completions.create(
            model=run_config.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "classification_response",
                    "strict": True,
                    "schema": CLASSIFICATION_JSON_SCHEMA,
                },
            },
            temperature=run_config.temperature,
            max_completion_tokens=run_config.max_output_tokens,
            timeout=run_config.timeout_seconds,
        )
        latency_ms = _latency_ms(started)

        raw = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"classification_parse_failed: {raw[:200]}") from exc

        items = [
            ClassificationItem(
                classification=item["classification"],
                confidence=float(item["confidence"]),
                reason=item["reason"],
            )
            for item in parsed.get("classifications", [])
        ]

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        return ClassificationResponse(
            classifications=items,
            model_name=run_config.model,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw_response=raw,
            provider=run_config.provider,
            model=run_config.model,
            latency_ms=latency_ms,
            raw_response_hash=sha256(raw.encode()).hexdigest(),
            estimated_cost_usd=_estimated_cost_usd(run_config.model, input_tokens, output_tokens),
        )

    def extract(
        self,
        chunk_text: str,
        prompt_template: str,
        prompt_version: str,
        config: ModelRunConfig | None = None,
    ) -> ExtractionResponse:
        """
        Calls the LLM for structured extraction using json_object mode.
        json_schema strict is not used here because output structure varies per fact_type.
        Pydantic validation in the worker handles structural correctness.
        """
        model = os.environ.get("EXTRACTION_MODEL", "gpt-4o")
        run_config = config or _default_config(model)
        _ensure_openai(run_config)
        prompt = prompt_template.replace("{chunk_text}", chunk_text)
        started = perf_counter()
        response = self._client.chat.completions.create(
            model=run_config.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=run_config.temperature,
            max_completion_tokens=run_config.max_output_tokens,
            timeout=run_config.timeout_seconds,
        )
        latency_ms = _latency_ms(started)
        raw = response.choices[0].message.content or "{}"
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        return ExtractionResponse(
            model_name=run_config.model,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw_response=raw,
            provider=run_config.provider,
            model=run_config.model,
            latency_ms=latency_ms,
            raw_response_hash=sha256(raw.encode()).hexdigest(),
            estimated_cost_usd=_estimated_cost_usd(run_config.model, input_tokens, output_tokens),
        )


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
        """Native independent entailment verification (grounding Check B).

        Uses json_object response format at temperature 0. The verifier only
        receives grounding inputs and never extractor rationale, prompt
        internals, or self-reported confidence.
        """
        model = os.environ.get("GROUNDING_MODEL", os.environ.get("EXTRACTION_MODEL", "gpt-4o"))
        run_config = config or _default_config(model)
        _ensure_openai(run_config)
        prompt = render_entailment_prompt(
            prompt_template,
            claim_payload=claim_payload,
            fact_type=fact_type,
            chunk_text=chunk_text,
            verified_quote=verified_quote,
            location=location,
        )
        started = perf_counter()
        response = self._client.chat.completions.create(
            model=run_config.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=run_config.temperature,
            max_completion_tokens=run_config.max_output_tokens,
            timeout=run_config.timeout_seconds,
        )
        latency_ms = _latency_ms(started)
        raw = response.choices[0].message.content or "{}"
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        return EntailmentResponse(
            model_name=run_config.model,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw_response=raw,
            provider=run_config.provider,
            model=run_config.model,
            latency_ms=latency_ms,
            raw_response_hash=sha256(raw.encode()).hexdigest(),
            estimated_cost_usd=_estimated_cost_usd(run_config.model, input_tokens, output_tokens),
        )


def _default_config(model: str) -> ModelRunConfig:
    return ModelRunConfig(
        provider="openai",
        model=model,
        temperature=float(os.getenv("MODEL_TEMPERATURE", "0")),
        max_output_tokens=int(os.getenv("MODEL_MAX_OUTPUT_TOKENS", "1024")),
        timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60")),
        allow_external_provider=True,
    )


def _ensure_openai(config: ModelRunConfig) -> None:
    if config.provider != "openai":
        raise ValueError(f"openai_gateway_config_provider_mismatch: {config.provider}")


def _latency_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


def _estimated_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = {
        "gpt-4o": (0.0000025, 0.00001),
        "gpt-4o-mini": (0.00000015, 0.0000006),
    }
    input_rate, output_rate = rates.get(model, (0.0, 0.0))
    return round(input_tokens * input_rate + output_tokens * output_rate, 8)
