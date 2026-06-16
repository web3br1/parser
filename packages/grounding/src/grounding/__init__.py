"""Grounding package public API.

The grounding stage promotes ``parse_artifact_created -> truth_evaluated`` with
two checks, always in this order:

1. :func:`verify_evidence` - deterministic, model-free evidence check (Check A).
2. independent entailment check (Check B), run by :func:`run_grounding` only for
   configured types after Check A passes.

See ``docs/03-pipeline/GROUNDING_WORKER.md`` for the design of record.
"""

from __future__ import annotations

from .config import (
    GroundingMode,
    StakesConfig,
    StakesConfigProvider,
    config_version,
    grounding_mode,
    load_stakes_config,
)
from .evidence_check import verify_evidence
from .prompt import get_grounding_prompt_version
from .runner import EvidenceInput, run_grounding
from .types import (
    DeterministicResult,
    DeterministicStatus,
    EntailmentResult,
    EntailmentStatus,
    GroundingResult,
    GroundingStatus,
    MatchMode,
    OffsetStatus,
)

__all__ = [
    # Orchestrator + inputs.
    "run_grounding",
    "EvidenceInput",
    # Check A.
    "verify_evidence",
    # Stakes config.
    "load_stakes_config",
    "grounding_mode",
    "config_version",
    "GroundingMode",
    "StakesConfig",
    "StakesConfigProvider",
    # Prompt provenance.
    "get_grounding_prompt_version",
    # Result + status types.
    "GroundingResult",
    "GroundingStatus",
    "DeterministicResult",
    "DeterministicStatus",
    "EntailmentResult",
    "EntailmentStatus",
    "MatchMode",
    "OffsetStatus",
]
