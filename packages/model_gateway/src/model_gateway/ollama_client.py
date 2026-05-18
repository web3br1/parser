import json
import os
from hashlib import sha256
from time import perf_counter
from typing import Any
from urllib.request import Request, urlopen

from model_gateway.base import (
    ClassificationItem,
    ClassificationResponse,
    ExtractionResponse,
    ModelGatewayBase,
    ModelRunConfig,
)


class OllamaModelGateway(ModelGatewayBase):
    def __init__(
        self,
        *,
        base_url: str | None = None,
        classification_model: str | None = None,
        extraction_model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._base_url = str(base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip(
            "/"
        )
        self._classification_model = str(classification_model or os.getenv(
            "CLASSIFICATION_MODEL",
            "gemma4:31b",
        ))
        self._extraction_model = str(extraction_model or os.getenv(
            "EXTRACTION_MODEL",
            "hf.co/hesamation/Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:Q4_K_M",
        ))
        self._timeout_seconds = timeout_seconds or float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))

    def classify(
        self,
        chunk_text: str,
        prompt_template: str,
        prompt_version: str,
        config: ModelRunConfig | None = None,
    ) -> ClassificationResponse:
        run_config = config or self._default_config(self._classification_model)
        _ensure_ollama(run_config)
        prompt = prompt_template.replace("{chunk_text}", chunk_text)
        started = perf_counter()
        response = self._generate(prompt=prompt, config=run_config)
        latency_ms = _latency_ms(started)
        raw_response = str(response.get("response") or "{}")
        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise ValueError(f"classification_parse_failed: {raw_response[:200]}") from exc

        items = []
        for raw_item in parsed.get("classifications", []):
            if not isinstance(raw_item, dict) or "classification" not in raw_item:
                continue
            items.append(
                ClassificationItem(
                    classification=raw_item["classification"],
                    confidence=float(raw_item.get("confidence", 0.0)),
                    reason=raw_item.get("reason", ""),
                )
            )
        input_tokens = _token_count(response, "prompt_eval_count")
        output_tokens = _token_count(response, "eval_count")
        return ClassificationResponse(
            classifications=items,
            model_name=run_config.model,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw_response=raw_response,
            provider=run_config.provider,
            model=run_config.model,
            latency_ms=latency_ms,
            raw_response_hash=sha256(raw_response.encode()).hexdigest(),
            estimated_cost_usd=0.0,
        )

    def extract(
        self,
        chunk_text: str,
        prompt_template: str,
        prompt_version: str,
        config: ModelRunConfig | None = None,
    ) -> ExtractionResponse:
        run_config = config or self._default_config(self._extraction_model)
        _ensure_ollama(run_config)
        prompt = prompt_template.replace("{chunk_text}", chunk_text)
        started = perf_counter()
        response = self._generate(prompt=prompt, config=run_config)
        latency_ms = _latency_ms(started)
        raw = str(response.get("response") or "{}")
        input_tokens = _token_count(response, "prompt_eval_count")
        output_tokens = _token_count(response, "eval_count")
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
            estimated_cost_usd=0.0,
        )

    def _generate(self, *, prompt: str, config: ModelRunConfig) -> dict[str, Any]:
        payload = {
            "model": config.model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": config.temperature,
                "num_predict": config.max_output_tokens,
            },
        }
        request = Request(
            f"{self._base_url}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=config.timeout_seconds) as response:
            body = response.read().decode()
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise ValueError("ollama_response_not_object")
        return parsed

    def _default_config(self, model: str) -> ModelRunConfig:
        return ModelRunConfig(
            provider="ollama",
            model=model,
            temperature=float(os.getenv("MODEL_TEMPERATURE", "0")),
            max_output_tokens=int(os.getenv("MODEL_MAX_OUTPUT_TOKENS", "2048")),
            timeout_seconds=self._timeout_seconds,
        )


def _token_count(response: dict[str, Any], key: str) -> int:
    value = response.get(key)
    return value if isinstance(value, int) else 0


def _ensure_ollama(config: ModelRunConfig) -> None:
    if config.provider != "ollama":
        raise ValueError(f"ollama_gateway_config_provider_mismatch: {config.provider}")


def _latency_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))
