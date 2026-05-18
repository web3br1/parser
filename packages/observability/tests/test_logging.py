import json

from observability.logging import get_logger, redact_payload


def test_redact_payload_removes_secrets() -> None:
    payload = {
        "authorization": "Bearer secret",
        "nested": {"api_key": "secret"},
        "safe": "ok",
    }

    assert redact_payload(payload) == {
        "authorization": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]"},
        "safe": "ok",
    }


def test_redact_payload_removes_secret_material_inside_strings() -> None:
    openai_like_key = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    jwt_like_token = "eyJ" + "aaa.bbb.ccc"
    payload = {
        "stack": f"failed with {openai_like_key}",
        "message": f"Authorization: Bearer {jwt_like_token}",
        "items": [f"token {openai_like_key}"],
    }

    redacted = redact_payload(payload)

    assert redacted["stack"] == "failed with [REDACTED]"
    assert redacted["message"] == "Authorization: [REDACTED]"
    assert redacted["items"] == ["token [REDACTED]"]


def test_logger_writes_json_line(capsys) -> None:
    logger = get_logger("test-service")

    logger.info("event_name", job_id="job-1", authorization="secret")

    output = capsys.readouterr().out.strip()
    line = json.loads(output)
    assert line["service"] == "test-service"
    assert line["event"] == "event_name"
    assert line["authorization"] == "[REDACTED]"


def test_exception_logger_omits_stack_in_production(monkeypatch, capsys) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    logger = get_logger("test-service")

    logger.exception("failed", RuntimeError("postgres://user:pass@example/db"))

    output = capsys.readouterr().out.strip()
    line = json.loads(output)
    assert line["event"] == "failed"
    assert line["error_type"] == "RuntimeError"
    assert line["stack"] is None
    assert "postgres://user:pass" not in output
