from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

NESTED_IDENTIFIER_RE = re.compile(
    r"\b(?P<prefix>POP|IT|MAN|MANUAL|POL|PTC|FOR|FR|FRM|REG)"
    r"(?:[ .-][A-Z]{1,8}){0,3}[ .-]\d{1,4}\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NestedIdentifierCandidate:
    identifier: str
    line_number: int
    quote: str
    identifier_type: str


@dataclass(frozen=True)
class ParserQualityProfile:
    document_family_candidate: bool = False
    nested_identifier_count: int = 0
    nested_identifiers: tuple[NestedIdentifierCandidate, ...] = field(default_factory=tuple)
    unsafe_file_metadata_blocked: bool = False
    review_required: bool = False
    publication_blocking_risk: bool = False
    risk_codes: tuple[str, ...] = field(default_factory=tuple)


def build_quality_profile(*, filename: str, text: str) -> ParserQualityProfile:
    identifiers = _nested_identifiers(text)
    distinct_identifiers = {candidate.identifier for candidate in identifiers}
    document_family_candidate = len(distinct_identifiers) >= 2
    risk_codes: list[str] = []
    if document_family_candidate:
        risk_codes.extend(["document_family_candidate", "unsafe_file_metadata_blocked"])
    return ParserQualityProfile(
        document_family_candidate=document_family_candidate,
        nested_identifier_count=len(distinct_identifiers),
        nested_identifiers=tuple(identifiers),
        unsafe_file_metadata_blocked=document_family_candidate,
        review_required=document_family_candidate,
        publication_blocking_risk=document_family_candidate,
        risk_codes=tuple(risk_codes),
    )


def quality_profile_to_metadata(profile: ParserQualityProfile) -> dict[str, Any]:
    return {
        "document_family_candidate": profile.document_family_candidate,
        "nested_identifier_count": profile.nested_identifier_count,
        "nested_identifiers": [asdict(candidate) for candidate in profile.nested_identifiers],
        "unsafe_file_metadata_blocked": profile.unsafe_file_metadata_blocked,
        "review_required": profile.review_required,
        "publication_blocking_risk": profile.publication_blocking_risk,
        "risk_codes": list(profile.risk_codes),
    }


def summarize_quality_profiles(profiles: list[ParserQualityProfile]) -> dict[str, Any]:
    risk_counts = Counter(code for profile in profiles for code in profile.risk_codes)
    return {
        "document_family_candidate_count": sum(
            1 for profile in profiles if profile.document_family_candidate
        ),
        "nested_identifier_count": sum(profile.nested_identifier_count for profile in profiles),
        "review_required_count": sum(1 for profile in profiles if profile.review_required),
        "publication_blocking_risk_count": sum(
            1 for profile in profiles if profile.publication_blocking_risk
        ),
        "risk_code_counts": dict(sorted(risk_counts.items())),
    }


def _nested_identifiers(text: str) -> list[NestedIdentifierCandidate]:
    seen: set[str] = set()
    candidates: list[NestedIdentifierCandidate] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        normalized_line = _normalize_search_text(line)
        for match in NESTED_IDENTIFIER_RE.finditer(normalized_line):
            identifier = _normalize_identifier(match.group(0))
            if identifier in seen:
                continue
            seen.add(identifier)
            candidates.append(
                NestedIdentifierCandidate(
                    identifier=identifier,
                    line_number=line_number,
                    quote=line.strip(),
                    identifier_type=identifier.split(maxsplit=1)[0].split("-", 1)[0].upper(),
                )
            )
    return candidates


def _normalize_identifier(value: str) -> str:
    normalized = _normalize_search_text(value).upper()
    normalized = re.sub(r"\s*-\s*", "-", normalized)
    normalized = re.sub(r"\s*\.\s*", ".", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return normalized.strip(" .:-")


def _normalize_search_text(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
