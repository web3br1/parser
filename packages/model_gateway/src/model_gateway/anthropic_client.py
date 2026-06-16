from typing import Any

from model_gateway.base import (
    ClassificationResponse,
    EntailmentResponse,
    ExtractionResponse,
    ModelGatewayBase,
    ModelRunConfig,
)


class AnthropicModelGateway(ModelGatewayBase):
    def classify(
        self,
        chunk_text: str,
        prompt_template: str,
        prompt_version: str,
        config: ModelRunConfig | None = None,
    ) -> ClassificationResponse:
        raise NotImplementedError("AnthropicModelGateway.classify nao implementado.")

    def extract(
        self,
        chunk_text: str,
        prompt_template: str,
        prompt_version: str,
        config: ModelRunConfig | None = None,
    ) -> ExtractionResponse:
        raise NotImplementedError("AnthropicModelGateway.extract nao implementado.")

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
        raise NotImplementedError("AnthropicModelGateway.verify_entailment nao implementado.")
