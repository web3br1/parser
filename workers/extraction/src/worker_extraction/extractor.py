from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from hashlib import sha256

from model_gateway import get_model_gateway
from normalizers.pre_extract import pre_normalize
from schema_registry.validators import validate_extraction

from worker_extraction.prompt import get_extraction_prompt, get_prompt_version


@dataclass
class ExtractionOutput:
    fact_type: str
    status: str                    # "ok" | "failed" | "parse_failed" | "validation_failed"
    raw_data: dict                 # type: ignore[type-arg]
    validated_data: dict           # type: ignore[type-arg]
    normalized_content: dict       # type: ignore[type-arg]
    evidence_quote: str
    evidence_char_start: int | None
    evidence_char_end: int | None
    ambiguities: list[str]
    model_name: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    raw_response_hash: str
    validation_errors: list[str]
    is_multi: bool                 # True for business_hours (list of records)
    records: list[dict] = field(default_factory=list)  # type: ignore[type-arg]
    model_provider: str = "unknown"
    latency_ms: int = 0
    estimated_cost_usd: float = 0.0


def extract(
    chunk_text: str,
    fact_type: str,
    *,
    retry: bool = False,
) -> ExtractionOutput:
    """
    Calls the LLM and processes extraction for one fact_type.
    Never raises — errors are encapsulated in ExtractionOutput.status.
    Technical exceptions (API errors) are re-raised for the caller (tasks.py) to handle.
    """
    prompt_version = get_prompt_version(fact_type)
    prompt = get_extraction_prompt(fact_type, retry=retry)
    fallback_provider = os.getenv("MODEL_PROVIDER", "ollama")

    gateway = get_model_gateway()
    # Technical exceptions bubble up — caller decides on Celery retry
    response = gateway.extract(
        chunk_text=chunk_text,
        prompt_template=prompt,
        prompt_version=prompt_version,
    )

    raw_str = response.raw_response
    raw_hash = response.raw_response_hash or sha256(raw_str.encode()).hexdigest()
    model_provider = response.provider or fallback_provider

    try:
        parsed = json.loads(raw_str)
    except json.JSONDecodeError:
        return ExtractionOutput(
            fact_type=fact_type,
            status="parse_failed",
            raw_data={},
            validated_data={},
            normalized_content={},
            evidence_quote="",
            evidence_char_start=None,
            evidence_char_end=None,
            ambiguities=[],
            model_name=response.model_name,
            model_provider=model_provider,
            prompt_version=prompt_version,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            raw_response_hash=raw_hash,
            latency_ms=response.latency_ms,
            estimated_cost_usd=response.estimated_cost_usd,
            validation_errors=[],
            is_multi=False,
        )

    if parsed.get("status") == "failed":
        evidence = parsed.get("evidence_span") or {}
        return ExtractionOutput(
            fact_type=fact_type,
            status="failed",
            raw_data=parsed,
            validated_data={},
            normalized_content={},
            evidence_quote=evidence.get("quote", ""),
            evidence_char_start=None,
            evidence_char_end=None,
            ambiguities=parsed.get("ambiguities") or [],
            model_name=response.model_name,
            model_provider=model_provider,
            prompt_version=prompt_version,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            raw_response_hash=raw_hash,
            latency_ms=response.latency_ms,
            estimated_cost_usd=response.estimated_cost_usd,
            validation_errors=[],
            is_multi=False,
        )

    evidence = parsed.get("evidence_span") or {}
    raw_data = parsed.get("data") or {}
    if isinstance(raw_data, list):
        records = _process_multi(fact_type, raw_data)
        return ExtractionOutput(
            fact_type=fact_type,
            status="ok",
            raw_data=parsed,
            validated_data={},
            normalized_content={},
            evidence_quote=evidence.get("quote", ""),
            evidence_char_start=evidence.get("char_start"),
            evidence_char_end=evidence.get("char_end"),
            ambiguities=parsed.get("ambiguities") or [],
            model_name=response.model_name,
            model_provider=model_provider,
            prompt_version=prompt_version,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            raw_response_hash=raw_hash,
            latency_ms=response.latency_ms,
            estimated_cost_usd=response.estimated_cost_usd,
            validation_errors=[],
            is_multi=True,
            records=records,
        )

    # Single-record path
    pre_normalized = pre_normalize(fact_type, raw_data)
    vr = validate_extraction(fact_type, pre_normalized)
    if not vr.valid:
        return ExtractionOutput(
            fact_type=fact_type,
            status="validation_failed",
            raw_data=raw_data,
            validated_data={},
            normalized_content={},
            evidence_quote=evidence.get("quote", ""),
            evidence_char_start=evidence.get("char_start"),
            evidence_char_end=evidence.get("char_end"),
            ambiguities=parsed.get("ambiguities") or [],
            model_name=response.model_name,
            model_provider=model_provider,
            prompt_version=prompt_version,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            raw_response_hash=raw_hash,
            latency_ms=response.latency_ms,
            estimated_cost_usd=response.estimated_cost_usd,
            validation_errors=vr.errors,
            is_multi=False,
        )

    return ExtractionOutput(
        fact_type=fact_type,
        status="ok",
        raw_data=raw_data,
        validated_data=vr.data,
        normalized_content=vr.data,  # post-Pydantic is already the canonical form
        evidence_quote=evidence.get("quote", ""),
        evidence_char_start=evidence.get("char_start"),
        evidence_char_end=evidence.get("char_end"),
        ambiguities=parsed.get("ambiguities") or [],
        model_name=response.model_name,
        model_provider=model_provider,
        prompt_version=prompt_version,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        raw_response_hash=raw_hash,
        latency_ms=response.latency_ms,
        estimated_cost_usd=response.estimated_cost_usd,
        validation_errors=[],
        is_multi=False,
    )


def _process_multi(fact_type: str, items: list) -> list[dict]:  # type: ignore[type-arg]
    """For business_hours: pre-normalize and validate each item individually."""
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        pre = pre_normalize(fact_type, item)
        vr = validate_extraction(fact_type, pre)
        if vr.valid:
            results.append(vr.data)
    return results
