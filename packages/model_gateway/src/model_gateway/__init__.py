import os

from model_gateway.base import (
    ClassificationItem,
    ClassificationResponse,
    EntailmentResponse,
    ExtractionResponse,
    ModelGatewayBase,
    ModelProvider,
    ModelRunConfig,
)


def get_model_gateway(provider: str | None = None) -> ModelGatewayBase:
    selected_provider = provider or os.getenv("MODEL_PROVIDER", "ollama")
    if selected_provider == "ollama":
        from model_gateway.ollama_client import OllamaModelGateway

        return OllamaModelGateway()
    if selected_provider == "openai":
        from model_gateway.openai_client import OpenAIModelGateway

        return OpenAIModelGateway()
    if selected_provider == "anthropic":
        from model_gateway.anthropic_client import AnthropicModelGateway

        return AnthropicModelGateway()
    raise ValueError(f"Unknown model provider: {selected_provider!r}")


__all__ = [
    "ClassificationItem",
    "ClassificationResponse",
    "EntailmentResponse",
    "ExtractionResponse",
    "ModelGatewayBase",
    "ModelProvider",
    "ModelRunConfig",
    "get_model_gateway",
]
