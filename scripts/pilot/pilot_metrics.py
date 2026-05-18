from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]

APPROVAL_RATE_MIN = 0.70
EDIT_RATE_MAX = 0.30
UNKNOWN_RATE_MAX = 0.25


def load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_dotenv_file(ROOT / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def supabase_rest() -> httpx.Client:
    return httpx.Client(
        base_url=f"{SUPABASE_URL}/rest/v1",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        },
        timeout=30.0,
    )


def build_pilot_metrics_report(
    rest: Any,
    workspace_id: str,
    *,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    chunks = _get_rows(
        rest,
        "/chunks",
        workspace_id,
        "id,status,created_at",
        since=since,
        until=until,
    )
    facts = _get_rows(
        rest,
        "/extracted_facts",
        workspace_id,
        "id,status,created_at",
        since=since,
        until=until,
    )
    rules = _get_rows(
        rest,
        "/business_rules",
        workspace_id,
        "id,status,created_at",
        since=since,
        until=until,
    )
    unknowns = _get_rows(
        rest,
        "/unknown_facts_queue",
        workspace_id,
        "id,status,created_at",
        since=since,
        until=until,
    )
    jobs = _get_rows(
        rest,
        "/processing_jobs",
        workspace_id,
        "id,status,job_type,error_code,error_message,created_at",
        since=since,
        until=until,
    )
    events = _get_rows(
        rest,
        "/validation_events",
        workspace_id,
        "id,action,created_at",
        since=since,
        until=until,
    )

    extracted_total = len(facts) + len(rules)
    approved_total = _count_statuses(facts, {"approved", "published"}) + _count_statuses(
        rules,
        {"approved", "published"},
    )
    validation_decisions = _count_actions(events, {"approved", "published"})
    edited_decisions = _count_actions(events, {"edited"})
    critical_errors = (
        _count_statuses(jobs, {"failed"})
        + _count_statuses(chunks, {"failed"})
        + _count_statuses(facts, {"failed"})
        + _count_statuses(rules, {"failed"})
    )

    rates = {
        "approval_rate": _rate(approved_total, extracted_total),
        "edit_rate": _rate(edited_decisions, validation_decisions),
        "unknown_rate": _rate(len(unknowns), len(chunks)),
    }
    counts = {
        "chunks_total": len(chunks),
        "facts_total": len(facts),
        "rules_total": len(rules),
        "extracted_total": extracted_total,
        "approved_total": approved_total,
        "unknown_total": len(unknowns),
        "validation_events_total": len(events),
        "edited_events": edited_decisions,
        "jobs_total": len(jobs),
        "critical_errors": critical_errors,
    }
    gates = {
        "approval_rate": {
            "threshold": f">= {APPROVAL_RATE_MIN}",
            "value": rates["approval_rate"],
            "passed": rates["approval_rate"] >= APPROVAL_RATE_MIN,
        },
        "edit_rate": {
            "threshold": f"<= {EDIT_RATE_MAX}",
            "value": rates["edit_rate"],
            "passed": rates["edit_rate"] <= EDIT_RATE_MAX,
        },
        "unknown_rate": {
            "threshold": f"<= {UNKNOWN_RATE_MAX}",
            "value": rates["unknown_rate"],
            "passed": rates["unknown_rate"] <= UNKNOWN_RATE_MAX,
        },
        "critical_error": {
            "threshold": "= 0",
            "value": critical_errors,
            "passed": critical_errors == 0,
        },
        "rls_violations": {
            "threshold": "= 0",
            "value": None,
            "passed": None,
            "note": "Use scripts/smoke/supabase_smoke.py --full for the RLS outsider check.",
        },
    }
    return {
        "workspace_id": workspace_id,
        "period": {"since": since, "until": until},
        "counts": counts,
        "rates": rates,
        "gates": gates,
        "passed": all(
            gate["passed"] is True
            for name, gate in gates.items()
            if name != "rls_violations"
        ),
    }


def _get_rows(
    rest: Any,
    path: str,
    workspace_id: str,
    select: str,
    *,
    since: str | None,
    until: str | None,
) -> list[dict[str, Any]]:
    params = {"workspace_id": f"eq.{workspace_id}", "select": select}
    if since and until:
        params["and"] = f"(created_at.gte.{since},created_at.lte.{until})"
    elif since:
        params["created_at"] = f"gte.{since}"
    elif until:
        params["created_at"] = f"lte.{until}"

    response = rest.get(path, params=params)
    if response.status_code != 200:
        raise RuntimeError(f"{path} query failed: {response.status_code} {response.text}")
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError(f"{path} returned non-list payload")
    return data


def _count_statuses(rows: list[dict[str, Any]], statuses: set[str]) -> int:
    return sum(1 for row in rows if row.get("status") in statuses)


def _count_actions(rows: list[dict[str, Any]], actions: set[str]) -> int:
    return sum(1 for row in rows if row.get("action") in actions)


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build pilot quality metrics for a workspace.")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--since", help="Inclusive ISO timestamp filter, e.g. 2026-05-01T00:00:00Z")
    parser.add_argument("--until", help="Inclusive ISO timestamp filter, e.g. 2026-05-12T23:59:59Z")
    parser.add_argument("--output")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    with supabase_rest() as rest:
        report = build_pilot_metrics_report(
            rest,
            args.workspace_id,
            since=args.since,
            until=args.until,
        )

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
