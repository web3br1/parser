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
