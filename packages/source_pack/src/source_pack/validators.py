from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from context_builder.schemas.context_bundle import ContextBundleResponse

# ---------------------------------------------------------------------------
# Legacy helpers (used by compiler.py)
# ---------------------------------------------------------------------------

FORBIDDEN_MARKERS = (
    "raw_prompt",
    "provider_response",
    "SYSTEM PROMPT",
    "system prompt",
    "Traceback",
    "X-Amz-Signature",
    "password=",
)

TOKEN_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\b(?:sk|pk|rk|sb|org|proj)-[A-Za-z0-9_-]{16,}\b", re.IGNORECASE),
    re.compile(
        r"\b[A-Za-z]:(?:\\|\\\\)+(?:Users|Documents and Settings)(?:\\|\\\\)+[^\s,;)]*",
        re.IGNORECASE,
    ),
    re.compile(r"(?<![A-Za-z0-9])/(?:Users|home|root)/[^\s,;)]*", re.IGNORECASE),
)


def sanitize_text(text: str) -> str:
    sanitized = text
    for pattern in TOKEN_PATTERNS:
        sanitized = pattern.sub("[redacted]", sanitized)
    for marker in FORBIDDEN_MARKERS:
        sanitized = sanitized.replace(marker, "[redacted]")
    return sanitized


def validate_no_forbidden_payload(payload: Any) -> list[str]:
    serialized = json.dumps(payload, sort_keys=True, default=str)
    errors: list[str] = []
    for marker in FORBIDDEN_MARKERS:
        if marker in serialized:
            errors.append(f"forbidden_marker:{marker}")
    for pattern in TOKEN_PATTERNS:
        if pattern.search(serialized):
            errors.append(f"forbidden_pattern:{pattern.pattern}")
    return errors


# ---------------------------------------------------------------------------
# Task 6: Bundle-level validation (ValidationIssue, validate_source_pack_bundle)
# ---------------------------------------------------------------------------

Severity = Literal["blocker", "warning"]


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    field: str
    message: str


# Patterns that must NEVER appear in any string field in the bundle
_SECRET_PATTERN = re.compile(
    r"sk-[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{20,}",
    re.IGNORECASE,
)
_PRIVATE_PATH_PATTERN = re.compile(
    r"\b[A-Za-z]:\\(?:Users|Documents and Settings)\\|"
    r"(^|\s)/(?:Users|home|root)/",
    re.IGNORECASE | re.MULTILINE,
)
_STACK_TRACE_PATTERN = re.compile(
    r"Traceback \(most recent call last\)|at \w+\.\w+\([\w.]+:\d+\)",
    re.IGNORECASE,
)
_RAW_PROMPT_PATTERN = re.compile(
    r"\bSYSTEM\s+PROMPT\b|\bYou are an AI\b|\bignore previous instructions\b",
    re.IGNORECASE,
)
_PROVIDER_RESPONSE_PATTERN = re.compile(
    r'"choices"\s*:\s*\[|"finish_reason"\s*:|"usage"\s*:\s*\{',
    re.IGNORECASE,
)


def _extract_strings(obj: Any) -> list[str]:
    """Recursively collect all string values from a dict/list/str."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        result = []
        for v in obj.values():
            result.extend(_extract_strings(v))
        return result
    if isinstance(obj, list):
        result = []
        for item in obj:
            result.extend(_extract_strings(item))
        return result
    return []


def validate_source_pack_bundle(bundle: ContextBundleResponse) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    bundle_dict = bundle.model_dump()

    # 1. Secret scan — blocker
    for s in _extract_strings(bundle_dict):
        if _SECRET_PATTERN.search(s):
            issues.append(
                ValidationIssue("blocker", "bundle", "Secret pattern detected (sk-... or Bearer token)")
            )
            break

    # 2. Private path scan — blocker
    for s in _extract_strings(bundle_dict):
        if _PRIVATE_PATH_PATTERN.search(s):
            issues.append(
                ValidationIssue("blocker", "bundle", f"Private local path detected: {s[:80]}")
            )
            break

    # 3. Stack trace scan — blocker
    for s in _extract_strings(bundle_dict):
        if _STACK_TRACE_PATTERN.search(s):
            issues.append(
                ValidationIssue("blocker", "bundle", "Stack trace detected in bundle content")
            )
            break

    # 4. Raw prompt labels — blocker
    for s in _extract_strings(bundle_dict):
        if _RAW_PROMPT_PATTERN.search(s):
            issues.append(ValidationIssue("blocker", "bundle", "Raw prompt label detected"))
            break

    # 5. Provider response payloads — blocker
    for s in _extract_strings(bundle_dict):
        if _PROVIDER_RESPONSE_PATTERN.search(s):
            issues.append(
                ValidationIssue("blocker", "bundle", "Provider raw response payload detected")
            )
            break

    # 6. All sources must be published — blocker
    for src in bundle.sources:
        if src.status != "published":
            issues.append(
                ValidationIssue(
                    "blocker",
                    "sources",
                    f"Source {src.id} has status '{src.status}' (must be 'published')",
                )
            )

    # 7. Rules with empty evidence_span_ids — blocker
    for rule in bundle.rules:
        if not rule.evidence_span_ids:
            issues.append(
                ValidationIssue("blocker", "rules", f"Rule {rule.id} has no evidence_span_ids")
            )

    # 8. Critical tests must have evidence reference (if critical=True) — blocker
    for test in bundle.tests:
        if (
            test.critical
            and not test.required_evidence_span_ids
            and not test.required_fact_ids
            and not test.required_rule_ids
        ):
            issues.append(
                ValidationIssue(
                    "blocker", "tests", f"Critical test '{test.id}' has no required references"
                )
            )

    # 9. Memory policy must not allow sensitive terms — blocker
    sensitive_terms = (
        "diagnosis",
        "full_prescription",
        "card_number",
        "controlled_substance_detail",
        "clinical_protocol",
    )
    allowed = [a.lower() for a in bundle.memory_policy.allowed]
    for term in sensitive_terms:
        if any(term in a for a in allowed):
            issues.append(
                ValidationIssue(
                    "blocker",
                    "memory_policy",
                    f"Memory policy explicitly allows sensitive term: {term}",
                )
            )

    return issues


def raise_if_blocked(issues: list[ValidationIssue]) -> None:
    blockers = [i for i in issues if i.severity == "blocker"]
    if blockers:
        msgs = "\n".join(f"  [{i.field}] {i.message}" for i in blockers)
        raise ValueError(f"Bundle validation blocked:\n{msgs}")
