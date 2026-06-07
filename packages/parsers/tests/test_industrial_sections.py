from parsers.base import ExtractedPage
from parsers.industrial_sections import resolve_document_sections


def _page(page_number: int, text: str) -> ExtractedPage:
    return ExtractedPage(
        page_number=page_number,
        text=text,
        char_count=len(text),
        is_empty=False,
    )


def test_marks_recurring_header_and_footer_as_boilerplate_without_deleting_text() -> None:
    pages = [
        _page(
            1,
            "ACME QMS Manual\n"
            "1 Objetivo\n"
            "Definir criterios do procedimento.\n"
            "Documento controlado",
        ),
        _page(
            2,
            "ACME QMS Manual\n"
            "1.1 Aplicacao\n"
            "Aplica-se a producao industrial.\n"
            "Documento controlado",
        ),
        _page(
            3,
            "ACME QMS Manual\n"
            "2 Responsabilidades\n"
            "A qualidade deve revisar registros.\n"
            "Documento controlado",
        ),
    ]

    diagnostics = resolve_document_sections(pages)

    assert [page.text for page in pages] == [
        "ACME QMS Manual\n"
        "1 Objetivo\n"
        "Definir criterios do procedimento.\n"
        "Documento controlado",
        "ACME QMS Manual\n"
        "1.1 Aplicacao\n"
        "Aplica-se a producao industrial.\n"
        "Documento controlado",
        "ACME QMS Manual\n"
        "2 Responsabilidades\n"
        "A qualidade deve revisar registros.\n"
        "Documento controlado",
    ]
    assert [
        (span.kind, span.page_number, span.line_index, span.quote)
        for span in diagnostics.boilerplate_spans
    ] == [
        ("header", 1, 0, "ACME QMS Manual"),
        ("footer", 1, 3, "Documento controlado"),
        ("header", 2, 0, "ACME QMS Manual"),
        ("footer", 2, 3, "Documento controlado"),
        ("header", 3, 0, "ACME QMS Manual"),
        ("footer", 3, 3, "Documento controlado"),
    ]


def test_marks_page_number_footer_lines_as_boilerplate_even_when_numbers_change() -> None:
    pages = [
        _page(1, "1 Objetivo\nConteudo tecnico.\nPagina 1 de 3"),
        _page(2, "1.1 Aplicacao\nConteudo tecnico.\nPagina 2 de 3"),
        _page(3, "2 Registros\nConteudo tecnico.\nPagina 3 de 3"),
    ]

    diagnostics = resolve_document_sections(pages)

    assert [
        (span.kind, span.page_number, span.line_index, span.quote)
        for span in diagnostics.boilerplate_spans
    ] == [
        ("footer", 1, 2, "Pagina 1 de 3"),
        ("footer", 2, 2, "Pagina 2 de 3"),
        ("footer", 3, 2, "Pagina 3 de 3"),
    ]


def test_builds_section_spans_with_stable_paths_and_page_bounds() -> None:
    pages = [
        _page(
            1,
            "ACME QMS Manual\n"
            "1 Objetivo\n"
            "Definir criterios do procedimento.\n"
            "Documento controlado",
        ),
        _page(
            2,
            "ACME QMS Manual\n"
            "1.1 Aplicacao\n"
            "Aplica-se a producao industrial.\n"
            "Documento controlado",
        ),
        _page(
            3,
            "ACME QMS Manual\n"
            "2 Responsabilidades\n"
            "A Qualidade deve revisar registros.\n"
            "Documento controlado",
        ),
    ]

    diagnostics = resolve_document_sections(pages)

    assert [
        (span.section_path, span.section_title, span.page_start, span.page_end)
        for span in diagnostics.section_spans
    ] == [
        ("1", "Objetivo", 1, 1),
        ("1/1.1", "Aplicacao", 2, 2),
        ("2", "Responsabilidades", 3, 3),
    ]
    assert diagnostics.risk_codes == []


def test_ambiguous_heading_is_reported_as_risk_without_section_assignment() -> None:
    diagnostics = resolve_document_sections([
        _page(
            1,
            "ESCOPO\n"
            "Texto com conteudo operacional suficiente.\n"
            "1 Objetivo\n"
            "Definir o controle documental.",
        )
    ])

    assert diagnostics.section_spans[0].section_path == "1"
    assert "ambiguous_section_heading" in diagnostics.risk_codes


def test_builds_hierarchical_section_paths_for_numbered_headings() -> None:
    pages = [
        _page(
            1,
            "1 Objetivo\n"
            "Definir o processo.\n"
            "1.1 Aplicacao\n"
            "Linhas produtivas abrangidas.\n"
            "1.1.1 Turno de operacao\n"
            "Detalhar responsabilidades por turno.",
        )
    ]

    diagnostics = resolve_document_sections(pages)

    assert [
        (span.kind, span.label, span.title, span.section_path)
        for span in diagnostics.section_spans
    ] == [
        ("numbered_heading", "1", "Objetivo", "1"),
        ("numbered_heading", "1.1", "Aplicacao", "1/1.1"),
        (
            "numbered_heading",
            "1.1.1",
            "Turno de operacao",
            "1/1.1/1.1.1",
        ),
    ]


def test_builds_canonical_section_paths_for_common_qms_headings() -> None:
    pages = [
        _page(
            1,
            "OBJETIVO\n"
            "Padronizar a atividade.\n"
            "Aplicacao\n"
            "Linhas fabris e laboratorio.\n"
            "RESPONSABILIDADES\n"
            "Qualidade e producao.\n"
            "PROCEDIMENTO\n"
            "Executar conforme instrucao.\n"
            "Registros\n"
            "Guardar evidencias.\n"
            "ANEXOS\n"
            "Fluxos complementares.",
        )
    ]

    diagnostics = resolve_document_sections(pages)

    assert [
        (span.kind, span.label, span.title, span.section_path)
        for span in diagnostics.section_spans
    ] == [
        ("qms_heading", "objetivo", "OBJETIVO", "objetivo"),
        ("qms_heading", "aplicacao", "Aplicacao", "aplicacao"),
        (
            "qms_heading",
            "responsabilidades",
            "RESPONSABILIDADES",
            "responsabilidades",
        ),
        ("qms_heading", "procedimento", "PROCEDIMENTO", "procedimento"),
        ("qms_heading", "registros", "Registros", "registros"),
        ("qms_heading", "anexos", "ANEXOS", "anexos"),
    ]


def test_reports_ambiguous_section_heading_when_unumbered_qms_heading_repeats() -> None:
    pages = [
        _page(1, "ACME QMS\nObjetivo\nDefinir uso.\nDocumento controlado"),
        _page(2, "ACME QMS\nObjetivo\nRepetido em outro bloco.\nDocumento controlado"),
    ]

    diagnostics = resolve_document_sections(pages)

    assert diagnostics.risk_codes == ["ambiguous_section_heading"]
    assert [
        (span.kind, span.page_number, span.line_index, span.section_path)
        for span in diagnostics.section_spans
    ] == [
        ("qms_heading", 1, 1, "objetivo"),
        ("qms_heading", 2, 1, "objetivo"),
    ]


def test_preserves_original_line_indexes_when_blank_lines_are_present() -> None:
    diagnostics = resolve_document_sections([
        _page(
            1,
            "\n"
            "ACME QMS\n"
            "\n"
            "1 Objetivo\n"
            "Definir uso.\n"
            "\n"
            "Documento controlado",
        ),
        _page(
            2,
            "\n"
            "ACME QMS\n"
            "\n"
            "2 Registros\n"
            "Guardar evidencias.\n"
            "\n"
            "Documento controlado",
        ),
    ])

    assert [
        (span.kind, span.page_number, span.line_index)
        for span in diagnostics.boilerplate_spans
    ] == [
        ("header", 1, 1),
        ("footer", 1, 6),
        ("header", 2, 1),
        ("footer", 2, 6),
    ]
    assert [
        (span.section_path, span.page_number, span.line_index)
        for span in diagnostics.section_spans
    ] == [
        ("1", 1, 3),
        ("2", 2, 3),
    ]


def test_repeated_qms_heading_at_page_edge_is_not_erased_as_header() -> None:
    diagnostics = resolve_document_sections([
        _page(1, "Objetivo\nDefinir uso.\nDocumento controlado"),
        _page(2, "Objetivo\nRepetido em outro bloco.\nDocumento controlado"),
    ])

    assert [
        (span.kind, span.page_number, span.line_index, span.quote)
        for span in diagnostics.boilerplate_spans
    ] == [
        ("footer", 1, 2, "Documento controlado"),
        ("footer", 2, 2, "Documento controlado"),
    ]
    assert [
        (span.kind, span.page_number, span.line_index, span.section_path)
        for span in diagnostics.section_spans
    ] == [
        ("qms_heading", 1, 0, "objetivo"),
        ("qms_heading", 2, 0, "objetivo"),
    ]
    assert diagnostics.risk_codes == ["ambiguous_section_heading"]


def test_section_hierarchy_gap_is_localized_on_section_span() -> None:
    diagnostics = resolve_document_sections([
        _page(1, "1.1 Aplicacao\nLinhas abrangidas.")
    ])

    assert diagnostics.section_spans[0].section_path == "1.1"
    assert diagnostics.section_spans[0].risk_codes == ("section_hierarchy_gap",)
    assert diagnostics.risk_codes == ["section_hierarchy_gap"]
