from parsers.chunker import RawChunk
from parsers.industrial_tables import (
    extract_table_figure_candidates,
    summarize_table_figure_candidates,
)


def _chunk(text: str, *, page_start: int = 3, section_path: str = "7") -> RawChunk:
    return RawChunk(
        chunk_index=1,
        text=text,
        char_count=len(text),
        token_estimate=len(text) // 4,
        chunk_hash="chunk-table-001",
        source_page=page_start,
        sheet_name=None,
        row_start=None,
        row_end=None,
        section_heading="Registros",
        metadata={"parser": "pdf"},
        page_start=page_start,
        page_end=page_start,
        section_path=section_path,
        section_title="Registros",
        chunk_kind="numbered_heading",
    )


def test_detects_simple_text_table_candidate_with_evidence() -> None:
    candidates = extract_table_figure_candidates([
        _chunk("Item    Responsavel    Status\nAbertura    Qualidade    Conforme")
    ])

    table = candidates[0]
    assert table.kind == "text_table"
    assert table.quote == "Item    Responsavel    Status\nAbertura    Qualidade    Conforme"
    assert table.page_number == 3
    assert table.section_path == "7"
    assert table.confidence == 0.72


def test_detects_checklist_row_candidates() -> None:
    candidates = extract_table_figure_candidates([
        _chunk("[x] Verificar limpeza da linha - Conforme\n[ ] Registrar desvio - Pendente")
    ])

    checklist = [candidate for candidate in candidates if candidate.kind == "checklist_row"]
    assert [
        candidate.normalized_content
        for candidate in checklist
    ] == [
        {"label": "Verificar limpeza da linha", "status": "conforme"},
        {"label": "Registrar desvio", "status": "pendente"},
    ]


def test_detects_figure_reference_from_caption() -> None:
    candidates = extract_table_figure_candidates([
        _chunk("Figura 1 - Fluxograma de aprovacao de CAPA.")
    ])

    figure = candidates[0]
    assert figure.kind == "figure_reference"
    assert figure.normalized_content == {
        "label": "Figura 1",
        "caption": "Fluxograma de aprovacao de CAPA.",
    }
    assert figure.quote == "Figura 1 - Fluxograma de aprovacao de CAPA."


def test_detects_bare_imagem_and_anexo_references() -> None:
    candidates = extract_table_figure_candidates([
        _chunk("Imagem - Painel eletrico antes da limpeza.\nAnexo - Lista de pecas.")
    ])

    assert [
        (candidate.kind, candidate.normalized_content["label"])
        for candidate in candidates
    ] == [
        ("figure_reference", "Imagem"),
        ("figure_reference", "Anexo"),
    ]


def test_visual_risk_page_without_caption_remains_explicit() -> None:
    candidates = extract_table_figure_candidates(
        [_chunk("Texto curto sem legenda.", page_start=5)],
        page_profiles=[
            {
                "page_number": 5,
                "image_count": 2,
                "text_chars": 24,
                "risk_codes": ["sparse_text_with_images"],
            }
        ],
    )

    visual = [candidate for candidate in candidates if candidate.kind == "visual_risk"][0]
    assert visual.page_number == 5
    assert visual.section_path is None
    assert visual.risk_codes == ("sparse_text_with_images", "visual_content_without_caption")


def test_reference_only_figure_text_does_not_suppress_visual_risk() -> None:
    candidates = extract_table_figure_candidates(
        [_chunk("Ver Figura 1.", page_start=5)],
        page_profiles=[
            {
                "page_number": 5,
                "image_count": 1,
                "text_chars": 13,
                "risk_codes": ["visual_content_without_caption"],
            }
        ],
    )

    assert any(candidate.kind == "figure_reference" for candidate in candidates)
    assert any(candidate.kind == "visual_risk" for candidate in candidates)


def test_candidate_ids_include_page_and_section_metadata() -> None:
    first = _chunk("Item    Responsavel    Status", page_start=3, section_path="7")
    second = _chunk("Item    Responsavel    Status", page_start=4, section_path="8")

    candidates = extract_table_figure_candidates([first, second])

    assert len({candidate.candidate_id for candidate in candidates}) == 2


def test_summarizes_table_figure_candidates() -> None:
    candidates = extract_table_figure_candidates([
        _chunk("Figura 1 - Fluxo.\nItem    Responsavel    Status")
    ])

    summary = summarize_table_figure_candidates(candidates)

    assert summary["total_candidate_count"] == 2
    assert summary["candidate_kind_counts"] == {
        "figure_reference": 1,
        "text_table": 1,
    }
