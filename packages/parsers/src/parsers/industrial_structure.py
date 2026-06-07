from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

SECTION_RE = re.compile(r"^\s*(?P<label>\d+(?:\.\d+)*)(?:[\.)])?\s+(?P<title>\S.+?)\s*$")
ANNEX_RE = re.compile(r"^\s*ANEXO\s+(?P<label>[IVXLCDM]+|\d+)\s*[-–:]?\s*(?P<title>.*?)\s*$", re.IGNORECASE)
TABLE_RE = re.compile(r"^\s*Tabela\s+(?P<label>\d+)\s*[-–:]?\s*(?P<title>.*?)\s*$", re.IGNORECASE)
FORM_FIELD_RE = re.compile(r"^\s*(?P<label>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 /_-]{2,40})\s*:\s*(?P<value>.+?)\s*$")

QMS_HEADING_KEYS = {
    "objetivo",
    "aplicacao",
    "responsabilidades",
    "procedimento",
    "registros",
    "anexos",
}


@dataclass(frozen=True)
class IndustrialStructureHint:
    kind: str
    label: str
    title: str | None
    char_start: int
    char_end: int
    section_path: str | None = None
    risk_codes: tuple[str, ...] = ()


def extract_structure_hints(text: str) -> list[IndustrialStructureHint]:
    hints: list[IndustrialStructureHint] = []
    offset = 0
    section_stack: dict[int, str] = {}
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.strip()
        start = offset + raw_line.find(line) if line else offset
        end = start + len(line)
        if line:
            hint = hint_from_line(line, start, end, section_stack=section_stack)
            if hint is not None:
                hints.append(hint)
        offset += len(raw_line)
    return hints


def hint_from_line(
    line: str,
    start: int,
    end: int,
    *,
    section_stack: dict[int, str] | None = None,
) -> IndustrialStructureHint | None:
    section_stack = section_stack if section_stack is not None else {}

    section = SECTION_RE.match(line)
    if section:
        label = section.group("label")
        title = section.group("title").strip()
        level = label.count(".") + 1
        parent_missing = level > 1 and any(
            parent_level not in section_stack for parent_level in range(1, level)
        )
        for existing_level in list(section_stack):
            if existing_level >= level:
                del section_stack[existing_level]
        section_stack[level] = label
        return IndustrialStructureHint(
            kind="section",
            label=label,
            title=title,
            char_start=start,
            char_end=end,
            section_path=label if parent_missing else _numbered_section_path(label),
            risk_codes=("section_hierarchy_gap",) if parent_missing else (),
        )

    qms_key = qms_heading_key(line)
    if qms_key in QMS_HEADING_KEYS:
        section_stack.clear()
        return IndustrialStructureHint(
            kind="section",
            label=qms_key,
            title=line.strip(),
            char_start=start,
            char_end=end,
            section_path=qms_key,
        )

    for kind, pattern in (
        ("annex", ANNEX_RE),
        ("table", TABLE_RE),
    ):
        match = pattern.match(line)
        if match:
            return IndustrialStructureHint(
                kind=kind,
                label=match.group("label"),
                title=(match.group("title") or "").strip() or None,
                char_start=start,
                char_end=end,
            )

    if _looks_like_ambiguous_heading(line):
        return IndustrialStructureHint(
            kind="ambiguous_section",
            label=line.strip(),
            title=line.strip(),
            char_start=start,
            char_end=end,
            risk_codes=("ambiguous_section_heading",),
        )

    field = FORM_FIELD_RE.match(line)
    if field and not line.startswith("|"):
        return IndustrialStructureHint(
            kind="form_field",
            label=field.group("label").strip(),
            title=field.group("value").strip(),
            char_start=start,
            char_end=end,
        )
    return None


def qms_heading_key(line: str) -> str:
    decomposed = unicodedata.normalize("NFKD", line.strip())
    ascii_line = decomposed.encode("ascii", errors="ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_line.strip(" :.-")).casefold()


def _numbered_section_path(label: str) -> str:
    parts = label.split(".")
    return "/".join(".".join(parts[:index]) for index in range(1, len(parts) + 1))


def _looks_like_ambiguous_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return False
    if any(marker in stripped for marker in (":", "|")) or stripped.endswith((".", ",")):
        return False
    if not any(character.isalpha() for character in stripped):
        return False
    if len(stripped.split()) > 4:
        return False
    return stripped.isupper() or stripped.istitle()
