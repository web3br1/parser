from model_gateway.base import (
    ClassificationResponse,
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
