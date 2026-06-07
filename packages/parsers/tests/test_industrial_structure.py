from parsers.industrial_structure import extract_structure_hints


def test_extracts_numbered_sections() -> None:
    hints = extract_structure_hints(
        "5 Abertura\n"
        "5.2 Abertura de NC\n"
        "Toda nao conformidade deve ser registrada.\n"
        "5.3 Investigacao\n"
        "O responsavel deve investigar."
    )

    sections = [hint for hint in hints if hint.kind == "section"]
    assert sections[0].label == "5"
    assert sections[0].title == "Abertura"
    assert sections[0].section_path == "5"
    assert sections[1].label == "5.2"
    assert sections[1].title == "Abertura de NC"
    assert sections[1].section_path == "5/5.2"
    assert sections[2].label == "5.3"
    assert sections[2].title == "Investigacao"
    assert sections[2].section_path == "5/5.3"


def test_extracts_common_qms_headings_with_canonical_section_paths() -> None:
    hints = extract_structure_hints(
        "OBJETIVO\n"
        "Definir controles.\n"
        "Aplicacao\n"
        "Linhas de producao.\n"
        "Responsabilidades\n"
        "Qualidade e Producao.\n"
    )

    sections = [hint for hint in hints if hint.kind == "section"]
    assert [
        (hint.label, hint.title, hint.section_path)
        for hint in sections
    ] == [
        ("objetivo", "OBJETIVO", "objetivo"),
        ("aplicacao", "Aplicacao", "aplicacao"),
        ("responsabilidades", "Responsabilidades", "responsabilidades"),
    ]


def test_ambiguous_heading_gets_risk_code_without_section_path() -> None:
    hints = extract_structure_hints(
        "ESCOPO\n"
        "Texto explicativo.\n"
        "Definicoes\n"
        "Outro texto explicativo.\n"
        "1 Objetivo\n"
        "Conteudo.\n"
    )

    ambiguous = [hint for hint in hints if hint.kind == "ambiguous_section"]
    assert ambiguous[0].label == "ESCOPO"
    assert ambiguous[0].section_path is None
    assert ambiguous[0].risk_codes == ("ambiguous_section_heading",)
    assert ambiguous[1].label == "Definicoes"
    assert ambiguous[1].section_path is None
    assert ambiguous[1].risk_codes == ("ambiguous_section_heading",)


def test_numbered_subsection_without_parent_keeps_local_path_with_risk() -> None:
    hints = extract_structure_hints(
        "1.1 Aplicacao\n"
        "Linhas abrangidas.\n"
    )

    section = [hint for hint in hints if hint.kind == "section"][0]
    assert section.section_path == "1.1"
    assert section.risk_codes == ("section_hierarchy_gap",)


def test_extracts_annex_and_form_fields() -> None:
    hints = extract_structure_hints(
        "ANEXO I - Fluxo de Aprovacao\n"
        "Responsavel: Gerente da Qualidade\n"
        "Data de aprovacao: 2026-01-15\n"
    )

    assert any(hint.kind == "annex" and hint.label == "I" for hint in hints)
    assert any(hint.kind == "form_field" and hint.label == "Responsavel" for hint in hints)
    assert any(hint.kind == "form_field" and hint.label == "Data de aprovacao" for hint in hints)


def test_extracts_table_heading() -> None:
    hints = extract_structure_hints(
        "Tabela 2 - Criterios de Aceitacao\n"
        "| Item | Criterio |\n"
        "| A | Conforme |\n"
    )

    assert any(
        hint.kind == "table"
        and hint.label == "2"
        and hint.title == "Criterios de Aceitacao"
        for hint in hints
    )


def test_extracts_root_numbered_and_qms_headings_with_section_paths() -> None:
    hints = extract_structure_hints(
        "1 Objetivo\n"
        "Definir o processo.\n"
        "1.1 Aplicacao\n"
        "Linhas abrangidas.\n"
        "Responsabilidades\n"
        "Qualidade aprova registros.\n"
    )

    sections = [hint for hint in hints if hint.kind == "section"]
    assert [
        (hint.label, hint.title, hint.section_path)
        for hint in sections
    ] == [
        ("1", "Objetivo", "1"),
        ("1.1", "Aplicacao", "1/1.1"),
        ("responsabilidades", "Responsabilidades", "responsabilidades"),
    ]
