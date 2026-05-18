import re
from dataclasses import dataclass


@dataclass(frozen=True)
class InjectionCheckResult:
    injection_suspected: bool
    matched_patterns: list[str]


_PATTERNS_EN: list[str] = [
    r"ignore\s+(all\s+)?previous\s+instructions?",
    r"ignore\s+(all\s+)?prior\s+instructions?",
    r"disregard\s+(your\s+)?(previous\s+)?instructions?",
    r"you\s+are\s+now\s+a",
    r"act\s+as\s+(if\s+you\s+(are|were)\s+)?a",
    r"new\s+instructions?:",
    r"system\s*:\s*ignore",
    r"<\s*/?system\s*>",
    r"prompt\s*injection",
    r"jailbreak",
]

_PATTERNS_PT: list[str] = [
    r"ignore\s+as\s+instruções\s+anteriores",
    r"desconsidere\s+as\s+instruções",
    r"novas\s+instruções\s*:",
    r"você\s+agora\s+é",
    r"finja\s+ser",
    r"aja\s+como",
    r"esqueça\s+(tudo|as\s+instruções)",
    r"a\s+partir\s+de\s+agora\s+você\s+é",
    r"novo\s+papel\s*:",
    r"instrução\s+do\s+sistema\s*:",
]

INJECTION_PATTERNS: list[str] = _PATTERNS_EN + _PATTERNS_PT


def check_injection(text: str) -> InjectionCheckResult:
    """
    Verifica se o texto contém padrões de prompt injection em EN e PT-BR.
    Case-insensitive. Falhas internas não bloqueiam o pipeline.
    """
    matched: list[str] = []
    try:
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                matched.append(pattern)
    except Exception:
        pass
    return InjectionCheckResult(
        injection_suspected=len(matched) > 0,
        matched_patterns=matched,
    )
