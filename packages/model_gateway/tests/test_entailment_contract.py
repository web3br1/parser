import inspect
import json
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from typing import Any
from unittest.mock import patch

import pytest
from model_gateway.base import EntailmentResponse, ModelGatewayBase
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


def test_verify_entailment_is_abstract_on_base() -> None:
    assert hasattr(ModelGatewayBase, "verify_entailment")
    assert getattr(
        ModelGatewayBase.verify_entailment, "__isabstractmethod__", False
    ) is True


def test_verify_entailment_signature_has_no_extractor_internals() -> None:
    params = set(inspect.signature(ModelGatewayBase.verify_entailment).parameters)
    expected = {
        "self",
        "claim_payload",
        "fact_type",
        "chunk_text",
        "verified_quote",
        "location",
        "prompt_template",
        "prompt_version",
        "config",
    }
    assert params == expected
    # The verifier must be independent of the extractor. No leakage fields.
    forbidden_fragments = (
        "rationale",
        "chain_of_thought",
        "cot",
        "reasoning",
        "prompt_internal",
        "self_confidence",
        "extractor",
        "confidence",
    )
    for name in params:
        for fragment in forbidden_fragments:
            assert fragment not in name, f"forbidden param fragment: {name}"


def test_entailment_response_mirrors_extraction_response_fields() -> None:
    fields = set(EntailmentResponse.__dataclass_fields__)
    expected = {
        "model_name",
        "prompt_version",
        "input_tokens",
        "output_tokens",
        "raw_response",
        "provider",
        "model",
        "latency_ms",
        "raw_response_hash",
        "estimated_cost_usd",
    }
    assert fields == expected


def test_entailment_response_is_frozen() -> None:
    response = EntailmentResponse(
        model_name="m",
        prompt_version="v",
        input_tokens=1,
        output_tokens=2,
        raw_response="{}",
    )
    with pytest.raises(FrozenInstanceError):
        response.model_name = "other"  # type: ignore[misc]


def test_ollama_verify_entailment_returns_entailment_response(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("GROUNDING_MODEL", "grounding-test")
    calls: list[dict[str, Any]] = []
    raw = '{"entailment_status":"passed","reason":"supported by source"}'

    with capture_urlopen(
        calls,
        {"response": raw, "prompt_eval_count": 21, "eval_count": 9},
    ):
        result = OllamaModelGateway().verify_entailment(
            claim_payload={"amount": "120.00", "currency": "BRL"},
            fact_type="service_price",
            chunk_text="O servico custa R$ 120,00.",
            verified_quote="R$ 120,00",
            location={"page": 1, "char_start": 13, "char_end": 22},
            prompt_template="Claim: {claim_payload}\nQuote: {verified_quote}\nChunk: {chunk_text}",
            prompt_version="grounding-v1",
        )

    assert isinstance(result, EntailmentResponse)
    assert result.model_name == "grounding-test"
    assert result.model == "grounding-test"
    assert result.provider == "ollama"
    assert result.prompt_version == "grounding-v1"
    assert result.input_tokens == 21
    assert result.output_tokens == 9
    assert result.raw_response == raw
    assert result.latency_ms >= 0
    assert len(result.raw_response_hash) == 64
    assert result.estimated_cost_usd == 0.0


def test_ollama_verify_entailment_uses_temperature_zero(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    calls: list[dict[str, Any]] = []

    with capture_urlopen(calls, {"response": '{"entailment_status":"abstained"}'}):
        OllamaModelGateway().verify_entailment(
            claim_payload={"x": 1},
            fact_type="business_rules",
            chunk_text="texto",
            verified_quote="texto",
            location={},
            prompt_template="{chunk_text}",
            prompt_version="grounding-v1",
        )

    assert calls[0]["url"] == "http://localhost:11434/api/generate"
    assert calls[0]["body"]["format"] == "json"
    assert calls[0]["body"]["stream"] is False
    assert calls[0]["body"]["options"]["temperature"] == 0
