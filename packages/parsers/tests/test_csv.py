from pathlib import Path

from parsers.base import ExtractionError
from parsers.csv_parser import CSVParser


def test_good_csv_extracts(tmp_path: Path) -> None:
    path = tmp_path / "good.csv"
    path.write_text("serviço,preço\nlimpeza,120\npeeling,200\n", encoding="utf-8")
    result = CSVParser().extract(path)
    assert result.error is None
    assert result.sheets[0].sheet_name == "sheet1"
    assert result.sheets[0].rows[0]["serviço"] == "limpeza"


def test_semicolon_csv_extracts(tmp_path: Path) -> None:
    path = tmp_path / "semicolon.csv"
    path.write_text("serviço;preço\nlimpeza;120\n", encoding="utf-8")
    result = CSVParser().extract(path)
    assert result.error is None
    assert result.sheets[0].headers == ["serviço", "preço"]


def test_csv_rows_exceeded(tmp_path: Path) -> None:
    path = tmp_path / "many.csv"
    lines = ["col"] + [str(index) for index in range(10_001)]
    path.write_text("\n".join(lines), encoding="utf-8")
    result = CSVParser().extract(path)
    assert result.error == ExtractionError.ROWS_EXCEEDED
