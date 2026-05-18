from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from worker_extraction.extractor import ExtractionOutput, extract


def _mock_response(content: str, input_tokens: int = 10, output_tokens: int = 20) -> MagicMock:
    resp = MagicMock()
    resp.raw_response = content
    resp.model_name = "gpt-4o"
    resp.prompt_version = "abc123"
    resp.input_tokens = input_tokens
    resp.output_tokens = output_tokens
    return resp


def _ok_service_price() -> str:
    return json.dumps({
        "status": "ok",
        "fact_type": "service_price",
        "data": {
            "service_name": "Corte feminino",
            "price_amount": 120.0,
            "currency": "BRL",
            "price_type": "fixed",
        },
        "evidence_span": {"quote": "Corte feminino R$120", "char_start": None, "char_end": None},
        "ambiguities": [],
    })


def _ok_business_hours_multi() -> str:
    return json.dumps({
        "status": "ok",
        "fact_type": "business_hours",
        "data": [
            {"day_of_week": "mon", "open_time": "09:00", "close_time": "18:00", "is_closed": False},
            {"day_of_week": "tue", "open_time": "09:00", "close_time": "18:00", "is_closed": False},
            {"day_of_week": "sat", "open_time": "09:00", "close_time": "13:00", "is_closed": False},
        ],
        "evidence_span": {"quote": "Seg a Sab", "char_start": None, "char_end": None},
        "ambiguities": [],
    })


@patch("worker_extraction.extractor.get_model_gateway")
def test_extract_ok_service_price(mock_gw: MagicMock) -> None:
    mock_gw.return_value.extract.return_value = _mock_response(_ok_service_price())
    output = extract("Corte feminino R$120", "service_price")
    assert output.status == "ok"
    assert output.validated_data["service_name"] == "Corte feminino"
    assert output.evidence_quote == "Corte feminino R$120"
    assert output.is_multi is False


@patch("worker_extraction.extractor.get_model_gateway")
def test_extract_llm_status_failed(mock_gw: MagicMock) -> None:
    payload = json.dumps({
        "status": "failed",
        "fact_type": "service_price",
        "data": {},
        "evidence_span": {"quote": ""},
        "ambiguities": [],
    })
    mock_gw.return_value.extract.return_value = _mock_response(payload)
    output = extract("texto", "service_price")
    assert output.status == "failed"


@patch("worker_extraction.extractor.get_model_gateway")
def test_extract_json_malformed(mock_gw: MagicMock) -> None:
    mock_gw.return_value.extract.return_value = _mock_response("not json at all")
    output = extract("texto", "service_price")
    assert output.status == "parse_failed"
    assert output.validated_data == {}


@patch("worker_extraction.extractor.get_model_gateway")
def test_extract_validation_failed(mock_gw: MagicMock) -> None:
    payload = json.dumps({
        "status": "ok",
        "fact_type": "service_price",
        "data": {"service_name": "Corte"},  # missing price_amount, currency, price_type
        "evidence_span": {"quote": "Corte"},
        "ambiguities": [],
    })
    mock_gw.return_value.extract.return_value = _mock_response(payload)
    output = extract("texto", "service_price")
    assert output.status == "validation_failed"
    assert len(output.validation_errors) > 0


@patch("worker_extraction.extractor.get_model_gateway")
def test_extract_business_hours_multi(mock_gw: MagicMock) -> None:
    mock_gw.return_value.extract.return_value = _mock_response(_ok_business_hours_multi())
    output = extract("Seg a Sab 9h-18h", "business_hours")
    assert output.is_multi is True
    assert len(output.records) == 3


@patch("worker_extraction.extractor.get_model_gateway")
def test_extract_business_hours_invalid_item_skipped(mock_gw: MagicMock) -> None:
    payload = json.dumps({
        "status": "ok",
        "fact_type": "business_hours",
        "data": [
            {"day_of_week": "mon", "open_time": "09:00", "close_time": "18:00", "is_closed": False},
            {"day_of_week": "INVALID_DAY"},  # will fail Pydantic validation
        ],
        "evidence_span": {"quote": "Seg", "char_start": None, "char_end": None},
        "ambiguities": [],
    })
    mock_gw.return_value.extract.return_value = _mock_response(payload)
    output = extract("texto", "business_hours")
    assert output.is_multi is True
    assert len(output.records) == 1  # only valid item kept


@patch("worker_extraction.extractor.get_model_gateway")
def test_extract_never_raises_on_parse_error(mock_gw: MagicMock) -> None:
    mock_gw.return_value.extract.return_value = _mock_response("{invalid")
    output = extract("texto", "service_price")
    assert isinstance(output, ExtractionOutput)
    assert output.status == "parse_failed"


@patch("worker_extraction.extractor.get_model_gateway")
def test_extract_tokens_present(mock_gw: MagicMock) -> None:
    mock_gw.return_value.extract.return_value = _mock_response(
        _ok_service_price(), input_tokens=42, output_tokens=17
    )
    output = extract("texto", "service_price")
    assert output.input_tokens == 42
    assert output.output_tokens == 17


@patch("worker_extraction.extractor.get_model_gateway")
def test_extract_contact_info_with_quote(mock_gw: MagicMock) -> None:
    payload = json.dumps({
        "status": "ok",
        "fact_type": "contact_info",
        "data": {"phone": "(11) 99999-9999"},
        "evidence_span": {"quote": "tel: (11) 99999-9999", "char_start": None, "char_end": None},
        "ambiguities": [],
    })
    mock_gw.return_value.extract.return_value = _mock_response(payload)
    output = extract("tel: (11) 99999-9999", "contact_info")
    assert output.status == "ok"
    assert output.evidence_quote == "tel: (11) 99999-9999"
