"""``run_grounding`` orchestrator (Task 7).

Joins the deterministic evidence check (Check A), the stakes config, the
re-grounding cache, and the independent entailment check (Check B) into a single
:class:`~grounding.types.GroundingResult` per claim.

Routing (see the design's "Failure Routing" and "Pipeline Placement"):

- Type not present in the active stakes config -> ``not_required``; Check B is
  skipped. (Check A still runs and is recorded.)
- Required type, Check A fails -> ``failed`` with reason
  ``grounding_evidence_not_literal``; Check B is skipped.
- Required type, Check A passes, Check B fails -> ``failed`` with reason
  ``grounding_entailment_failed``.
- Required type, Check B abstains -> ``abstained`` with reason
  ``grounding_abstained``.
- Required type, everything passes -> ``passed`` with reason
  ``grounding_passed``.
- Warn-only type -> overall status is never a hard fail. The deterministic and
  entailment sub-results are still recorded so review and publication gates can
  see the warning, but the item is not marked unreliable. Reason
  ``grounding_warn_only``.

Caching: Check B is deduplicated by :func:`grounding.cache.grounding_key`.
Check A ALWAYS runs, because it also validates offsets and source-local evidence
integrity for the current chunk (the cache key does not capture those).

This module never logs chunk text, claim payloads, or PII.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from model_gateway.base import EntailmentResponse, ModelRunConfig

from .cache import grounding_key
from .config import StakesConfigProvider, grounding_mode, load_stakes_config
from .entailment import verify_entailment_claim
from .evidence_check import verify_evidence
from .prompt import get_grounding_prompt_version
from .types import EntailmentResult, GroundingResult, GroundingStatus

# Failure / outcome reason codes (stable strings persisted on the result).
_REASON_NOT_REQUIRED = "grounding_not_required"
_REASON_EVIDENCE_NOT_LITERAL = "grounding_evidence_not_literal"
_REASON_ENTAILMENT_FAILED = "grounding_entailment_failed"
_REASON_ABSTAINED = "grounding_abstained"
_REASON_PASSED = "grounding_passed"
_REASON_WARN_ONLY = "grounding_warn_only"

# Model identifier used to compute the (pre-call) cache key when no
# ``ModelRunConfig`` is supplied. Keeping it stable keeps the cache deterministic.
_UNKNOWN_MODEL = "unknown"


@dataclass(frozen=True)
class EvidenceInput:
    """Check A inputs carried by a single extracted record.

    ``char_start``/``char_end`` are optional; when absent Check A falls back to
    substring matching and records the corresponding ``offset_status``.
    ``location`` is opaque source metadata handed to the verifier (never logged).
    """

    evidence_quote: str
    char_start: int | None = None
    char_end: int | None = None
    location: dict[str, Any] = field(default_factory=dict)


class _EntailmentGateway(Protocol):
    """Structural type for the slice of the gateway Check B needs."""

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
    ) -> EntailmentResponse: ...


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _model_for_key(config: ModelRunConfig | None) -> str:
    """Resolve the model identifier used in the pre-call cache key.

    The cache must dedup *before* invoking Check B, so the key cannot depend on
    the verifier response. We use the configured model when available.
    """
    if config is not None and getattr(config, "model", None):
        return config.model
    return _UNKNOWN_MODEL


def run_grounding(
    *,
    claim: dict[str, Any],
    fact_type: str,
    chunk_text: str,
    evidence: EvidenceInput,
    profile: str,
    gateway: _EntailmentGateway,
    cache: MutableMapping[str, EntailmentResult] | None = None,
    config: ModelRunConfig | None = None,
    config_provider: StakesConfigProvider | None = None,
) -> GroundingResult:
    """Run grounding (Check A + optional Check B) for a single claim.

    Returns a single :class:`GroundingResult`. Never raises on routing input;
    Check A is model-free and Check B is only invoked for configured types after
    Check A passes.
    """
    checked_at = _now_iso()
    stakes = load_stakes_config(profile, provider=config_provider)
    config_version = stakes.config_version
    mode = grounding_mode(fact_type, profile, provider=config_provider)
    required = mode == "required"

    # --- Check A (always runs) ---------------------------------------------
    det = verify_evidence(
        chunk_text,
        evidence.evidence_quote,
        evidence.char_start,
        evidence.char_end,
    )

    prompt_version = get_grounding_prompt_version()

    # --- Type not configured: never run Check B ----------------------------
    if mode == "not_configured":
        return GroundingResult(
            grounding_status="not_required",
            grounding_required=False,
            grounding_reason=_REASON_NOT_REQUIRED,
            deterministic_status=det.deterministic_status,
            deterministic_reason=det.deterministic_reason,
            match_mode=det.match_mode,
            offset_status=det.offset_status,
            entailment_status=None,
            entailment_reason=None,
            grounding_model=None,
            grounding_prompt_version=prompt_version,
            grounding_checked_at=checked_at,
            grounding_key=None,
            config_version=config_version,
        )

    # --- Check A failed -----------------------------------------------------
    # Check B is skipped: there is no verified literal evidence to entail.
    if det.deterministic_status == "failed":
        status: GroundingStatus
        if required:
            status = "failed"
            reason = _REASON_EVIDENCE_NOT_LITERAL
        else:
            # Warn-only: record the failure but do not mark the item unreliable.
            status = "passed"
            reason = _REASON_WARN_ONLY
        return GroundingResult(
            grounding_status=status,
            grounding_required=required,
            grounding_reason=reason,
            deterministic_status=det.deterministic_status,
            deterministic_reason=det.deterministic_reason,
            match_mode=det.match_mode,
            offset_status=det.offset_status,
            entailment_status=None,
            entailment_reason=None,
            grounding_model=None,
            grounding_prompt_version=prompt_version,
            grounding_checked_at=checked_at,
            grounding_key=None,
            config_version=config_version,
        )

    # --- Check A passed: run (or reuse cached) Check B ----------------------
    verified_quote = det.verified_quote or ""
    key = grounding_key(
        fact_type,
        claim,
        verified_quote,
        prompt_version,
        _model_for_key(config),
    )

    ent: EntailmentResult
    if cache is not None and key in cache:
        ent = cache[key]
    else:
        ent = verify_entailment_claim(
            gateway=gateway,
            claim_payload=claim,
            fact_type=fact_type,
            chunk_text=chunk_text,
            verified_quote=verified_quote,
            location=evidence.location,
            config=config,
        )
        if cache is not None:
            cache[key] = ent

    # --- Map combined outcome ----------------------------------------------
    final_status: GroundingStatus
    if not required:
        # Warn-only: record both sub-results, never a hard fail.
        final_status = "passed"
        reason = _REASON_WARN_ONLY
    elif ent.entailment_status == "passed":
        final_status = "passed"
        reason = _REASON_PASSED
    elif ent.entailment_status == "abstained":
        final_status = "abstained"
        reason = _REASON_ABSTAINED
    else:  # "failed"
        final_status = "failed"
        reason = _REASON_ENTAILMENT_FAILED

    return GroundingResult(
        grounding_status=final_status,
        grounding_required=required,
        grounding_reason=reason,
        deterministic_status=det.deterministic_status,
        deterministic_reason=det.deterministic_reason,
        match_mode=det.match_mode,
        offset_status=det.offset_status,
        entailment_status=ent.entailment_status,
        entailment_reason=ent.entailment_reason,
        grounding_model=ent.grounding_model,
        grounding_prompt_version=ent.grounding_prompt_version or prompt_version,
        grounding_checked_at=checked_at,
        grounding_key=key,
        config_version=config_version,
    )
