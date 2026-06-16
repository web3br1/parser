"""Stakes config loader (Task 2).

The list of types requiring hard grounding is *configuration*, not worker logic
(see the design's "Stakes Config" section). This module loads the default and
industrial profiles from ``stakes_config.json`` and exposes:

- ``load_stakes_config(profile)`` -> :class:`StakesConfig`
- ``grounding_mode(fact_type, profile)`` -> ``"required" | "warn_only" | "not_configured"``
- ``config_version()`` -> the version string used by the re-grounding cache.

Loading goes through the small :class:`StakesConfigProvider` protocol so that
tenant or vertical adapters can replace the source of truth without editing any
worker code. Unknown profiles fall back to ``"default"``.

Pure, model-free.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

# Result of resolving a fact/rule type against the active stakes config.
GroundingMode = Literal["required", "warn_only", "not_configured"]

_DEFAULT_PROFILE = "default"

_CONFIG_PATH = Path(__file__).with_name("stakes_config.json")


@dataclass(frozen=True)
class StakesConfig:
    """Resolved stakes configuration for a single profile.

    ``required_grounding_types`` and ``warn_only_grounding_types`` are sets for
    cheap membership tests. ``config_version`` participates in re-grounding
    invalidation just like the prompt version and model.
    """

    profile: str
    required_grounding_types: frozenset[str]
    warn_only_grounding_types: frozenset[str]
    config_version: str


@runtime_checkable
class StakesConfigProvider(Protocol):
    """Replaceable source of stakes configuration.

    Adapters (per-tenant, per-vertical) implement ``load`` to override the
    default JSON-backed config without changing worker code.
    """

    def load(self, profile: str) -> StakesConfig:  # pragma: no cover - protocol
        ...


@lru_cache(maxsize=1)
def _raw_config() -> dict[str, Any]:
    with _CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data


class DefaultStakesConfigProvider:
    """Default provider: reads ``stakes_config.json`` shipped with the package.

    Unknown profiles fall back to the ``"default"`` profile so the worker always
    receives a usable config.
    """

    def load(self, profile: str) -> StakesConfig:
        raw = _raw_config()
        profiles = raw.get("profiles", {})
        resolved = profile if profile in profiles else _DEFAULT_PROFILE
        entry = profiles[resolved]
        return StakesConfig(
            profile=resolved,
            required_grounding_types=frozenset(entry.get("required_grounding_types", [])),
            warn_only_grounding_types=frozenset(entry.get("warn_only_grounding_types", [])),
            config_version=str(raw.get("config_version", "")),
        )


# Module-level default provider used when no override is supplied.
_DEFAULT_PROVIDER: StakesConfigProvider = DefaultStakesConfigProvider()


def load_stakes_config(
    profile: str = _DEFAULT_PROFILE,
    *,
    provider: StakesConfigProvider | None = None,
) -> StakesConfig:
    """Load the resolved stakes config for ``profile``.

    Unknown profiles fall back to ``"default"``. Pass ``provider`` to use an
    adapter-supplied configuration source.
    """
    active = provider if provider is not None else _DEFAULT_PROVIDER
    return active.load(profile)


def grounding_mode(
    fact_type: str,
    profile: str = _DEFAULT_PROFILE,
    *,
    provider: StakesConfigProvider | None = None,
) -> GroundingMode:
    """Resolve the grounding mode for ``fact_type`` under ``profile``.

    Returns ``"required"`` if the type demands hard grounding, ``"warn_only"``
    if grounding warnings should be surfaced but not block, or
    ``"not_configured"`` if the type is absent from the active config.
    """
    cfg = load_stakes_config(profile, provider=provider)
    if fact_type in cfg.required_grounding_types:
        return "required"
    if fact_type in cfg.warn_only_grounding_types:
        return "warn_only"
    return "not_configured"


def config_version(*, provider: StakesConfigProvider | None = None) -> str:
    """Return the stakes config version for the default profile."""
    return load_stakes_config(_DEFAULT_PROFILE, provider=provider).config_version
