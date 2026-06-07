from parsers.chunker import RawChunk
from parsers.industrial_semantics import (
    extract_semantic_candidates,
    summarize_semantic_candidates,
)


def _chunk(text: str, *, section_path: str = "5/5.2", section_title: str = "Procedimento") -> RawChunk:
    return RawChunk(
        chunk_index=0,
        text=text,
        char_count=len(text),
        token_estimate=len(text) // 4,
        chunk_hash="hash-001",
        source_page=7,
        sheet_name=None,
        row_start=None,
        row_end=None,
        section_heading=section_title,
        metadata={"parser": "pdf"},
        page_start=7,
        page_end=8,
        section_path=section_path,
        section_title=section_title,
        chunk_kind="numbered_heading",
    )


def test_extracts_requirement_with_quote_section_path_and_confidence() -> None:
    candidates = extract_semantic_candidates([
        _chunk("Toda nao conformidade deve ser registrada no FOR-QA-002.")
    ])

    requirement = candidates[0]
    assert requirement.kind == "requirement"
    assert requirement.normalized_text == "Toda nao conformidade deve ser registrada no FOR-QA-002."
    assert requirement.normalized_content == {
        "requirement": "Toda nao conformidade deve ser registrada no FOR-QA-002.",
        "modality": "mandatory",
    }
    assert requirement.confidence == 0.82
    assert requirement.evidence.quote == "Toda nao conformidade deve ser registrada no FOR-QA-002."
    assert requirement.evidence.section_path == "5/5.2"
    assert requirement.evidence.page_start == 7
    assert requirement.evidence.page_end == 8


def test_extracts_responsibility_from_explicit_role_action() -> None:
    candidates = extract_semantic_candidates([
        _chunk("O Gerente da Qualidade deve aprovar CAPA critica.")
    ])

    responsibility = [candidate for candidate in candidates if candidate.kind == "responsibility"][0]
    assert responsibility.normalized_content == {
        "role": "Gerente da Qualidade",
        "responsibility": "aprovar CAPA critica.",
    }
    assert responsibility.evidence.quote == "O Gerente da Qualidade deve aprovar CAPA critica."


def test_extracts_record_and_form_references_with_identifier() -> None:
    candidates = extract_semantic_candidates([
        _chunk("Registro obrigatorio: FOR-QA-002 - Registro de Nao Conformidade.")
    ])

    references = [candidate for candidate in candidates if candidate.kind in {"record_reference", "form_reference"}]
    assert [
        (candidate.kind, candidate.normalized_content)
        for candidate in references
    ] == [
        (
            "form_reference",
            {"identifier": "FOR-QA-002", "name": "Registro de Nao Conformidade."},
        ),
        (
            "record_reference",
            {"identifier": "FOR-QA-002", "name": "Registro de Nao Conformidade."},
        ),
    ]


def test_extracts_anexo_reference_without_form_identifier() -> None:
    candidates = extract_semantic_candidates([
        _chunk("Anexo I - Fluxo de Aprovacao de CAPA.")
    ])

    annex = [candidate for candidate in candidates if candidate.kind == "record_reference"][0]
    assert annex.normalized_content == {
        "identifier": "ANEXO I",
        "name": "Fluxo de Aprovacao de CAPA.",
    }


def test_extracts_equipment_reference() -> None:
    candidates = extract_semantic_candidates([
        _chunk("Equipamento: Torquimetro digital TQ-01 calibrado.")
    ])

    equipment = [candidate for candidate in candidates if candidate.kind == "equipment_reference"][0]
    assert equipment.normalized_content == {
        "equipment": "Torquimetro digital TQ-01 calibrado.",
    }


def test_extracts_ordered_procedure_steps_within_section() -> None:
    candidates = extract_semantic_candidates([
        _chunk(
            "1. Abrir registro de NC.\n"
            "2. Avaliar causa raiz.\n"
            "3. Encerrar CAPA apos verificacao.",
            section_path="6",
        )
    ])

    steps = [candidate for candidate in candidates if candidate.kind == "procedure_step"]
    assert [
        candidate.normalized_content
        for candidate in steps
    ] == [
        {"step_label": "1", "instruction": "Abrir registro de NC.", "order": 1},
        {"step_label": "2", "instruction": "Avaliar causa raiz.", "order": 2},
        {"step_label": "3", "instruction": "Encerrar CAPA apos verificacao.", "order": 3},
    ]
    assert all(step.evidence.section_path == "6" for step in steps)


def test_orders_procedure_steps_across_chunks_in_same_section() -> None:
    first = _chunk("1. Abrir registro de NC.", section_path="6")
    second = RawChunk(
        **{
            **first.__dict__,
            "chunk_index": 1,
            "text": "2. Avaliar causa raiz.",
            "char_count": len("2. Avaliar causa raiz."),
            "chunk_hash": "hash-002",
        }
    )

    steps = [
        candidate
        for candidate in extract_semantic_candidates([first, second])
        if candidate.kind == "procedure_step"
    ]

    assert [step.normalized_content["order"] for step in steps] == [1, 2]


def test_extracts_lowercase_form_identifier_name_without_inflating_line() -> None:
    candidates = extract_semantic_candidates([
        _chunk("Registro obrigatorio: for-qa-002 - Registro de Nao Conformidade.")
    ])

    form = [candidate for candidate in candidates if candidate.kind == "form_reference"][0]
    assert form.normalized_content == {
        "identifier": "FOR-QA-002",
        "name": "Registro de Nao Conformidade.",
    }


def test_extracts_responsibility_with_accented_role_prefix() -> None:
    candidates = extract_semantic_candidates([
        _chunk("O Responsável Técnico é responsável por liberar a linha.")
    ])

    responsibility = [candidate for candidate in candidates if candidate.kind == "responsibility"][0]
    assert responsibility.normalized_content == {
        "role": "Responsável Técnico",
        "responsibility": "liberar a linha.",
    }


def test_avoids_toc_and_generic_role_false_positives() -> None:
    candidates = extract_semantic_candidates([
        _chunk(
            "SUMARIO\n"
            "FOR-QA-002 Registro de Nao Conformidade........11\n"
            "A qualidade do produto deve ser verificada.\n"
            "1.1 Aplicacao........9",
            section_title="Sumario",
        )
    ])

    assert [candidate.kind for candidate in candidates] == ["requirement"]


def test_sumario_section_without_dot_leaders_does_not_promote_references() -> None:
    candidates = extract_semantic_candidates([
        _chunk(
            "FOR-QA-002 Registro de Nao Conformidade\n"
            "Anexo I Fluxo de Aprovacao",
            section_title="Sumario",
        )
    ])

    assert candidates == []


def test_summarizes_semantic_candidates_by_kind() -> None:
    candidates = extract_semantic_candidates([
        _chunk(
            "Toda nao conformidade deve ser registrada.\n"
            "1. Abrir registro de NC."
        )
    ])

    summary = summarize_semantic_candidates(candidates)

    assert summary["total_candidate_count"] == 2
    assert summary["candidate_kind_counts"] == {
        "procedure_step": 1,
        "requirement": 1,
    }
