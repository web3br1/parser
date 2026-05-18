from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.status_code = 200
        self._payload = payload
        self.text = repr(payload)

    def json(self) -> object:
        return self._payload


class MetricsRest:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.payloads = {
            "/chunks": [
                {"id": "chunk-1", "status": "extracted"},
                {"id": "chunk-2", "status": "needs_review"},
                {"id": "chunk-3", "status": "failed"},
            ],
            "/extracted_facts": [
                {"id": "fact-1", "status": "published"},
                {"id": "fact-2", "status": "approved"},
                {"id": "fact-3", "status": "needs_review"},
                {"id": "fact-4", "status": "failed"},
            ],
            "/business_rules": [
                {"id": "rule-1", "status": "published"},
                {"id": "rule-2", "status": "needs_review"},
            ],
            "/unknown_facts_queue": [
                {"id": "unknown-1", "status": "open"},
            ],
            "/processing_jobs": [
                {"id": "job-1", "status": "failed"},
                {"id": "job-2", "status": "succeeded"},
            ],
            "/validation_events": [
                {"id": "event-1", "action": "approved"},
                {"id": "event-2", "action": "edited"},
                {"id": "event-3", "action": "published"},
            ],
        }

    def get(self, path: str, params: dict[str, str]) -> FakeResponse:
        self.calls.append((path, params))
        return FakeResponse(self.payloads[path])


def test_build_pilot_metrics_report_counts_quality_rates() -> None:
    module = load_module(
        ROOT / "scripts" / "pilot" / "pilot_metrics.py",
        "pilot_metrics_under_test",
    )

    report = module.build_pilot_metrics_report(MetricsRest(), "workspace-id")

    assert report["workspace_id"] == "workspace-id"
    assert report["counts"]["chunks_total"] == 3
    assert report["counts"]["facts_total"] == 4
    assert report["counts"]["rules_total"] == 2
    assert report["counts"]["unknown_total"] == 1
    assert report["counts"]["critical_errors"] == 3
    assert report["rates"]["approval_rate"] == 0.5
    assert report["rates"]["edit_rate"] == 0.5
    assert report["rates"]["unknown_rate"] == 0.3333
    assert report["gates"]["approval_rate"]["passed"] is False
    assert report["gates"]["edit_rate"]["passed"] is False
    assert report["gates"]["unknown_rate"]["passed"] is False
    assert report["gates"]["critical_error"]["passed"] is False


def test_pilot_metrics_filters_by_period_when_provided() -> None:
    module = load_module(
        ROOT / "scripts" / "pilot" / "pilot_metrics.py",
        "pilot_metrics_period_under_test",
    )
    rest = MetricsRest()

    module.build_pilot_metrics_report(
        rest,
        "workspace-id",
        since="2026-05-01T00:00:00Z",
        until="2026-05-12T23:59:59Z",
    )

    for _path, params in rest.calls:
        assert params["workspace_id"] == "eq.workspace-id"
        assert params["and"] == (
            "(created_at.gte.2026-05-01T00:00:00Z,"
            "created_at.lte.2026-05-12T23:59:59Z)"
        )
