from types import SimpleNamespace
from unittest.mock import patch

import pytest
from model_gateway import ModelRunConfig
from model_gateway.openai_client import OpenAIModelGateway


def _response(raw: str, prompt_tokens: int = 7, completion_tokens: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=raw))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


@patch("model_gateway.openai_client.OpenAI")
def test_valid_response_returns_classification(mock_openai, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFICATION_MODEL", "test-model")
    raw = (
        '{"classifications":[{"classification":"service_price",'
        '"confidence":0.91,"reason":"preço explícito"}]}'
    )
    create = mock_openai.return_value.chat.completions.create
    create.return_value = _response(raw)

    gateway = OpenAIModelGateway()
    result = gateway.classify("Serviço R$ 120", "{chunk_text}", "prompt-v1")

    assert result.model_name == "test-model"
    assert result.prompt_version == "prompt-v1"
    assert result.input_tokens == 7
    assert result.output_tokens == 3
    assert result.raw_response == raw
    assert result.classifications[0].classification == "service_price"
    assert result.classifications[0].confidence == 0.91
    assert isinstance(result.classifications[0].confidence, float)


@patch("model_gateway.openai_client.OpenAI")
def test_malformed_json_raises_parse_failed(mock_openai, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFICATION_MODEL", "test-model")
    mock_openai.return_value.chat.completions.create.return_value = _response("{bad")

    gateway = OpenAIModelGateway()

    with pytest.raises(ValueError, match="classification_parse_failed:"):
        gateway.classify("texto", "{chunk_text}", "prompt-v1")


@patch("model_gateway.openai_client.OpenAI")
def test_empty_classifications_is_allowed(mock_openai, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFICATION_MODEL", "test-model")
    mock_openai.return_value.chat.completions.create.return_value = _response(
        '{"classifications":[]}'
    )

    result = OpenAIModelGateway().classify("texto", "{chunk_text}", "prompt-v1")

    assert result.classifications == []


@patch("model_gateway.openai_client.OpenAI")
def test_temperature_zero_is_passed(mock_openai, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFICATION_MODEL", "test-model")
    mock_openai.return_value.chat.completions.create.return_value = _response(
        '{"classifications":[]}'
    )

    OpenAIModelGateway().classify("texto", "{chunk_text}", "prompt-v1")

    assert mock_openai.return_value.chat.completions.create.call_args.kwargs["temperature"] == 0


@patch("model_gateway.openai_client.OpenAI")
def test_openai_classification_sends_max_output_tokens(mock_openai, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFICATION_MODEL", "test-model")
    mock_openai.return_value.chat.completions.create.return_value = _response(
        '{"classifications":[]}'
    )
    config = ModelRunConfig(
        provider="openai",
        model="gpt-test",
        max_output_tokens=700,
        timeout_seconds=12,
    )

    OpenAIModelGateway().classify("texto", "{chunk_text}", "prompt-v1", config=config)

    request = mock_openai.return_value.chat.completions.create.call_args.kwargs
    assert request["model"] == "gpt-test"
    assert request["max_completion_tokens"] == 700
    assert request["timeout"] == 12


@patch("model_gateway.openai_client.OpenAI")
def test_openai_response_includes_audit_metadata(mock_openai, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFICATION_MODEL", "test-model")
    raw = '{"classifications":[]}'
    mock_openai.return_value.chat.completions.create.return_value = _response(raw)

    result = OpenAIModelGateway().classify("texto", "{chunk_text}", "prompt-v1")

    assert result.provider == "openai"
    assert result.model == "test-model"
    assert result.latency_ms >= 0
    assert len(result.raw_response_hash) == 64
