from hashlib import sha256

from parsers.base import ExtractedPage, ExtractedSheet, ExtractionResult
from parsers.chunker import chunk_extraction


def test_text_chunks_are_continuous_and_hashed() -> None:
    result = ExtractionResult(
        mime_type="text/plain",
        pages=[
            ExtractedPage(
                page_number=1,
                text="Primeiro parágrafo com conteúdo suficiente.\n\nSegundo parágrafo também válido.",
                char_count=74,
                is_empty=False,
            )
        ],
        total_chars=74,
        metadata={"parser": "txt"},
    )
    chunks = chunk_extraction(result)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.text for chunk in chunks)
    assert chunks[0].chunk_hash == sha256(chunks[0].text.encode()).hexdigest()
    assert {"parser", "source_version", "extraction_timestamp"} <= set(chunks[0].metadata)


def test_csv_30_rows_becomes_two_chunks() -> None:
    rows = [{"col": str(index)} for index in range(30)]
    result = ExtractionResult(
        mime_type="text/csv",
        sheets=[ExtractedSheet("sheet1", ["col"], rows, 2, 31)],
        total_chars=60,
        metadata={"parser": "csv"},
    )
    chunks = chunk_extraction(result)
    assert len(chunks) == 2
    assert chunks[0].row_start == 2
    assert chunks[0].row_end == 16
    assert chunks[1].row_start == 17
    assert chunks[1].row_end == 31


def test_empty_extraction_returns_no_chunks() -> None:
    result = ExtractionResult(mime_type="text/plain", pages=[], total_chars=0)
    assert chunk_extraction(result) == []


def test_short_block_is_merged_with_next() -> None:
    result = ExtractionResult(
        mime_type="text/plain",
        pages=[
            ExtractedPage(
                page_number=1,
                text="Curto.\n\nEste bloco tem conteúdo suficiente para receber o bloco anterior.",
                char_count=68,
                is_empty=False,
            )
        ],
        total_chars=68,
        metadata={"parser": "txt"},
    )
    chunks = chunk_extraction(result)
    assert len(chunks) == 1
    assert "Curto." in chunks[0].text


def test_industrial_chunks_include_section_path_page_span_and_kind() -> None:
    result = ExtractionResult(
        mime_type="application/pdf",
        pages=[
            ExtractedPage(
                page_number=1,
                text=(
                    "ACME QMS\n"
                    "1 Objetivo\n"
                    "Definir criterios do procedimento.\n"
                    "Documento controlado"
                ),
                char_count=86,
                is_empty=False,
            )
        ],
        total_chars=86,
        metadata={"parser": "pdf"},
    )
    industrial_context = {
        "boilerplate_spans": [
            {"kind": "header", "page_number": 1, "line_index": 0, "quote": "ACME QMS"},
            {
                "kind": "footer",
                "page_number": 1,
                "line_index": 3,
                "quote": "Documento controlado",
            },
        ],
        "section_spans": [
            {
                "kind": "numbered_heading",
                "page_number": 1,
                "line_index": 1,
                "label": "1",
                "section_title": "Objetivo",
                "section_path": "1",
                "page_start": 1,
                "page_end": 1,
                "risk_codes": [],
            }
        ],
        "risk_codes": [],
    }

    chunks = chunk_extraction(result, industrial_context=industrial_context)

    assert len(chunks) == 1
    assert chunks[0].source_page == 1
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 1
    assert chunks[0].section_heading == "Objetivo"
    assert chunks[0].section_title == "Objetivo"
    assert chunks[0].section_path == "1"
    assert chunks[0].chunk_kind == "numbered_heading"
    assert chunks[0].structure_risk_codes == ()
    assert "ACME QMS" not in chunks[0].text
    assert "Documento controlado" not in chunks[0].text


def test_industrial_chunk_hash_ignores_section_metadata() -> None:
    result = ExtractionResult(
        mime_type="application/pdf",
        pages=[
            ExtractedPage(
                page_number=1,
                text="1 Objetivo\nMesmo texto tecnico.",
                char_count=31,
                is_empty=False,
            )
        ],
        total_chars=31,
        metadata={"parser": "pdf"},
    )
    base_span = {
        "kind": "numbered_heading",
        "page_number": 1,
        "line_index": 0,
        "label": "1",
        "section_title": "Objetivo",
        "section_path": "1",
        "page_start": 1,
        "page_end": 1,
        "risk_codes": [],
    }

    first = chunk_extraction(result, industrial_context={"section_spans": [base_span]})[0]
    second = chunk_extraction(
        result,
        industrial_context={
            "section_spans": [
                {
                    **base_span,
                    "section_title": "Titulo alterado",
                    "section_path": "outro",
                }
            ]
        },
    )[0]

    assert first.text == second.text
    assert first.chunk_hash == second.chunk_hash == sha256(first.text.encode()).hexdigest()


def test_short_industrial_sections_do_not_merge_across_section_paths() -> None:
    result = ExtractionResult(
        mime_type="application/pdf",
        pages=[
            ExtractedPage(
                page_number=1,
                text="1 Objetivo\nCurto.\n2 Registros\nOutro curto.",
                char_count=43,
                is_empty=False,
            )
        ],
        total_chars=43,
        metadata={"parser": "pdf"},
    )
    chunks = chunk_extraction(
        result,
        industrial_context={
            "section_spans": [
                {
                    "kind": "numbered_heading",
                    "page_number": 1,
                    "line_index": 0,
                    "section_title": "Objetivo",
                    "section_path": "1",
                    "page_start": 1,
                    "page_end": 1,
                    "risk_codes": [],
                },
                {
                    "kind": "numbered_heading",
                    "page_number": 1,
                    "line_index": 2,
                    "section_title": "Registros",
                    "section_path": "2",
                    "page_start": 1,
                    "page_end": 1,
                    "risk_codes": ["section_hierarchy_gap", "section_hierarchy_gap"],
                },
            ]
        },
    )

    assert [chunk.section_path for chunk in chunks] == ["1", "2"]
    assert chunks[1].structure_risk_codes == ("section_hierarchy_gap",)


def test_chunker_uses_section_diagnostics_metadata_by_default() -> None:
    result = ExtractionResult(
        mime_type="application/pdf",
        pages=[
            ExtractedPage(
                page_number=1,
                text="1 Objetivo\nMesmo texto tecnico.",
                char_count=31,
                is_empty=False,
            )
        ],
        total_chars=31,
        metadata={
            "parser": "pdf",
            "section_diagnostics": {
                "section_spans": [
                    {
                        "kind": "numbered_heading",
                        "page_number": 1,
                        "line_index": 0,
                        "section_title": "Objetivo",
                        "section_path": "1",
                        "page_start": 1,
                        "page_end": 1,
                        "risk_codes": ["section_hierarchy_gap"],
                    }
                ]
            },
        },
    )

    chunk = chunk_extraction(result)[0]

    assert chunk.section_path == "1"
    assert chunk.metadata["section_path"] == "1"
    assert chunk.metadata["page_start"] == 1
    assert chunk.metadata["page_end"] == 1
    assert chunk.metadata["chunk_kind"] == "numbered_heading"
    assert chunk.metadata["structure_risk_codes"] == ["section_hierarchy_gap"]


def test_malformed_industrial_context_falls_back_to_generic_chunks() -> None:
    result = ExtractionResult(
        mime_type="application/pdf",
        pages=[
            ExtractedPage(
                page_number=1,
                text="Texto tecnico suficiente para chunk generico.",
                char_count=44,
                is_empty=False,
            )
        ],
        total_chars=44,
        metadata={"parser": "pdf"},
    )

    chunks = chunk_extraction(
        result,
        industrial_context={
            "section_spans": [
                {
                    "page_number": "not-a-number",
                    "line_index": "also-bad",
                    "section_path": "1",
                }
            ]
        },
    )

    assert len(chunks) == 1
    assert chunks[0].section_path is None
    assert chunks[0].text == "Texto tecnico suficiente para chunk generico."
