from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from parsers.base import ExtractedPage, ExtractionError, ExtractionResult

fitz = pytest.importorskip("fitz")
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "industrial" / "benchmark_dirty_documents.py"
DEFAULT_PAGE_PROFILE_SUMMARY = {
    "page_count": 0,
    "text_pages": 0,
    "image_pages": 0,
    "ocr_required_pages": [],
    "ocr_risk_pages": [],
    "empty_pages": [],
    "image_only_pages": [],
    "table_candidate_pages": [],
    "table_risk_pages": [],
    "header_detected_pages": [],
    "footer_detected_pages": [],
    "layout_complexity_counts": {},
    "layout_complexity": {},
    "text_layer_type_counts": {},
    "risk_code_counts": {},
    "risk_codes": {},
}


def load_benchmark() -> Any:
    module_name = "industrial_dirty_benchmark_under_test"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_cli(module: Any, argv: list[str]) -> int:
    try:
        result = module.main(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return int(result or 0)


def read_report(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def test_benchmark_writes_stable_json_shape_for_successful_document(tmp_path: Path) -> None:
    benchmark = load_benchmark()
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    output = tmp_path / "benchmark.json"
    source = input_dir / "POP-QA-014_Rev04_vigent.txt"
    source.write_text(
        "\n".join([
            "Codigo: POP-QA-014",
            "Revisao: 04",
            "Titulo: Controle de Nao Conformidades",
            "Area dona: Qualidade",
                "Status: Vigente",
                "1.1 Objetivo",
                "Item    Responsavel    Status",
                "Toda nao conformidade deve ser registrada.",
                "Figura 1 - Fluxo de registro de NC.",
            ]),
        encoding="utf-8",
    )

    code = run_cli(benchmark, ["--input-dir", str(input_dir), "--output", str(output)])

    assert code == 0
    report = read_report(output)
    assert report["schema_version"] == "industrial_dirty_benchmark.v1"
    assert "generated_at" not in report
    assert report["input_root"] == "docs"
    assert report["summary"]["document_count"] == 1
    assert report["summary"]["parsed_count"] == 1
    assert report["summary"]["failed_count"] == 0
    assert report["expected_documents"]["present_count"] == 0
    assert "missing" in report["expected_documents"]
    document = report["documents"][0]
    assert document["document_id"] == "pop-qa-014-rev04-vigent"
    assert document["relative_path"] == "POP-QA-014_Rev04_vigent.txt"
    assert document["mime_type"] == "text/plain"
    assert "file_size_bytes" in document
    assert "extracted_char_count" in document
    assert "size_bytes" not in document
    assert "total_chars" not in document
    assert document["parser_error"] is None
    assert document["metadata"]["document_code"] == "POP-QA-014"
    assert document["metadata"]["revision"] == "04"
    assert document["metadata"]["status"] == "vigent"
    assert document["page_profile_summary"] == DEFAULT_PAGE_PROFILE_SUMMARY
    assert document["gap_codes"] == []
    assert document["structure_hint_count"] >= 1
    assert document["section_diagnostics"]["summary"]["section_count"] >= 1
    assert document["section_diagnostics"]["summary"]["section_path_count"] >= 1
    assert document["chunk_diagnostics"]["total_chunk_count"] >= 1
    assert document["chunk_diagnostics"]["section_path_chunk_count"] >= 1
    assert document["semantic_diagnostics"]["total_candidate_count"] >= 1
    assert "candidate_kind_counts" in document["semantic_diagnostics"]
    assert document["table_figure_diagnostics"]["total_candidate_count"] >= 1
    assert "candidate_kind_counts" in document["table_figure_diagnostics"]
    assert "total_packet_count" in document["review_packet_summary"]
    assert "reason_code_counts" in document["review_packet_summary"]
    assert "section_count" in report["summary"]
    assert report["summary"]["section_count"] >= 1
    assert report["summary"]["chunk_count"] >= 1
    assert report["summary"]["section_path_chunk_count"] >= 1
    assert report["summary"]["semantic_candidate_count"] >= 1
    assert report["summary"]["table_figure_candidate_count"] >= 1
    assert "review_packet_count" in report["summary"]
    assert "review_packet_reason_counts" in report["summary"]
    assert "elapsed_ms" in document
    assert str(tmp_path) not in output.read_text(encoding="utf-8")


def test_benchmark_records_parser_error_without_crashing(tmp_path: Path) -> None:
    benchmark = load_benchmark()
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    output = tmp_path / "benchmark.json"
    (input_dir / "broken.pdf").write_bytes(b"not a real pdf")

    code = run_cli(benchmark, ["--input-dir", str(input_dir), "--output", str(output)])

    assert code == 0
    document = read_report(output)["documents"][0]
    assert document["relative_path"] == "broken.pdf"
    assert document["parser_error"] == "parse_failed"
    assert document["quality"]["passed"] is False
    assert document["quality"]["rejection_reason"] == "parse_failed"
    assert document["page_count"] is None
    assert document["embedded_image_count"] is None
    assert set(document["gap_codes"]) == {"missing_document_code", "missing_revision"}


def test_benchmark_splits_pages_exceeded_pdf_across_two_workers(
    tmp_path: Path,
) -> None:
    benchmark = load_benchmark()
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    output = tmp_path / "benchmark.json"
    (input_dir / "ponte-pop-pmpr-fotos.pdf").write_bytes(b"%PDF fake enough for monkeypatch")

    class FakeParser:
        def extract(self, _path: Path) -> ExtractionResult:
            return ExtractionResult(
                mime_type="application/pdf",
                error=ExtractionError.PAGES_EXCEEDED,
            )

    benchmark.get_parser = lambda _mime_type: FakeParser()
    benchmark._pdf_metrics = lambda _path: {
        "page_count": 374,
        "embedded_image_count": 306,
    }
    benchmark._extract_pdf_pages_with_workers = lambda **_kwargs: [
        ExtractedPage(
            page_number=1,
            text=(
                "ACME QMS\n"
                "Codigo: POP-PMPR-001\n"
                "Revisao: 01\n"
                "1 Objetivo\n"
                "procedimento operacional com fotos\n"
                "Documento controlado"
            ),
            char_count=132,
            is_empty=False,
        ),
        ExtractedPage(
            page_number=2,
            text=(
                "ACME QMS\n"
                "1.1 Aplicacao\n"
                + ("procedimento operacional com fotos\n" * 4)
                + "Documento controlado"
            ),
            char_count=169,
            is_empty=False,
        ),
    ]

    code = run_cli(benchmark, ["--input-dir", str(input_dir), "--output", str(output)])

    assert code == 0
    report = read_report(output)
    assert report["summary"]["parser_errors"] == {}
    assert report["summary"]["split_processed_count"] == 1
    document = report["documents"][0]
    assert document["parser_error"] is None
    assert document["processing"] == {
        "mode": "split_pages",
        "worker_count": 2,
        "original_parser_error": "pages_exceeded",
        "page_ranges": [[0, 187], [187, 374]],
    }
    assert document["page_count"] == 374
    assert document["embedded_image_count"] == 306
    assert document["page_profile_summary"] == DEFAULT_PAGE_PROFILE_SUMMARY
    assert document["section_diagnostics"]["summary"]["boilerplate_counts"] == {
        "footer": 2,
        "header": 2,
    }
    assert [
        (span["section_path"], span["page_start"])
        for span in document["section_diagnostics"]["section_spans"]
    ] == [("1", 1), ("1/1.1", 2)]
    assert document["quality"]["passed"] is True
    assert document["quality"]["rejection_reason"] is None
    assert document["extracted_char_count"] > 100
    assert document["known_findings"] == []


def test_benchmark_copies_pdf_page_profile_summary_from_normal_parser(
    tmp_path: Path,
) -> None:
    benchmark = load_benchmark()
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    output = tmp_path / "benchmark.json"
    source = input_dir / "table-like.pdf"
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((72, 72), "Codigo: POP-QA-020")
    page.insert_text((72, 120), "Etapa    Responsavel    Status")
    page.insert_text((72, 180), "Validar procedimento industrial")
    document.save(source)
    document.close()

    code = run_cli(benchmark, ["--input-dir", str(input_dir), "--output", str(output)])

    assert code == 0
    report_document = read_report(output)["documents"][0]
    summary = report_document["page_profile_summary"]
    assert summary["page_count"] == 1
    assert summary["text_pages"] == 1
    assert summary["table_candidate_pages"] == [1]
    assert summary["table_risk_pages"] == [1]
    assert summary["text_layer_type_counts"]["digital_text"] == 1


def test_benchmark_records_expected_processing_mode_changed(tmp_path: Path) -> None:
    benchmark = load_benchmark()
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    output = tmp_path / "benchmark.json"
    (input_dir / "ponte-pop-pmpr-fotos.pdf").write_bytes(b"%PDF fake enough for monkeypatch")

    class FakeParser:
        def extract(self, _path: Path) -> ExtractionResult:
            text = "Procedimento Operacional Padrao com conteudo textual extraido.\n" * 4
            return ExtractionResult(
                mime_type="application/pdf",
                pages=[
                    ExtractedPage(
                        page_number=1,
                        text=text,
                        char_count=len(text),
                        is_empty=False,
                    )
                ],
                total_chars=len(text),
            )

    benchmark.get_parser = lambda _mime_type: FakeParser()
    benchmark._pdf_metrics = lambda _path: {
        "page_count": 374,
        "embedded_image_count": 306,
    }

    code = run_cli(benchmark, ["--input-dir", str(input_dir), "--output", str(output)])

    assert code == 0
    document = read_report(output)["documents"][0]
    assert document["processing"]["mode"] == "single_parser"
    assert document["known_findings"] == [
        {
            "kind": "expected_processing_mode_changed",
            "expected": "split_pages",
            "actual": "single_parser",
        }
    ]


def test_benchmark_records_metadata_gaps_and_known_findings(tmp_path: Path) -> None:
    benchmark = load_benchmark()
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    output = tmp_path / "benchmark.json"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({
            "documents": [
                {
                    "filename": "manual-fotovoltaico.txt",
                    "expected_code": "BLU002",
                }
            ]
        }),
        encoding="utf-8",
    )
    source = input_dir / "manual-fotovoltaico.txt"
    source.write_text(
        "\n".join([
            "Procedimento Operacional Padrao",
            "TITULO: Instalacao do KIT Fotovoltaico Bluesun",
            "REVISAO",
            "00",
        ]),
        encoding="utf-8",
    )

    code = run_cli(
        benchmark,
        [
            "--input-dir",
            str(input_dir),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
    )

    assert code == 0
    document = read_report(output)["documents"][0]
    assert document["document_id"] == "manual-fotovoltaico"
    assert document["metadata"]["document_code"] is None
    assert document["metadata"]["revision"] == "00"
    assert document["gap_codes"] == ["missing_document_code"]
    assert document["known_findings"] == [
        {
            "kind": "expected_code_missed",
            "expected": "BLU002",
            "actual": None,
        }
    ]


def test_benchmark_bootstraps_parser_source_path_for_standalone_cli() -> None:
    parser_src = ROOT / "packages" / "parsers" / "src"
    original_path = list(sys.path)
    sys.path = [
        path
        for path in sys.path
        if Path(path).resolve() != parser_src
    ]

    try:
        load_benchmark()

        assert sys.path[0] == str(parser_src)
    finally:
        sys.path = original_path
