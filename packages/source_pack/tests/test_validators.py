from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from context_builder.schemas.context_bundle import (
    ContextBundleEvidence,
    ContextBundleFact,
    ContextBundleIntegrity,
    ContextBundleReadiness,
    ContextBundleResponse,
    ContextBundleRule,
    ContextBundleSource,
)
from source_pack.validators import ValidationIssue, raise_if_blocked, validate_source_pack_bundle


# Minimal valid bundle helper
def _make_bundle(**overrides: object) -> ContextBundleResponse:
    src_id = uuid4()
    chunk_id = uuid4()
    ev_id = uuid4()
    base = dict(
        schema_version="context_bundle.v1",
        context_version="test-v1",
        workspace_id=uuid4(),
        generated_at=datetime.now(UTC),
        sources=[ContextBundleSource(id=src_id, type="markdown", status="published")],
        facts=[ContextBundleFact(
            id=uuid4(), fact_type="test_fact", schema_version="v1",
            normalized_content={"value": "ok"},
            source_id=src_id, chunk_id=chunk_id, evidence_span_ids=[ev_id],
        )],
        rules=[ContextBundleRule(
            id=uuid4(), rule_type="test_rule", schema_version="v1",
            condition={"trigger": "test"}, action={"do": "something"},
            priority=1, source_id=src_id, chunk_id=chunk_id, evidence_span_ids=[ev_id],
        )],
        evidence=[ContextBundleEvidence(id=ev_id, source_id=src_id, chunk_id=chunk_id)],
        readiness=ContextBundleReadiness(status="ready", score=100),
        integrity=ContextBundleIntegrity(
            bundle_hash="abc", source_count=1, fact_count=1, rule_count=1, evidence_count=1,
        ),
    )
    base.update(overrides)
    return ContextBundleResponse(**base)


class TestSecretScan:
    def test_blocks_sk_secret(self):
        bundle = _make_bundle(
            facts=[ContextBundleFact(
                id=uuid4(), fact_type="f", schema_version="v1",
                normalized_content={"key": "sk-" + "abcdefghijklmnopqrstuvwxyz12345"},
                source_id=uuid4(), chunk_id=uuid4(), evidence_span_ids=[uuid4()],
            )]
        )
        issues = validate_source_pack_bundle(bundle)
        assert any(i.severity == "blocker" and "Secret" in i.message for i in issues)

    def test_blocks_bearer_token(self):
        bundle = _make_bundle(
            rules=[ContextBundleRule(
                id=uuid4(), rule_type="r", schema_version="v1",
                condition={"auth": "Bearer " + "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9xxxyyy"},
                action={}, priority=1, source_id=uuid4(), chunk_id=uuid4(), evidence_span_ids=[uuid4()],
            )]
        )
        issues = validate_source_pack_bundle(bundle)
        assert any(i.severity == "blocker" and "Secret" in i.message for i in issues)

    def test_clean_bundle_has_no_secret_issue(self):
        bundle = _make_bundle()
        issues = validate_source_pack_bundle(bundle)
        assert not any("Secret" in i.message for i in issues)


class TestPrivatePathScan:
    def test_blocks_windows_user_path(self):
        bundle = _make_bundle(
            facts=[ContextBundleFact(
                id=uuid4(), fact_type="f", schema_version="v1",
                normalized_content={"path": r"C:\Users\admin\data.csv"},
                source_id=uuid4(), chunk_id=uuid4(), evidence_span_ids=[uuid4()],
            )]
        )
        issues = validate_source_pack_bundle(bundle)
        assert any(i.severity == "blocker" and "path" in i.message.lower() for i in issues)

    def test_blocks_unix_home_path(self):
        bundle = _make_bundle(
            facts=[ContextBundleFact(
                id=uuid4(), fact_type="f", schema_version="v1",
                normalized_content={"path": "/home/user/secrets"},
                source_id=uuid4(), chunk_id=uuid4(), evidence_span_ids=[uuid4()],
            )]
        )
        issues = validate_source_pack_bundle(bundle)
        assert any(i.severity == "blocker" and "path" in i.message.lower() for i in issues)


class TestStackTraceScan:
    def test_blocks_stack_trace(self):
        bundle = _make_bundle(
            facts=[ContextBundleFact(
                id=uuid4(), fact_type="f", schema_version="v1",
                normalized_content={"error": "Traceback (most recent call last): File x.py"},
                source_id=uuid4(), chunk_id=uuid4(), evidence_span_ids=[uuid4()],
            )]
        )
        issues = validate_source_pack_bundle(bundle)
        assert any(i.severity == "blocker" and "Stack trace" in i.message for i in issues)


class TestRawPromptScan:
    def test_blocks_system_prompt_label(self):
        bundle = _make_bundle(
            facts=[ContextBundleFact(
                id=uuid4(), fact_type="f", schema_version="v1",
                normalized_content={"content": "SYSTEM PROMPT: You must obey."},
                source_id=uuid4(), chunk_id=uuid4(), evidence_span_ids=[uuid4()],
            )]
        )
        issues = validate_source_pack_bundle(bundle)
        assert any(i.severity == "blocker" and "prompt" in i.message.lower() for i in issues)


class TestSourcePublishedCheck:
    def test_blocks_unpublished_source(self):
        src_id = uuid4()
        bundle = _make_bundle(
            sources=[ContextBundleSource(id=src_id, type="csv", status="draft")],
            facts=[], rules=[], evidence=[],
            readiness=ContextBundleReadiness(status="blocked", score=0),
            integrity=ContextBundleIntegrity(
                bundle_hash="x", source_count=1, fact_count=0, rule_count=0, evidence_count=0,
            ),
        )
        issues = validate_source_pack_bundle(bundle)
        assert any(i.severity == "blocker" and "status" in i.message for i in issues)

    def test_published_source_ok(self):
        bundle = _make_bundle()
        issues = validate_source_pack_bundle(bundle)
        assert not any("status" in i.message and "sources" == i.field for i in issues)


class TestRuleEvidenceCheck:
    def test_blocks_rule_without_evidence(self):
        bundle = _make_bundle(
            rules=[ContextBundleRule(
                id=uuid4(), rule_type="r", schema_version="v1",
                condition={}, action={}, priority=1,
                source_id=uuid4(), chunk_id=uuid4(),
                evidence_span_ids=[],  # EMPTY — blocker
            )]
        )
        issues = validate_source_pack_bundle(bundle)
        assert any(i.severity == "blocker" and i.field == "rules" for i in issues)

    def test_rule_with_evidence_ok(self):
        bundle = _make_bundle()
        issues = validate_source_pack_bundle(bundle)
        assert not any(i.field == "rules" for i in issues)


class TestRaiseIfBlocked:
    def test_raises_on_blocker(self):
        issues = [ValidationIssue("blocker", "bundle", "Test blocker")]
        with pytest.raises(ValueError, match="blocked"):
            raise_if_blocked(issues)

    def test_does_not_raise_on_warning_only(self):
        issues = [ValidationIssue("warning", "bundle", "Just a warning")]
        raise_if_blocked(issues)  # must not raise

    def test_does_not_raise_on_empty(self):
        raise_if_blocked([])  # must not raise
