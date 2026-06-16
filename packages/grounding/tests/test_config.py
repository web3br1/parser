"""Tests for the stakes config loader (Task 2).

Covers the default + industrial profiles from the design's "Stakes Config"
section, the ``grounding_mode`` lookup, unknown-profile fallback, the exposed
``config_version``, and the replaceable ``StakesConfigProvider`` protocol.
"""

from __future__ import annotations

from grounding.config import (
    DefaultStakesConfigProvider,
    StakesConfig,
    StakesConfigProvider,
    config_version,
    grounding_mode,
    load_stakes_config,
)

# --- load_stakes_config: default profile ------------------------------------


def test_default_profile_required_types():
    cfg = load_stakes_config("default")
    assert isinstance(cfg, StakesConfig)
    assert cfg.required_grounding_types == {"business_rules", "service_price"}


def test_default_profile_warn_only_types():
    cfg = load_stakes_config("default")
    assert cfg.warn_only_grounding_types == {
        "business_hours",
        "payment_method",
        "contact_info",
        "faq_item",
    }


def test_default_profile_has_config_version():
    cfg = load_stakes_config("default")
    assert isinstance(cfg.config_version, str)
    assert cfg.config_version != ""


# --- load_stakes_config: industrial profile ---------------------------------


def test_industrial_profile_required_types():
    cfg = load_stakes_config("industrial")
    assert cfg.required_grounding_types == {
        "business_rules",
        "service_price",
        "controlled_document_metadata",
        "industrial_requirement",
    }


def test_industrial_profile_warn_only_types():
    cfg = load_stakes_config("industrial")
    assert cfg.warn_only_grounding_types == {
        "industrial_responsibility",
        "industrial_relation",
    }


# --- unknown profile falls back to default ----------------------------------


def test_unknown_profile_falls_back_to_default():
    fallback = load_stakes_config("does-not-exist")
    default = load_stakes_config("default")
    assert fallback.required_grounding_types == default.required_grounding_types
    assert fallback.warn_only_grounding_types == default.warn_only_grounding_types


def test_default_is_default_when_no_profile_passed():
    cfg = load_stakes_config()
    assert cfg.required_grounding_types == {"business_rules", "service_price"}


# --- grounding_mode ---------------------------------------------------------


def test_grounding_mode_required():
    assert grounding_mode("business_rules", "default") == "required"
    assert grounding_mode("service_price", "default") == "required"


def test_grounding_mode_warn_only():
    assert grounding_mode("business_hours", "default") == "warn_only"
    assert grounding_mode("faq_item", "default") == "warn_only"


def test_grounding_mode_not_configured():
    assert grounding_mode("unknown_type", "default") == "not_configured"


def test_grounding_mode_uses_profile():
    # industrial-only required type is not configured under default.
    assert grounding_mode("industrial_requirement", "industrial") == "required"
    assert grounding_mode("industrial_requirement", "default") == "not_configured"


def test_grounding_mode_unknown_profile_falls_back():
    assert grounding_mode("business_rules", "nope") == "required"


def test_grounding_mode_default_profile_argument_optional():
    assert grounding_mode("business_rules") == "required"


# --- config_version module-level helper -------------------------------------


def test_config_version_matches_loaded_config():
    assert config_version() == load_stakes_config("default").config_version


# --- StakesConfigProvider protocol ------------------------------------------


def test_default_provider_implements_protocol():
    provider = DefaultStakesConfigProvider()
    assert isinstance(provider, StakesConfigProvider)
    cfg = provider.load("default")
    assert cfg.required_grounding_types == {"business_rules", "service_price"}


def test_custom_provider_overrides_without_worker_changes():
    class CustomProvider:
        def load(self, profile: str) -> StakesConfig:
            return StakesConfig(
                profile=profile,
                required_grounding_types=frozenset({"custom_type"}),
                warn_only_grounding_types=frozenset(),
                config_version="custom-v1",
            )

    provider = CustomProvider()
    assert isinstance(provider, StakesConfigProvider)
    cfg = provider.load("anything")
    assert cfg.required_grounding_types == {"custom_type"}
    assert cfg.config_version == "custom-v1"


def test_grounding_mode_accepts_provider():
    class CustomProvider:
        def load(self, profile: str) -> StakesConfig:
            return StakesConfig(
                profile=profile,
                required_grounding_types=frozenset({"custom_type"}),
                warn_only_grounding_types=frozenset({"soft_type"}),
                config_version="custom-v1",
            )

    provider = CustomProvider()
    assert grounding_mode("custom_type", "x", provider=provider) == "required"
    assert grounding_mode("soft_type", "x", provider=provider) == "warn_only"
    assert grounding_mode("business_rules", "x", provider=provider) == "not_configured"
