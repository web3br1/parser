import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
from semantic_metrics import compute_semantic_metrics, export_predictions_from_tables

ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT / "examples" / "pilot_semireal"
MANIFEST_PATH = DATASET_DIR / "manifest.json"

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8005").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SMOKE_EMAIL = os.getenv("SMOKE_USER_EMAIL", "owner@example.test")
SMOKE_PASSWORD = os.getenv("SMOKE_USER_PASSWORD", "SmokeTest1234!")
POLL_INTERVAL = int(os.getenv("SEMIREAL_POLL_INTERVAL", "10"))
POLL_TIMEOUT = int(os.getenv("SEMIREAL_POLL_TIMEOUT", "3600"))
HTTP_TIMEOUT = float(os.getenv("SEMIREAL_HTTP_TIMEOUT", "180"))

MIME_TYPES = {
    "csv": "text/csv",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "txt": "text/plain",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
TERMINAL_JOB_STATUSES = {"succeeded", "failed", "dead_letter"}
ACTIVE_JOB_STATUSES = {"queued", "running", "retrying"}


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
API_BASE = os.getenv("API_BASE_URL", API_BASE).rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", SUPABASE_URL).rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", SUPABASE_ANON_KEY)
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_SERVICE_ROLE_KEY)


def api(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        headers={"Authorization": f"Bearer {token}"},
        timeout=HTTP_TIMEOUT,
    )


def rest() -> httpx.Client:
    return httpx.Client(
        base_url=f"{SUPABASE_URL}/rest/v1",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        },
        timeout=HTTP_TIMEOUT,
    )


def auth_admin() -> httpx.Client:
    return httpx.Client(
        base_url=f"{SUPABASE_URL}/auth/v1/admin",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        },
        timeout=HTTP_TIMEOUT,
    )


def require_env() -> None:
    missing = [
        name
        for name, value in {
            "SUPABASE_URL": SUPABASE_URL,
            "SUPABASE_ANON_KEY": SUPABASE_ANON_KEY,
            "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE_KEY,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing required env: {', '.join(missing)}")


def ensure_user(email: str, password: str) -> None:
    with auth_admin() as client:
        response = client.post(
            "/users",
            json={"email": email, "password": password, "email_confirm": True},
        )
    if response.status_code not in {200, 201, 422}:
        raise RuntimeError(f"user_create_failed {email}: {response.status_code} {response.text}")


def get_jwt(email: str, password: str) -> str:
    response = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": SUPABASE_ANON_KEY},
        json={"email": email, "password": password},
        timeout=HTTP_TIMEOUT,
    )
    if response.status_code != 200:
        raise RuntimeError(f"login_failed {email}: {response.status_code} {response.text}")
    return str(response.json()["access_token"])


def rest_get(path: str, params: dict[str, str]) -> list[dict[str, Any]]:
    with rest() as client:
        response = client.get(path, params=params)
    if response.status_code != 200:
        raise RuntimeError(f"rest_get_failed {path}: {response.status_code} {response.text}")
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError(f"rest_get_non_list {path}: {data}")
    return data


def create_workspace(token: str) -> dict[str, Any]:
    stamp = int(time.time())
    with api(token) as client:
        response = client.post(
            "/workspaces",
            json={"name": f"Semi-real Pilot v1 {stamp}", "slug": f"pilot-semireal-v1-{stamp}"},
        )
    if response.status_code not in {200, 201}:
        raise RuntimeError(f"workspace_create_failed: {response.status_code} {response.text}")
    return response.json()


def get_workspace(workspace_id: str) -> dict[str, Any]:
    rows = rest_get(
        "/workspaces",
        {"id": f"eq.{workspace_id}", "select": "id,name,slug,status,created_at"},
    )
    if not rows:
        raise RuntimeError(f"workspace_not_found {workspace_id}")
    return rows[0]


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def upload_document(token: str, workspace_id: str, item: dict[str, Any]) -> dict[str, Any]:
    path = DATASET_DIR / item["filename"]
    mime_type = MIME_TYPES[item["format"]]
    with path.open("rb") as handle, api(token) as client:
        response = client.post(
            f"/workspaces/{workspace_id}/sources/upload",
            files={"file": (item["filename"], handle, mime_type)},
        )
    if response.status_code not in {200, 201, 202}:
        raise RuntimeError(f"upload_failed {item['filename']}: {response.status_code} {response.text}")
    payload = response.json()
    return {
        "filename": item["filename"],
        "format": item["format"],
        "source_id": payload["source_id"],
        "job_id": payload["job_id"],
        "status_code": response.status_code,
    }


def uploads_from_workspace(workspace_id: str, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    sources = rest_get(
        "/sources",
        {
            "workspace_id": f"eq.{workspace_id}",
            "select": "id,original_filename",
            "order": "created_at.asc",
        },
    )
    ingest_jobs = rest_get(
        "/processing_jobs",
        {
            "workspace_id": f"eq.{workspace_id}",
            "job_type": "eq.ingest",
            "select": "id,source_id",
            "order": "created_at.asc",
        },
    )
    jobs_by_source = {row["source_id"]: row["id"] for row in ingest_jobs}
    formats_by_name = {item["filename"]: item["format"] for item in manifest["documents"]}
    return [
        {
            "filename": source["original_filename"],
            "format": formats_by_name.get(source["original_filename"], "unknown"),
            "source_id": source["id"],
            "job_id": jobs_by_source.get(source["id"]),
            "status_code": None,
        }
        for source in sources
    ]


def summarize_jobs(workspace_id: str) -> dict[str, Any]:
    rows = rest_get(
        "/processing_jobs",
        {
            "workspace_id": f"eq.{workspace_id}",
            "select": "id,source_id,chunk_id,job_type,status,error_message,created_at,updated_at,finished_at",
            "order": "created_at.asc",
        },
    )
    by_status = Counter(str(row.get("status")) for row in rows)
    by_type = Counter(str(row.get("job_type")) for row in rows)
    failures = [row for row in rows if row.get("status") in {"failed", "dead_letter"}]
    active = [row for row in rows if row.get("status") in ACTIVE_JOB_STATUSES]
    return {
        "total": len(rows),
        "by_status": dict(sorted(by_status.items())),
        "by_type": dict(sorted(by_type.items())),
        "active": active,
        "failures": failures,
        "rows": rows,
    }


def collect_tables(workspace_id: str) -> dict[str, list[dict[str, Any]]]:
    return {
        "sources": rest_get(
            "/sources",
            {
                "workspace_id": f"eq.{workspace_id}",
                "select": "id,original_filename,status,created_at,updated_at",
                "order": "created_at.asc",
            },
        ),
        "chunks": rest_get(
            "/chunks",
            {
                "workspace_id": f"eq.{workspace_id}",
                "select": "id,source_id,chunk_index,status,created_at,updated_at",
                "order": "created_at.asc",
            },
        ),
        "facts": rest_get(
            "/extracted_facts",
            {
                "workspace_id": f"eq.{workspace_id}",
                "select": (
                    "id,source_id,chunk_id,fact_type,status,confidence,content,"
                    "normalized_content,created_at,updated_at"
                ),
                "order": "created_at.asc",
            },
        ),
        "rules": rest_get(
            "/business_rules",
            {
                "workspace_id": f"eq.{workspace_id}",
                "select": (
                    "id,source_id,chunk_id,rule_type,status,confidence,condition,action,"
                    "created_at,updated_at"
                ),
                "order": "created_at.asc",
            },
        ),
        "unknowns": rest_get(
            "/unknown_facts_queue",
            {
                "workspace_id": f"eq.{workspace_id}",
                "select": "id,source_id,chunk_id,status,suggested_fact_type,confidence,metadata,created_at,updated_at",
                "order": "created_at.asc",
            },
        ),
        "published_facts": rest_get(
            "/published_facts",
            {
                "workspace_id": f"eq.{workspace_id}",
                "select": (
                    "id,source_id,chunk_id,fact_type,status,confidence,content,"
                    "normalized_content,created_at,updated_at"
                ),
                "order": "created_at.asc",
            },
        ),
        "published_rules": rest_get(
            "/published_rules",
            {
                "workspace_id": f"eq.{workspace_id}",
                "select": (
                    "id,source_id,chunk_id,rule_type,status,confidence,condition,action,"
                    "created_at,updated_at"
                ),
                "order": "created_at.asc",
            },
        ),
    }


def wait_for_pipeline(workspace_id: str) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    deadline = time.time() + POLL_TIMEOUT
    stable_terminal_polls = 0
    while time.time() < deadline:
        jobs = summarize_jobs(workspace_id)
        tables = collect_tables(workspace_id)
        snapshot = {
            "elapsed_seconds": round(POLL_TIMEOUT - (deadline - time.time()), 1),
            "jobs_by_status": jobs["by_status"],
            "jobs_by_type": jobs["by_type"],
            "sources": len(tables["sources"]),
            "chunks": len(tables["chunks"]),
            "facts": len(tables["facts"]),
            "rules": len(tables["rules"]),
            "unknowns": len(tables["unknowns"]),
            "published_facts": len(tables["published_facts"]),
            "published_rules": len(tables["published_rules"]),
        }
        timeline.append(snapshot)
        print(json.dumps({"stage": "poll", **snapshot}, sort_keys=True))
        if not jobs["active"] and jobs["total"] >= len(tables["sources"]):
            stable_terminal_polls += 1
        else:
            stable_terminal_polls = 0
        if stable_terminal_polls >= 3:
            return timeline
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"pipeline_timeout after {POLL_TIMEOUT}s")


def review_and_publish(token: str, workspace_id: str) -> dict[str, Any]:
    tables = collect_tables(workspace_id)
    actions: list[dict[str, Any]] = []
    with api(token) as client:
        for fact in tables["facts"]:
            if fact["status"] not in {"extracted", "needs_review", "approved"}:
                continue
            approve = client.post(
                f"/workspaces/{workspace_id}/review/facts/{fact['id']}/approve",
                json={"note": "semi-real automated technical approval; semantic QA pending"},
            )
            publish = client.post(f"/workspaces/{workspace_id}/review/facts/{fact['id']}/publish")
            actions.append({
                "resource_type": "fact",
                "id": fact["id"],
                "approve_status": approve.status_code,
                "publish_status": publish.status_code,
            })
        for rule in tables["rules"]:
            if rule["status"] not in {"extracted", "needs_review", "approved"}:
                continue
            approve = client.post(
                f"/workspaces/{workspace_id}/review/rules/{rule['id']}/approve",
                json={"note": "semi-real automated technical approval; semantic QA pending"},
            )
            publish = client.post(f"/workspaces/{workspace_id}/review/rules/{rule['id']}/publish")
            actions.append({
                "resource_type": "rule",
                "id": rule["id"],
                "approve_status": approve.status_code,
                "publish_status": publish.status_code,
            })
    return {
        "actions": actions,
        "failed_actions": [
            action
            for action in actions
            if action["approve_status"] not in {200, 201} or action["publish_status"] not in {200, 201}
        ],
    }


def summarize_tables(tables: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "counts": {name: len(rows) for name, rows in tables.items()},
        "source_statuses": dict(Counter(str(row.get("status")) for row in tables["sources"])),
        "chunk_statuses": dict(Counter(str(row.get("status")) for row in tables["chunks"])),
        "fact_statuses": dict(Counter(str(row.get("status")) for row in tables["facts"])),
        "rule_statuses": dict(Counter(str(row.get("status")) for row in tables["rules"])),
        "unknown_statuses": dict(Counter(str(row.get("status")) for row in tables["unknowns"])),
        "fact_types": dict(Counter(str(row.get("fact_type")) for row in tables["facts"])),
        "rule_types": dict(Counter(str(row.get("rule_type")) for row in tables["rules"])),
    }


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    final = report["final_summary"]
    post = report["post_review_summary"]
    jobs = report["jobs"]
    lines = [
        "# Semi-Real Pilot v1 Run Report",
        "",
        f"Run id: `{report['run_id']}`",
        f"Workspace id: `{report['workspace_id']}`",
        f"Status: `{report['status']}`",
        f"API base: `{report['api_base']}`",
        "",
        "## Dataset",
        "",
        f"- Documents expected: {report['manifest']['document_count']}",
        f"- Documents uploaded: {len(report['uploads'])}",
        f"- Formats: {', '.join(report['manifest']['formats'])}",
        "",
        "## Pipeline Outputs",
        "",
        f"- Jobs total: {jobs['total']}",
        f"- Jobs by status: `{json.dumps(jobs['by_status'], sort_keys=True)}`",
        f"- Jobs by type: `{json.dumps(jobs['by_type'], sort_keys=True)}`",
        f"- Job failures: {len(jobs['failures'])}",
        "",
        "## Pre-Review Summary",
        "",
        f"- Counts: `{json.dumps(final['counts'], sort_keys=True)}`",
        f"- Chunk statuses: `{json.dumps(final['chunk_statuses'], sort_keys=True)}`",
        f"- Fact statuses: `{json.dumps(final['fact_statuses'], sort_keys=True)}`",
        f"- Rule statuses: `{json.dumps(final['rule_statuses'], sort_keys=True)}`",
        f"- Unknown statuses: `{json.dumps(final['unknown_statuses'], sort_keys=True)}`",
        f"- Fact types: `{json.dumps(final['fact_types'], sort_keys=True)}`",
        f"- Rule types: `{json.dumps(final['rule_types'], sort_keys=True)}`",
        "",
        "## Review/Publish Outputs",
        "",
        f"- Actions attempted: {len(report['review']['actions'])}",
        f"- Failed actions: {len(report['review']['failed_actions'])}",
        f"- Post-review counts: `{json.dumps(post['counts'], sort_keys=True)}`",
        f"- Post-review fact statuses: `{json.dumps(post['fact_statuses'], sort_keys=True)}`",
        f"- Post-review rule statuses: `{json.dumps(post['rule_statuses'], sort_keys=True)}`",
        "",
        "## Acceptance Gates",
        "",
        f"- Mechanical pass: `{report['mechanical_pass']}`",
        f"- Semantic pass: `{report['semantic_pass']}`",
        f"- Semantic precision: `{report['semantic_report']['precision']}`",
        f"- Semantic recall: `{report['semantic_report']['recall']}`",
        f"- Semantic predictions exported: {len(report['semantic_predictions'])}",
        "",
        "## Source Outputs",
        "",
        "| File | Source ID | Upload Job ID |",
        "|---|---|---|",
    ]
    for upload in report["uploads"]:
        lines.append(f"| `{upload['filename']}` | `{upload['source_id']}` | `{upload['job_id']}` |")
    lines.extend([
        "",
        "## Notes",
        "",
        "- Review/publish actions are automated technical approvals for synthetic data only.",
        "- Semantic correctness still requires comparing extracted content against `examples/pilot_semireal/manifest.json`.",
        "- Unknown queue items are intentionally not auto-resolved.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the semi-real pilot dataset end to end.")
    parser.add_argument("--output", default=".run/semireal-pilot-v1-report.json")
    parser.add_argument("--markdown-output", default="docs/07-qa/SEMIREAL_PILOT_V1_RUN_REPORT.md")
    parser.add_argument("--workspace-id")
    args = parser.parse_args()

    require_env()
    ensure_user(SMOKE_EMAIL, SMOKE_PASSWORD)
    token = get_jwt(SMOKE_EMAIL, SMOKE_PASSWORD)
    manifest = load_manifest()
    run_id = f"semireal-v1-{int(time.time())}"
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with api(token) as client:
        health = client.get("/health")
    if health.status_code != 200:
        raise RuntimeError(f"api_health_failed: {health.status_code} {health.text}")

    workspace = get_workspace(args.workspace_id) if args.workspace_id else create_workspace(token)
    workspace_id = workspace["id"]
    if args.workspace_id:
        uploads = uploads_from_workspace(workspace_id, manifest)
    else:
        uploads = []
        for item in manifest["documents"]:
            upload = upload_document(token, workspace_id, item)
            uploads.append(upload)
            print(json.dumps({"stage": "upload", **upload}, sort_keys=True))

    timeline = wait_for_pipeline(workspace_id)
    tables = collect_tables(workspace_id)
    final_summary = summarize_tables(tables)
    jobs = summarize_jobs(workspace_id)
    review = review_and_publish(token, workspace_id)
    post_review_tables = collect_tables(workspace_id)
    post_review_summary = summarize_tables(post_review_tables)
    semantic_predictions = export_predictions_from_tables(post_review_tables)
    semantic_report = compute_semantic_metrics(manifest, semantic_predictions)
    semantic_report["workspace_id"] = workspace_id
    semantic_report["mechanical_pass"] = not (jobs["failures"] or review["failed_actions"])
    semantic_report["semantic_pass"] = semantic_report["semantic_gate"]["passed"]
    finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    mechanical_pass = not (jobs["failures"] or review["failed_actions"])
    semantic_pass = semantic_report["semantic_gate"]["passed"]
    status = "passed" if mechanical_pass and semantic_pass else "failed"

    report = {
        "run_id": run_id,
        "status": status,
        "api_base": API_BASE,
        "started_at": started_at,
        "finished_at": finished_at,
        "workspace": workspace,
        "workspace_id": workspace_id,
        "mechanical_pass": mechanical_pass,
        "semantic_pass": semantic_pass,
        "manifest": {
            "document_count": manifest["document_count"],
            "formats": manifest["formats"],
        },
        "uploads": uploads,
        "timeline": timeline,
        "jobs": jobs,
        "final_summary": final_summary,
        "post_review_summary": post_review_summary,
        "review": review,
        "tables": post_review_tables,
        "semantic_predictions": semantic_predictions,
        "semantic_report": semantic_report,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown_report(Path(args.markdown_output), report)
    print(json.dumps({"status": status, "workspace_id": workspace_id, "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
