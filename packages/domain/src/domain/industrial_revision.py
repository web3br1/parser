from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from domain.industrial import (
    DOCUMENT_STATUS_VALUES,
    normalize_document_code,
    normalize_document_status,
    normalize_revision,
)

_ACTIVE_STATUSES = {"approved", "vigent"}
_OBSOLETE_STATUS = "obsolete"


@dataclass(frozen=True)
class RevisionFamilyResolution:
    family_key: str | None
    candidate_revision: str | None
    vigent_revision: str | None
    blocking_gap_codes: list[str]
    revision_order: list[str]


@dataclass(frozen=True)
class _RevisionDocument:
    document_code: str
    revision: str
    status: str
    content_hash: str | None


def resolve_revision_family(documents: Iterable[Mapping[str, Any]]) -> RevisionFamilyResolution:
    normalized_documents = [_normalize_document(document) for document in documents]
    family_key = _resolve_family_key(normalized_documents)
    revision_order = _revision_order(normalized_documents)
    candidate_revision = _highest_active_revision(normalized_documents) or _highest_revision(
        revision_order,
    )

    blocking_gap_codes = _blocking_gap_codes(normalized_documents, candidate_revision)
    vigent_revision = candidate_revision if candidate_revision and not blocking_gap_codes else None

    return RevisionFamilyResolution(
        family_key=family_key,
        candidate_revision=candidate_revision,
        vigent_revision=vigent_revision,
        blocking_gap_codes=blocking_gap_codes,
        revision_order=revision_order,
    )


def _normalize_document(document: Mapping[str, Any]) -> _RevisionDocument:
    document_code = _normalize_optional_code(document.get("document_code"))
    revision = _normalize_optional_revision(document.get("revision"))
    status = _normalize_optional_status(document.get("status"))
    content_hash = _normalize_optional_text(document.get("content_hash"))
    return _RevisionDocument(
        document_code=document_code,
        revision=revision,
        status=status,
        content_hash=content_hash,
    )


def _normalize_optional_code(value: object) -> str:
    if isinstance(value, str):
        return normalize_document_code(value)
    return ""


def _normalize_optional_revision(value: object) -> str:
    if isinstance(value, str):
        return normalize_revision(value)
    return ""


def _normalize_optional_status(value: object) -> str:
    if isinstance(value, str):
        status = normalize_document_status(value)
        if status in DOCUMENT_STATUS_VALUES:
            return status
    return "unknown"


def _normalize_optional_text(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _resolve_family_key(documents: list[_RevisionDocument]) -> str | None:
    family_keys = sorted({document.document_code for document in documents if document.document_code})
    if not family_keys:
        return None
    return family_keys[0]


def _revision_order(documents: list[_RevisionDocument]) -> list[str]:
    revisions = {document.revision for document in documents if document.revision}
    return sorted(revisions, key=_revision_sort_key)


def _highest_active_revision(documents: list[_RevisionDocument]) -> str | None:
    return _highest_revision(
        {
            document.revision
            for document in documents
            if document.revision and document.status in _ACTIVE_STATUSES
        },
    )


def _highest_revision(revisions: set[str] | list[str]) -> str | None:
    if not revisions:
        return None
    return max(revisions, key=_revision_sort_key)


def _revision_sort_key(revision: str) -> tuple[int, int, str]:
    if revision.isdigit():
        return (0, int(revision), revision)
    return (1, 0, revision)


def _blocking_gap_codes(
    documents: list[_RevisionDocument],
    candidate_revision: str | None,
) -> list[str]:
    gap_codes: list[str] = []

    if any(not document.revision for document in documents):
        gap_codes.append("missing_revision")

    if _has_duplicate_revision_conflict(documents):
        gap_codes.append("duplicate_revision_conflict")

    if _has_ambiguous_vigent_revision(documents, candidate_revision):
        gap_codes.append("ambiguous_vigent_revision")

    return gap_codes


def _has_duplicate_revision_conflict(documents: list[_RevisionDocument]) -> bool:
    hashes_by_revision: dict[str, set[str]] = {}
    for document in documents:
        if not document.revision or not document.content_hash:
            continue
        hashes_by_revision.setdefault(document.revision, set()).add(document.content_hash)
    return any(len(content_hashes) > 1 for content_hashes in hashes_by_revision.values())


def _has_ambiguous_vigent_revision(
    documents: list[_RevisionDocument],
    candidate_revision: str | None,
) -> bool:
    active_revisions = {
        document.revision
        for document in documents
        if document.revision and document.status in _ACTIVE_STATUSES
    }
    if len(active_revisions) <= 1:
        return False

    obsolete_revisions = {
        document.revision
        for document in documents
        if document.revision and document.status == _OBSOLETE_STATUS
    }
    older_active_revisions = active_revisions - {candidate_revision}
    return any(revision not in obsolete_revisions for revision in older_active_revisions)
