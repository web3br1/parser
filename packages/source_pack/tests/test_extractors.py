from __future__ import annotations

from pathlib import Path

import pytest
from source_pack.compiler import compile_source_pack

SOURCE_PACK = Path("C:/tmp/context-builder-sources/compounding-pharmacy-gold")
pytestmark = pytest.mark.skipif(
    not SOURCE_PACK.exists(),
    reason="compounding pharmacy gold source pack is not available",
)


def test_compile_source_pack_extracts_domain_sections_from_gold_pack() -> None:
    bundle = compile_source_pack(SOURCE_PACK)

    assert len(bundle.sources) == 64
    assert len(bundle.evidence) > 100
    assert any(fact.fact_type == "active_ingredient" for fact in bundle.facts)
    assert any(rule.rule_type == "allergen_handoff" for rule in bundle.rules)
    assert any(rule.rule_type == "tool_policy" for rule in bundle.rules)
    assert any(gap.id == "gap_payment_methods" for gap in bundle.gaps)
    assert any(test.critical for test in bundle.tests)
    assert "preferred_contact_channel" in bundle.memory_policy.allowed
    assert any(
        recommendation.tool_name == "check_inventory"
        for recommendation in bundle.tool_recommendations
    )
