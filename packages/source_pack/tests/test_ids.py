from __future__ import annotations

from source_pack.ids import slug_from_filename, stable_uuid


def test_stable_uuid_is_deterministic_for_semantic_id() -> None:
    assert stable_uuid("source:02_active_ingredients_catalog.csv") == stable_uuid(
        "source:02_active_ingredients_catalog.csv"
    )


def test_stable_uuid_changes_by_namespace_prefix() -> None:
    assert stable_uuid("source:x") != stable_uuid("fact:x")


def test_slug_from_filename_strips_prefix_and_extension() -> None:
    assert slug_from_filename("02_active_ingredients_catalog.csv") == "active-ingredients-catalog"


def test_slug_from_filename_no_prefix() -> None:
    assert slug_from_filename("README.md") == "readme"


def test_slug_from_filename_handles_spaces() -> None:
    assert slug_from_filename("10_quote pricing policy.md") == "quote-pricing-policy"


def test_stable_uuid_returns_uuid_type() -> None:
    from uuid import UUID

    result = stable_uuid("source:test.csv")
    assert isinstance(result, UUID)
