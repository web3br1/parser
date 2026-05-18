from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


@dataclass
class EvidenceSpanInput:
    workspace_id: str
    source_id: str
    chunk_id: str
    quote: str
    char_start: int | None
    char_end: int | None
    page_number: int | None
    sheet_name: str | None
    row_number: int | None


def build_evidence_span_input(
    *,
    workspace_id: str,
    source_id: str,
    chunk_id: str,
    llm_evidence: dict,  # type: ignore[type-arg]
    chunk_metadata: dict,  # type: ignore[type-arg]
) -> EvidenceSpanInput | None:
    """
    Builds the input for evidence_span creation.
    Returns None if quote is absent or empty — caller must handle per destination:
      - extracted_facts: continue without evidence_span (nullable)
      - business_rules:  fail with reason="missing_evidence_quote"
    """
    quote = (llm_evidence.get("quote") or "").strip()
    if not quote:
        return None

    return EvidenceSpanInput(
        workspace_id=workspace_id,
        source_id=source_id,
        chunk_id=chunk_id,
        quote=quote,
        char_start=llm_evidence.get("char_start"),
        char_end=llm_evidence.get("char_end"),
        page_number=chunk_metadata.get("source_page"),
        sheet_name=chunk_metadata.get("sheet_name"),
        row_number=chunk_metadata.get("row_start"),
    )


def compute_quote_hash(quote: str) -> str:
    return sha256(quote.encode()).hexdigest()
