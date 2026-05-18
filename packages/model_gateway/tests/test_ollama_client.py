import json
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest
from model_gateway import ModelRunConfig, get_model_gateway
from model_gateway.ollama_client import OllamaModelGateway


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


@contextmanager
def capture_urlopen(calls: list[dict[str, Any]], payload: dict[str, Any]):
    def fake_urlopen(request, timeout: float):  # noqa: ANN001
        calls.append({
            "url": request.full_url,
            "headers": dict(request.header_items()),
            "body": json.loads(request.data.decode()),
            "timeout": timeout,
        })
        return FakeHTTPResponse(payload)

    with patch("model_gateway.ollama_client.urlopen", fake_urlopen):
        yield


def test_get_model_gateway_selects_ollama(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")

    assert isinstance(get_model_gateway(), OllamaModelGateway)


def test_get_model_gateway_defaults_to_ollama(monkeypatch) -> None:
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)

    assert isinstance(get_model_gateway(), OllamaModelGateway)


def test_classify_calls_ollama_generate_with_json_format(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("CLASSIFICATION_MODEL", "gemma4:31b")
    calls: list[dict[str, Any]] = []
    raw = (
        '{"classifications":[{"classification":"service_price",'
        '"confidence":0.91,"reason":"preco explicito"}]}'
    )

    with capture_urlopen(
        calls,
        {
            "response": raw,
            "prompt_eval_count": 13,
            "eval_count": 7,
        },
    ):
        result = OllamaModelGateway().classify(
            "Servico R$ 120",
            "Classifique: {chunk_text}",
            "prompt-v1",
        )

    assert result.model_name == "gemma4:31b"
    assert result.prompt_version == "prompt-v1"
    assert result.input_tokens == 13
    assert result.output_tokens == 7
    assert result.classifications[0].classification == "service_price"
    assert calls[0]["url"] == "http://localhost:11434/api/generate"
    assert calls[0]["body"]["model"] == "gemma4:31b"
    assert calls[0]["body"]["prompt"] == "Classifique: Servico R$ 120"
    assert calls[0]["body"]["format"] == "json"
    assert calls[0]["body"]["stream"] is False
    assert calls[0]["body"]["options"]["temperature"] == 0
    assert result.provider == "ollama"
    assert result.model == "gemma4:31b"
    assert result.latency_ms >= 0
    assert len(result.raw_response_hash) == 64


def test_ollama_sets_num_predict(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    calls: list[dict[str, Any]] = []
    config = ModelRunConfig(
        provider="ollama",
        model="gemma-test",
        max_output_tokens=700,
        timeout_seconds=12,
    )

    with capture_urlopen(calls, {"response": '{"classifications":[]}'}):
        OllamaModelGateway().classify("texto", "{chunk_text}", "prompt-v1", config=config)

    assert calls[0]["body"]["model"] == "gemma-test"
    assert calls[0]["body"]["options"]["num_predict"] == 700
    assert calls[0]["timeout"] == 12


def test_classify_malformed_json_raises_parse_failed(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("CLASSIFICATION_MODEL", "gemma4:31b")

    with capture_urlopen([], {"response": "{bad"}):
        with pytest.raises(ValueError, match="classification_parse_failed:"):
            OllamaModelGateway().classify("texto", "{chunk_text}", "prompt-v1")


def test_classify_skips_malformed_items_and_preserves_raw_response(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("CLASSIFICATION_MODEL", "gemma4:31b")
    raw = json.dumps({
        "classifications": [
            {"confidence": 0.91, "reason": "missing type"},
            "not-an-object",
            {"classification": "service_price", "confidence": 0.88},
        ]
    })

    with capture_urlopen([], {"response": raw}):
        result = OllamaModelGateway().classify("texto", "{chunk_text}", "prompt-v1")

    assert result.raw_response == raw
    assert len(result.classifications) == 1
    assert result.classifications[0].classification == "service_price"
    assert result.classifications[0].reason == ""


def test_classify_all_malformed_items_returns_empty_classifications(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("CLASSIFICATION_MODEL", "gemma4:31b")
    raw = '{"classifications":[{"confidence":0.91}, "bad"]}'

    with capture_urlopen([], {"response": raw}):
        result = OllamaModelGateway().classify("texto", "{chunk_text}", "prompt-v1")

    assert result.raw_response == raw
    assert result.classifications == []


def test_extract_uses_extraction_model_and_returns_raw_json(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/")
    monkeypatch.setenv(
        "EXTRACTION_MODEL",
        "kwangsuklee/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:latest",
    )
    calls: list[dict[str, Any]] = []
    raw = '{"status":"ok","data":{},"evidence_span":{"quote":""},"ambiguities":[]}'

    with capture_urlopen(calls, {"response": raw}):
        result = OllamaModelGateway().extract("texto", "Extraia: {chunk_text}", "prompt-v2")

    assert result.model_name == (
        "kwangsuklee/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:latest"
    )
    assert result.prompt_version == "prompt-v2"
    assert result.input_tokens == 0
    assert result.output_tokens == 0
    assert result.raw_response == raw
    assert calls[0]["url"] == "http://localhost:11434/api/generate"
    assert calls[0]["body"]["model"] == (
        "kwangsuklee/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:latest"
    )


def test_extract_defaults_to_benchmark_winner_when_env_is_missing(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.delenv("EXTRACTION_MODEL", raising=False)
    calls: list[dict[str, Any]] = []

    with capture_urlopen(calls, {"response": "{}"}):
        OllamaModelGateway().extract("texto", "{chunk_text}", "prompt-v1")

    assert calls[0]["body"]["model"] == (
        "hf.co/hesamation/Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:Q4_K_M"
    )
