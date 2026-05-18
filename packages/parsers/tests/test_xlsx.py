from pathlib import Path

import pytest
from parsers.base import ExtractionError
from parsers.xlsx_parser import XLSXParser

openpyxl = pytest.importorskip("openpyxl")


def test_good_xlsx_extracts(tmp_path: Path) -> None:
    path = tmp_path / "good.xlsx"
    workbook = openpyxl.Workbook()
    first = workbook.active
    first.title = "servicos"
    first.append(["serviço", "preço"])
    first.append(["limpeza", 120])
    second = workbook.create_sheet("horarios")
    second.append(["dia", "abre"])
    second.append(["segunda", "09:00"])
    workbook.save(path)

    result = XLSXParser().extract(path)
    assert result.error is None
    assert {sheet.sheet_name for sheet in result.sheets} == {"servicos", "horarios"}


def test_xlsx_rows_exceeded(tmp_path: Path) -> None:
    path = tmp_path / "many.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["col"])
    for index in range(10_001):
        sheet.append([index])
    workbook.save(path)

    result = XLSXParser().extract(path)
    assert result.error == ExtractionError.ROWS_EXCEEDED


def test_corrupt_xlsx_parse_failed(tmp_path: Path) -> None:
    path = tmp_path / "bad.xlsx"
    path.write_text("not xlsx", encoding="utf-8")
    result = XLSXParser().extract(path)
    assert result.error == ExtractionError.PARSE_FAILED
