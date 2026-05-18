from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


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
