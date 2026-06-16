from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# --- Status literals --------------------------------------------------------

# Deterministic evidence check (Check A) outcome.
DeterministicStatus = Literal["passed", "failed"]

# Match strategy used by Check A. "fuzzy" is reserved for future OCR/WhatsApp
# modality support and is not implemented in this slice.
MatchMode = Literal["exact", "normalized", "fuzzy"]

# How offsets were resolved during Check A.
OffsetStatus = Literal[
    "offsets_verified",
    "substring_without_offsets",
    "ambiguous_substring_without_offsets",
    "no_match",
]

# Independent entailment check (Check B) outcome.
EntailmentStatus = Literal["passed", "failed", "abstained"]

# Overall grounding outcome persisted for an extracted record.
GroundingStatus = Literal["not_required", "passed", "failed", "abstained"]


# --- Deterministic evidence (Check A) result --------------------------------


@dataclass(frozen=True)
class DeterministicResult:
    """Result of the deterministic evidence check (Check A).

    Pure, model-free. Proves that ``evidence_quote`` is literal source text
    inside ``chunk_text`` after typographic normalization.
    """

    deterministic_status: DeterministicStatus
    deterministic_reason: str
    match_mode: MatchMode | None
    offset_status: OffsetStatus
    verified_quote: str | None
    char_start: int | None
    char_end: int | None


# --- Independent entailment (Check B) result --------------------------------


@dataclass(frozen=True)
class EntailmentResult:
    """Result of the independent entailment check (Check B)."""

    entailment_status: EntailmentStatus
    entailment_reason: str
    grounding_model: str | None
    grounding_prompt_version: str | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None


# --- Combined persisted grounding result ------------------------------------


@dataclass(frozen=True)
class GroundingResult:
    """Every field persisted for a grounding evaluation.

    Mirrors the "Persistence" section of the grounding worker design plus the
    deterministic and entailment sub-fields and the re-grounding cache key.
    """

    grounding_status: GroundingStatus
    grounding_required: bool
    grounding_reason: str

    # Deterministic (Check A) sub-fields.
    deterministic_status: DeterministicStatus | None
    deterministic_reason: str | None
    match_mode: MatchMode | None
    offset_status: OffsetStatus | None

    # Entailment (Check B) sub-fields.
    entailment_status: EntailmentStatus | None
    entailment_reason: str | None

    # Verifier provenance.
    grounding_model: str | None
    grounding_prompt_version: str | None
    grounding_checked_at: str | None

    # Re-grounding cache + config versioning.
    grounding_key: str | None
    config_version: str | None
