from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]


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


def _get(rest: Any, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
    response = rest.get(path, params=params)
    if response.status_code != 200:
        raise RuntimeError(f"{path} query failed: {response.status_code} {response.text}")
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError(f"{path} returned non-list payload")
    return data


def build_source_report(rest: Any, workspace_id: str, source_id: str) -> dict[str, Any]:
    source_rows = _get(
        rest,
        "/sources",
        {
            "workspace_id": f"eq.{workspace_id}",
            "id": f"eq.{source_id}",
            "select": "id,status,original_filename,storage_path,created_at",
        },
    )
    job_rows = _get(
        rest,
        "/processing_jobs",
        {
            "workspace_id": f"eq.{workspace_id}",
            "source_id": f"eq.{source_id}",
            "select": "id,job_type,status,chunk_id,error_message,metadata,created_at,updated_at",
            "order": "created_at.asc",
        },
    )
    chunk_rows = _get(
        rest,
        "/chunks",
        {
            "workspace_id": f"eq.{workspace_id}",
            "source_id": f"eq.{source_id}",
            "select": "id,status,chunk_index,created_at",
            "order": "chunk_index.asc",
        },
    )
    fact_rows = _get(
        rest,
        "/extracted_facts",
        {
            "workspace_id": f"eq.{workspace_id}",
            "source_id": f"eq.{source_id}",
            "select": "id,fact_type,status,confidence,chunk_id,created_at",
            "order": "created_at.asc",
        },
    )
    rule_rows = _get(
        rest,
        "/business_rules",
        {
            "workspace_id": f"eq.{workspace_id}",
            "source_id": f"eq.{source_id}",
            "select": "id,rule_type,status,confidence,chunk_id,created_at",
            "order": "created_at.asc",
        },
    )
    unknown_rows = _get(
        rest,
        "/unknown_facts_queue",
        {
            "workspace_id": f"eq.{workspace_id}",
            "source_id": f"eq.{source_id}",
            "select": "id,status,suggested_fact_type,chunk_id,created_at",
            "order": "created_at.asc",
        },
    )
    return {
        "workspace_id": workspace_id,
        "source_id": source_id,
        "source": source_rows[0] if source_rows else None,
        "counts": {
            "jobs": len(job_rows),
            "chunks": len(chunk_rows),
            "facts": len(fact_rows),
            "rules": len(rule_rows),
            "unknowns": len(unknown_rows),
        },
        "jobs": job_rows,
        "chunks": chunk_rows,
        "facts": fact_rows,
        "rules": rule_rows,
        "unknowns": unknown_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose a Supabase source pipeline run.")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    with supabase_rest() as rest:
        report = build_source_report(rest, args.workspace_id, args.source_id)

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
