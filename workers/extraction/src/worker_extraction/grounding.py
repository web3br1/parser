"""Grounding adapter for the extraction worker (TASK-040, Task 8).

Thin glue between :mod:`worker_extraction.tasks` and the ``grounding`` package.
It builds the claim payload and Check A inputs from an :class:`ExtractionOutput`
plus the evidence span, runs :func:`grounding.run_grounding`, and converts the
:class:`grounding.GroundingResult` into the jsonb payload expected by the
``complete_extraction_job`` RPC.

Grounding runs only when the ``GROUNDING_ENABLED`` flag is set; default OFF
preserves the worker's prior behavior exactly. The stage is warn-only: only
required-grounding types can route a record to review, and that decision is made
by the runner (``grounding_required`` + ``grounding_status``), not here.

This module never logs chunk text, claim payloads, or PII.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

from grounding import EvidenceInput, GroundingResult, run_grounding
from model_gateway import get_model_gateway

from worker_extraction.evidence import EvidenceSpanInput
from worker_extraction.extractor import ExtractionOutput

_TRUE_VALUES = {"1", "true", "yes", "on"}


def grounding_enabled() -> bool:
    """True when the ``GROUNDING_ENABLED`` flag opts this worker into grounding."""
    return os.getenv("GROUNDING_ENABLED", "").strip().lower() in _TRUE_VALUES


def grounding_profile() -> str:
    """Active stakes-config profile (``default`` unless overridden)."""
    return os.getenv("GROUNDING_PROFILE", "default").strip() or "default"


def build_claim(output: ExtractionOutput, destination: str) -> dict[str, Any]:
    """Build the structured claim payload grounding evaluates.

    The claim is the normalized, post-validation content - never the extractor's
    rationale or prompt internals. Multi-record facts (e.g. business_hours) are
    warn-only, so a representative envelope is sufficient for routing.
    """
    if output.is_multi:
        return {"records": output.records}
    if destination == "business_rules":
        return {
            "condition": output.validated_data.get("condition") or {},
            "action": output.validated_data.get("action") or {},
        }
    return output.normalized_content or output.raw_data or {}


def _location(span_input: EvidenceSpanInput) -> dict[str, Any]:
    return {
        "page_number": span_input.page_number,
        "sheet_name": span_input.sheet_name,
        "row_number": span_input.row_number,
    }


def evaluate_for_extraction(
    *,
    output: ExtractionOutput,
    fact_type: str,
    destination: str,
    chunk_text: str,
    span_input: EvidenceSpanInput | None,
) -> GroundingResult:
    """Run grounding for one extracted candidate and return its result.

    When the evidence span is absent the candidate has no literal evidence to
    ground; Check A fails on the empty quote, which the runner routes per stakes.
    """
    evidence = EvidenceInput(
        evidence_quote="" if span_input is None else span_input.quote,
        char_start=None if span_input is None else span_input.char_start,
        char_end=None if span_input is None else span_input.char_end,
        location={} if span_input is None else _location(span_input),
    )
    return run_grounding(
        claim=build_claim(output, destination),
        fact_type=fact_type,
        chunk_text=chunk_text,
        evidence=evidence,
        profile=grounding_profile(),
        gateway=get_model_gateway(),
    )


def blocks_record(result: GroundingResult) -> bool:
    """True when a required-grounding result must route the record to review."""
    return result.grounding_required and result.grounding_status in ("failed", "abstained")


def to_payload(result: GroundingResult) -> dict[str, Any]:
    """Convert the result to the jsonb payload for ``complete_extraction_job``.

    Every key maps directly to a ``grounding_results`` column. ``fact_id`` /
    ``rule_id`` are left unset; the RPC inserts the row in the same transaction
    as the candidate but does not yet back-link the generated id.
    """
    return asdict(result)
