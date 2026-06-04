from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

DOCUMENT_CODE_RE = re.compile(
    r"\b(?P<type>POP|IT|MAN|MANUAL|POL|FOR|FRM|REG|ESP|SPEC|FAQ)"
    r"(?:[ .-][A-Z]{1,8}){0,3}[ .-]\d{1,4}\b",
    re.IGNORECASE,
)
PROTOCOL_CODE_RE = re.compile(
    r"\b[A-Z]{2,5}(?:\.[A-Z]{2,16})+(?:-[A-Z]{2,16})?\.\d{1,4}\b",
    re.IGNORECASE,
)
COMPACT_DOCUMENT_CODE_RE = re.compile(
    r"\b(?!REV\d{1,3}\b)[A-Z]{2,8}\d{2,4}\b",
    re.IGNORECASE,
)
REVISION_RE = re.compile(
    r"\b(?:rev(?:isao)?\.?|revisao|revision|versao(?:\s*n)?|version|r)"
    r"\s*(?:n\.?)?\s*[:.\-]?\s*(?P<revision>\d{1,3}(?:\.\d{1,3})*)\b",
    re.IGNORECASE,
)
LABELED_VALUE_RE = re.compile(r"^\s*(?P<label>[^:\n]{2,40})\s*:\s*(?P<value>.+?)\s*$")

TYPE_ALIASES = {
    "POP": "POP",
    "IT": "IT",
    "FAQ": "FAQ",
    "PTC": "PTC",
    "MAN": "Manual",
    "MANUAL": "Manual",
    "POL": "Policy",
    "FOR": "Form",
    "FRM": "Form",
    "REG": "Record",
    "ESP": "Specification",
    "SPEC": "Specification",
}
STATUS_ALIASES = {
    "vigencia": "vigent",
    "vigente": "vigent",
    "vigent": "vigent",
    "aprovado": "approved",
    "approved": "approved",
    "obsoleto": "obsolete",
    "obsolete": "obsolete",
    "rascunho": "draft",
    "draft": "draft",
}
CODE_LABELS = ("codigo", "code", "document code", "documento", "numero", "number", "n")
REVISION_LABELS = (
    "revisao",
    "revision",
    "rev",
    "versao",
    "versao n",
    "versao no",
    "version",
)
STATUS_LABELS = ("status", "situacao")
OWNER_LABELS = ("area dona", "owner area", "area", "departamento", "depto")
TITLE_LABELS = ("titulo", "title")
STACKED_VALUE_LABELS = CODE_LABELS + REVISION_LABELS + STATUS_LABELS
HEADER_LABELS = (
    CODE_LABELS
    + REVISION_LABELS
    + STATUS_LABELS
    + OWNER_LABELS
    + TITLE_LABELS
    + ("pagina", "pagina total", "data", "responsavel nome", "aprovacao nome")
)
DASH_TRANSLATIONS = ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212")


@dataclass(frozen=True)
class IndustrialMetadataCandidate:
    document_code: str | None = None
    document_type: str | None = None
    title: str | None = None
    revision: str | None = None
    status: str | None = None
    owner_area: str | None = None
    gap_codes: list[str] = field(default_factory=list)


def extract_metadata_candidates(*, filename: str, text: str) -> IndustrialMetadataCandidate:
    haystack = f"{filename}\n{text[:4000]}"
    labeled = _labeled_values(text)
    code = _first_document_code(filename=filename, text=text, labeled=labeled)
    revision = _first_revision(haystack, labeled)
    document_type = _document_type_from_code(code) or _document_type_from_text(haystack)
    status = _status(haystack, labeled)
    title = _first_labeled(labeled, TITLE_LABELS)
    owner_area = _first_labeled(labeled, OWNER_LABELS)
    gap_codes = _gap_codes(code=code, revision=revision)
    return IndustrialMetadataCandidate(
        document_code=code,
        document_type=document_type,
        title=title,
        revision=revision,
        status=status,
        owner_area=owner_area,
        gap_codes=gap_codes,
    )


def _labeled_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    lines = text.splitlines()[:100]
    for line in lines:
        match = LABELED_VALUE_RE.match(line)
        if not match:
            continue
        label = _normalize_label(match.group("label"))
        value = match.group("value").strip()
        if value:
            values[label] = value
    for index, line in enumerate(lines):
        label = _normalize_label(line)
        if label not in STACKED_VALUE_LABELS or label in values:
            continue
        value = _stacked_value_after_label(lines, index)
        if value:
            values[label] = value
    return values


def _first_document_code(*, filename: str, text: str, labeled: dict[str, str]) -> str | None:
    for label in CODE_LABELS:
        value = labeled.get(label)
        if value:
            code = _find_document_code(value, allow_compact=True)
            if code:
                return code
    code = _document_code_near_label(text)
    if code:
        return code
    code = _document_code_in_header(text)
    if code:
        return code
    code = _find_document_code(filename, allow_compact=True)
    if code:
        return code
    return None


def _first_revision(haystack: str, labeled: dict[str, str]) -> str | None:
    for label in REVISION_LABELS:
        value = labeled.get(label)
        if value:
            number = re.search(r"\d{1,3}(?:\.\d{1,3})*", value)
            if number:
                return _normalize_revision(number.group(0))
    match = REVISION_RE.search(_normalize_search_text(haystack))
    if match:
        return _normalize_revision(match.group("revision"))
    return None


def _document_type_from_code(code: str | None) -> str | None:
    if not code:
        return None
    prefix = re.split(r"[- .]", code, maxsplit=1)[0].upper()
    if prefix in TYPE_ALIASES:
        return TYPE_ALIASES[prefix]
    if any(character.isdigit() for character in prefix):
        return None
    return prefix


def _document_type_from_text(text: str) -> str | None:
    normalized = _normalize_search_text(text).lower()
    if "procedimento operacional padrao" in normalized:
        return "POP"
    if "instrucao de trabalho" in normalized:
        return "IT"
    if "protocolo" in normalized:
        return "PTC"
    return None


def _status(haystack: str, labeled: dict[str, str]) -> str | None:
    explicit = _first_labeled(labeled, STATUS_LABELS)
    if explicit:
        normalized = _status_from_text(explicit)
        if normalized:
            return normalized
    return _status_from_text(haystack)


def _status_from_text(text: str) -> str | None:
    lower = _normalize_search_text(text).lower()
    for marker, status in STATUS_ALIASES.items():
        if marker in lower:
            return status
    return None


def _first_labeled(labeled: dict[str, str], labels: tuple[str, ...]) -> str | None:
    for label in labels:
        value = labeled.get(label)
        if value:
            return value
    return None


def _gap_codes(*, code: str | None, revision: str | None) -> list[str]:
    gaps: list[str] = []
    if code is None:
        gaps.append("missing_document_code")
    if revision is None:
        gaps.append("missing_revision")
    return gaps


def _find_document_code(value: str, *, allow_compact: bool) -> str | None:
    normalized = _normalize_search_text(value)
    for pattern in (DOCUMENT_CODE_RE, PROTOCOL_CODE_RE):
        match = pattern.search(normalized)
        if match:
            return _normalize_document_code(match.group(0))
    if allow_compact:
        match = COMPACT_DOCUMENT_CODE_RE.search(normalized)
        if match:
            return _normalize_document_code(match.group(0))
    return None


def _document_code_near_label(text: str) -> str | None:
    lines = text.splitlines()[:100]
    for index, line in enumerate(lines):
        label = _normalize_label(line)
        if label not in CODE_LABELS:
            continue
        window_lines: list[str] = []
        for candidate in lines[index + 1 : index + 12]:
            if _normalize_label(candidate) in ("sumario", "indice", "table of contents"):
                break
            window_lines.append(candidate)
        window = "\n".join(window_lines)
        code = _find_document_code(window, allow_compact=True)
        if code:
            return code
    return None


def _document_code_in_header(text: str) -> str | None:
    header_lines: list[str] = []
    for line in text.splitlines()[:100]:
        label = _normalize_label(line)
        if label in ("sumario", "indice", "table of contents"):
            break
        if not line.strip() or label.isdigit():
            continue
        header_lines.append(line)
        if len(header_lines) >= 40:
            break
    if not header_lines:
        return None
    return _find_document_code("\n".join(header_lines), allow_compact=False)


def _stacked_value_after_label(lines: list[str], index: int) -> str | None:
    for line in lines[index + 1 : index + 8]:
        value = line.strip()
        if not value:
            continue
        if _normalize_label(value) in HEADER_LABELS:
            continue
        return value
    return None


def _normalize_document_code(value: str) -> str:
    normalized = _normalize_search_text(value).upper()
    normalized = re.sub(r"\s*-\s*", "-", normalized)
    normalized = re.sub(r"\s*\.\s*", ".", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return normalized.strip(" .:-")


def _normalize_revision(value: str) -> str:
    normalized = value.strip().upper()
    if normalized.isdigit():
        return normalized.zfill(2)
    return normalized


def _normalize_label(value: str) -> str:
    normalized = _normalize_search_text(value).lower()
    normalized = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_search_text(value: str) -> str:
    repaired = _repair_mojibake(value)
    for dash in DASH_TRANSLATIONS:
        repaired = repaired.replace(dash, "-")
    return unicodedata.normalize("NFKD", repaired).encode("ascii", "ignore").decode("ascii")


def _repair_mojibake(value: str) -> str:
    try:
        return value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return value
