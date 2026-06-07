from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from parsers.base import sanitize_text
from parsers.chunker import RawChunk

NORMATIVE_RE = re.compile(
    r"\b(deve|devem|obrigatorio|obrigatoria|proibido|proibida|necessario|necessaria)\b",
    re.IGNORECASE,
)
RESPONSIBILITY_RE = re.compile(
    r"^(?:O|A|Os|As)\s+(?P<role>[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç ]{2,60}?)\s+"
    r"(?:deve|devem|é responsável por|e responsavel por)\s+(?P<action>.+)$",
    re.IGNORECASE,
)
FORM_ID_RE = re.compile(r"\b(?P<identifier>(?:FOR|FR)-[A-Z]{2,}-\d{2,})\b", re.IGNORECASE)
ANNEX_RE = re.compile(r"\bAnexo\s+(?P<label>[IVXLCDM]+|\d+)\s*[-–:]?\s*(?P<name>.+)?$", re.IGNORECASE)
RECORD_LABEL_RE = re.compile(
    r"\b(?P<label>Registro|Formulario|Formulário|Lista de verificacao|Lista de verificação|Anexo)\b",
    re.IGNORECASE,
)
EQUIPMENT_RE = re.compile(r"\b(?:Equipamento|Instrumento|Maquina|Máquina)\s*:\s*(?P<name>.+)$", re.IGNORECASE)
STEP_RE = re.compile(r"^\s*(?P<label>\d+(?:\.\d+)*)(?:[\.)])\s+(?P<instruction>.+?)\s*$")
TOC_DOT_LEADER_RE = re.compile(r"\.{3,}\s*\d+\s*$")
TOC_NUMBERED_ENTRY_RE = re.compile(r"^\s*\d+(?:\.\d+)*\s+\S.+$")
TOC_SECTION_TITLES = {"sumario", "indice", "table of contents"}


@dataclass(frozen=True)
class IndustrialSemanticEvidence:
    quote: str
    chunk_index: int
    chunk_hash: str
    section_path: str | None
    section_title: str | None
    page_start: int | None
    page_end: int | None
    char_start: int
    char_end: int


@dataclass(frozen=True)
class IndustrialSemanticCandidate:
    candidate_id: str
    kind: str
    normalized_text: str
    normalized_content: dict[str, Any]
    confidence: float
    evidence: IndustrialSemanticEvidence
    risk_codes: tuple[str, ...] = ()


def extract_semantic_candidates(chunks: list[RawChunk]) -> list[IndustrialSemanticCandidate]:
    candidates: list[IndustrialSemanticCandidate] = []
    section_step_counts: dict[str, int] = {}
    for chunk in chunks:
        candidates.extend(
            extract_semantic_candidates_from_chunk(
                chunk,
                section_step_counts=section_step_counts,
            )
        )
    return candidates


def extract_semantic_candidates_from_chunk(
    chunk: RawChunk,
    *,
    section_step_counts: dict[str, int] | None = None,
) -> list[IndustrialSemanticCandidate]:
    if _is_boilerplate_chunk(chunk):
        return []
    candidates: list[IndustrialSemanticCandidate] = []
    offset = 0
    section_step_counts = section_step_counts if section_step_counts is not None else {}
    section_key = chunk.section_path or f"chunk:{chunk.chunk_index}"
    for raw_line in chunk.text.splitlines(keepends=True):
        line = sanitize_text(raw_line)
        start = offset + raw_line.find(raw_line.strip()) if raw_line.strip() else offset
        end = start + len(line)
        offset += len(raw_line)
        if not line or _is_toc_line(line):
            continue

        requirement = _requirement_candidate(chunk, line, start, end)
        if requirement is not None:
            candidates.append(requirement)

        responsibility = _responsibility_candidate(chunk, line, start, end)
        if responsibility is not None:
            candidates.append(responsibility)

        candidates.extend(_reference_candidates(chunk, line, start, end))
        equipment = _equipment_candidate(chunk, line, start, end)
        if equipment is not None:
            candidates.append(equipment)

        step_order = section_step_counts.get(section_key, 0) + 1
        step = _procedure_step_candidate(chunk, line, start, end, order=step_order)
        if step is not None:
            section_step_counts[section_key] = step_order
            candidates.append(step)
    return candidates


def summarize_semantic_candidates(candidates: list[IndustrialSemanticCandidate]) -> dict[str, Any]:
    kind_counts = Counter(candidate.kind for candidate in candidates)
    return {
        "total_candidate_count": len(candidates),
        "candidate_kind_counts": dict(sorted(kind_counts.items())),
    }


def semantic_candidates_to_metadata(candidates: list[IndustrialSemanticCandidate]) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": candidate.candidate_id,
            "kind": candidate.kind,
            "normalized_text": candidate.normalized_text,
            "normalized_content": candidate.normalized_content,
            "confidence": candidate.confidence,
            "evidence": asdict(candidate.evidence),
            "risk_codes": list(candidate.risk_codes),
        }
        for candidate in candidates
    ]


def _requirement_candidate(
    chunk: RawChunk,
    line: str,
    start: int,
    end: int,
) -> IndustrialSemanticCandidate | None:
    if _is_toc_section(chunk) and _looks_like_toc_entry(line):
        return None
    if NORMATIVE_RE.search(line) is None:
        return None
    modality = "mandatory"
    if re.search(r"\bproibid[oa]\b", line, re.IGNORECASE):
        modality = "prohibited"
    return _candidate(
        chunk=chunk,
        kind="requirement",
        text=line,
        normalized_content={"requirement": line, "modality": modality},
        confidence=0.82,
        char_start=start,
        char_end=end,
    )


def _responsibility_candidate(
    chunk: RawChunk,
    line: str,
    start: int,
    end: int,
) -> IndustrialSemanticCandidate | None:
    match = RESPONSIBILITY_RE.match(line)
    if not match:
        return None
    role = sanitize_text(match.group("role"))
    if not _is_explicit_role(role):
        return None
    action = sanitize_text(match.group("action"))
    return _candidate(
        chunk=chunk,
        kind="responsibility",
        text=line,
        normalized_content={"role": role, "responsibility": action},
        confidence=0.78,
        char_start=start,
        char_end=end,
    )


def _reference_candidates(
    chunk: RawChunk,
    line: str,
    start: int,
    end: int,
) -> list[IndustrialSemanticCandidate]:
    if _is_toc_line(line) or _is_toc_section(chunk):
        return []
    annex = ANNEX_RE.search(line)
    if annex is not None:
        identifier = f"ANEXO {annex.group('label').upper()}"
        name = sanitize_text(annex.group("name") or identifier)
        return [
            _candidate(
                chunk=chunk,
                kind="record_reference",
                text=line,
                normalized_content={"identifier": identifier, "name": name},
                confidence=0.7,
                char_start=start,
                char_end=end,
            )
        ]
    identifier_match = FORM_ID_RE.search(line)
    if identifier_match is None:
        return []
    identifier = identifier_match.group("identifier").upper()
    name = _reference_name(line, identifier)
    candidates = [
        _candidate(
            chunk=chunk,
            kind="form_reference",
            text=line,
            normalized_content={"identifier": identifier, "name": name},
            confidence=0.8,
            char_start=start,
            char_end=end,
        )
    ]
    if RECORD_LABEL_RE.search(line):
        candidates.append(
            _candidate(
                chunk=chunk,
                kind="record_reference",
                text=line,
                normalized_content={"identifier": identifier, "name": name},
                confidence=0.76,
                char_start=start,
                char_end=end,
            )
        )
    return candidates


def _procedure_step_candidate(
    chunk: RawChunk,
    line: str,
    start: int,
    end: int,
    *,
    order: int,
) -> IndustrialSemanticCandidate | None:
    match = STEP_RE.match(line)
    if not match or _is_toc_line(line) or _is_toc_section(chunk):
        return None
    instruction = sanitize_text(match.group("instruction"))
    return _candidate(
        chunk=chunk,
        kind="procedure_step",
        text=line,
        normalized_content={
            "step_label": match.group("label"),
            "instruction": instruction,
            "order": order,
        },
        confidence=0.74,
        char_start=start,
        char_end=end,
    )


def _equipment_candidate(
    chunk: RawChunk,
    line: str,
    start: int,
    end: int,
) -> IndustrialSemanticCandidate | None:
    if _is_toc_line(line) or _is_toc_section(chunk):
        return None
    match = EQUIPMENT_RE.search(line)
    if not match:
        return None
    equipment = sanitize_text(match.group("name"))
    return _candidate(
        chunk=chunk,
        kind="equipment_reference",
        text=line,
        normalized_content={"equipment": equipment},
        confidence=0.72,
        char_start=start,
        char_end=end,
    )


def _candidate(
    *,
    chunk: RawChunk,
    kind: str,
    text: str,
    normalized_content: dict[str, Any],
    confidence: float,
    char_start: int,
    char_end: int,
) -> IndustrialSemanticCandidate:
    evidence = IndustrialSemanticEvidence(
        quote=text,
        chunk_index=chunk.chunk_index,
        chunk_hash=chunk.chunk_hash,
        section_path=chunk.section_path,
        section_title=chunk.section_title,
        page_start=chunk.page_start or chunk.source_page,
        page_end=chunk.page_end or chunk.source_page,
        char_start=char_start,
        char_end=char_end,
    )
    return IndustrialSemanticCandidate(
        candidate_id=_candidate_id(chunk, kind, char_start, text),
        kind=kind,
        normalized_text=text,
        normalized_content=normalized_content,
        confidence=confidence,
        evidence=evidence,
    )


def _candidate_id(chunk: RawChunk, kind: str, char_start: int, text: str) -> str:
    safe_text = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")[:48]
    return f"{chunk.chunk_hash}:{kind}:{char_start}:{safe_text}"


def _is_explicit_role(role: str) -> bool:
    role_key = _fold_ascii(role)
    return role_key.startswith((
        "gerente",
        "supervisor",
        "coordenador",
        "responsavel",
        "operador",
        "analista",
        "equipe",
        "setor",
    ))


def _reference_name(line: str, identifier: str) -> str:
    match = re.search(re.escape(identifier), line, flags=re.IGNORECASE)
    after_identifier = line[match.end():] if match else line
    cleaned = re.sub(r"^[\s:–\-.]+", "", after_identifier).strip()
    return cleaned or identifier


def _is_toc_line(line: str) -> bool:
    return (
        bool(TOC_DOT_LEADER_RE.search(line))
        or _fold_ascii(line.strip()) in TOC_SECTION_TITLES
    )


def _looks_like_toc_entry(line: str) -> bool:
    return bool(TOC_NUMBERED_ENTRY_RE.match(line)) or _is_toc_line(line)


def _is_toc_section(chunk: RawChunk) -> bool:
    return _fold_ascii(chunk.section_title or "") in TOC_SECTION_TITLES


def _is_boilerplate_chunk(chunk: RawChunk) -> bool:
    chunk_kind = (chunk.chunk_kind or "").casefold()
    if chunk_kind in {"boilerplate", "header", "footer"}:
        return True
    metadata_kind = str(chunk.metadata.get("boilerplate_kind") or "").casefold()
    return metadata_kind in {"boilerplate", "header", "footer"}


def _fold_ascii(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return decomposed.encode("ascii", errors="ignore").decode("ascii").casefold()
