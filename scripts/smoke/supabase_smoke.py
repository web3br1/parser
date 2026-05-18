from __future__ import annotations

import argparse
import json
import os
import sys
import time
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

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
WORKSPACE_STORAGE_BUCKET = os.getenv("WORKSPACE_STORAGE_BUCKET", "context-builder-private")
SMOKE_EMAIL = os.getenv("SMOKE_USER_EMAIL", "owner@example.test")
SMOKE_PASSWORD = os.getenv("SMOKE_USER_PASSWORD", "SmokeTest1234!")
SMOKE_EMAIL_OUTSIDER = os.getenv("SMOKE_OUTSIDER_EMAIL", "outsider@example.test")
SMOKE_PASSWORD_OUTSIDER = os.getenv("SMOKE_OUTSIDER_PASSWORD", "OutsiderTest1234!")
OUTSIDER_CLIENT_READ_TABLES = {"workspaces", "workspace_members", "sources"}
OUTSIDER_API_ONLY_TABLES = {
    "chunks",
    "extracted_facts",
    "business_rules",
    "unknown_facts_queue",
}

parser = argparse.ArgumentParser(description="Run Supabase/API smoke checks.")
parser.add_argument("--full", action="store_true", help="Run full review/publish/RLS smoke.")
parser.add_argument("--json-report", default=os.getenv("SMOKE_REPORT_JSON"))
parser.add_argument("--poll-interval", type=int, default=int(os.getenv("SMOKE_POLL_INTERVAL", "5")))
parser.add_argument("--poll-timeout", type=int, default=int(os.getenv("SMOKE_POLL_TIMEOUT", "300")))
parser.add_argument("--http-timeout", type=float, default=float(os.getenv("SMOKE_HTTP_TIMEOUT", "30")))
parser.add_argument("--no-color", action="store_true", default=bool(os.getenv("NO_COLOR")))
ARGS, _UNKNOWN_ARGS = parser.parse_known_args()

FULL = ARGS.full
REPORT_JSON = ARGS.json_report
POLL_INTERVAL = ARGS.poll_interval
POLL_TIMEOUT = ARGS.poll_timeout
HTTP_TIMEOUT = ARGS.http_timeout

USE_COLOR = not ARGS.no_color and sys.stdout.isatty()
GREEN = "\033[92m" if USE_COLOR else ""
RED = "\033[91m" if USE_COLOR else ""
YELLOW = "\033[93m" if USE_COLOR else ""
RESET = "\033[0m" if USE_COLOR else ""


class SmokeReport:
    def __init__(self, mode: str, api_base: str) -> None:
        self.data: dict[str, Any] = {
            "mode": mode,
            "api_base": api_base,
            "status": "running",
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "steps": [],
        }

    def ok(self, step: str, message: str, **context: Any) -> None:
        self.data["steps"].append({
            "step": step,
            "status": "ok",
            "message": message,
            **{k: v for k, v in context.items() if v is not None},
        })

    def fail(self, step: str, message: str, **context: Any) -> None:
        self.data["status"] = "failed"
        self.data["steps"].append({
            "step": step,
            "status": "failed",
            "message": message,
            **{k: v for k, v in context.items() if v is not None},
        })

    def pass_(self) -> None:
        self.data["status"] = "passed"
        self.data["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def write(self, path: str | Path) -> None:
        if self.data["status"] == "running":
            self.pass_()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")


def ok(msg: str) -> None:
    print(f"{GREEN}  OK {msg}{RESET}")


def fail(msg: str) -> None:
    print(f"{RED}  FAIL {msg}{RESET}")
    sys.exit(1)


def info(msg: str) -> None:
    print(f"{YELLOW}  -> {msg}{RESET}")


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
        fail(f"Missing required env: {', '.join(missing)}")


def _admin() -> httpx.Client:
    return httpx.Client(
        base_url=f"{SUPABASE_URL}/auth/v1/admin",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        },
        timeout=30.0,
    )


def ensure_user(email: str, password: str) -> None:
    with _admin() as client:
        resp = client.post(
            "/users",
            json={"email": email, "password": password, "email_confirm": True},
        )
    if resp.status_code in (200, 201):
        ok(f"User ready: {email}")
    elif resp.status_code == 422 and "already" in resp.text.lower():
        ok(f"User exists: {email}")
    else:
        fail(f"User creation failed for {email}: {resp.status_code} {resp.text}")


def get_jwt(email: str, password: str) -> str:
    resp = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": SUPABASE_ANON_KEY},
        json={"email": email, "password": password},
        timeout=30.0,
    )
    if resp.status_code != 200:
        fail(f"Login failed for {email}: {resp.status_code} {resp.text}")
    return str(resp.json()["access_token"])


def api(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        headers={"Authorization": f"Bearer {token}"},
        timeout=HTTP_TIMEOUT,
    )


def supabase_rest(token: str | None = None, *, service_role: bool = True) -> httpx.Client:
    key = SUPABASE_SERVICE_ROLE_KEY if service_role else SUPABASE_ANON_KEY
    bearer = token or key
    return httpx.Client(
        base_url=f"{SUPABASE_URL}/rest/v1",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {bearer}",
        },
        timeout=30.0,
    )


def step_health(client: httpx.Client) -> None:
    print("\n[1] Health check")
    resp = client.get("/health")
    if resp.status_code != 200:
        fail(f"API unhealthy: {resp.status_code} {resp.text}")
    ok("API is up")


def step_create_workspace(client: httpx.Client) -> str:
    print("\n[2] Create workspace")
    stamp = int(time.time())
    resp = client.post(
        "/workspaces",
        json={"name": f"Smoke Test Workspace {stamp}", "slug": f"smoke-{stamp}"},
    )
    if resp.status_code not in (200, 201):
        fail(f"Workspace creation failed: {resp.status_code} {resp.text}")
    workspace_id = str(resp.json()["id"])
    ok(f"Workspace: {workspace_id}")
    return workspace_id


def smoke_fixture() -> Path:
    fixture = ROOT / "examples" / "good.txt"
    if fixture.exists():
        return fixture
    fallback = Path(os.getenv("TMP", "/tmp")) / f"context-builder-smoke-{int(time.time())}.txt"
    fallback.write_text(
        "Servico: Corte feminino\n"
        "Preco: R$ 120\n"
        "Horario: Segunda a sexta, 09:00 as 18:00\n"
        "Pagamento: pix e cartao\n",
        encoding="utf-8",
    )
    return fallback


def step_upload(client: httpx.Client, workspace_id: str) -> tuple[str, str]:
    print("\n[3] Upload good.txt")
    fixture = smoke_fixture()
    with fixture.open("rb") as handle:
        resp = client.post(
            f"/workspaces/{workspace_id}/sources/upload",
            files={"file": ("good.txt", handle, "text/plain")},
        )
    if resp.status_code not in (200, 201, 202):
        fail(f"Upload failed: {resp.status_code} {resp.text}")
    data = resp.json()
    source_id = str(data["source_id"])
    job_id = str(data["job_id"])
    ok(f"Source: {source_id} | Job: {job_id}")
    return source_id, job_id


def step_poll_ingest(client: httpx.Client, workspace_id: str, source_id: str) -> None:
    print("\n[4] Poll ingest to succeeded")
    deadline = time.time() + POLL_TIMEOUT
    last_status = None
    terminal_failures = {"failed", "failed_processing", "cancelled"}
    while time.time() < deadline:
        resp = client.get(f"/workspaces/{workspace_id}/sources/{source_id}/job")
        if resp.status_code != 200:
            fail(f"Job status failed: {resp.status_code} {resp.text}")
        data = resp.json()
        status = data.get("status")
        if status != last_status:
            info(f"Ingest status: {status}")
            last_status = status
        if status == "succeeded":
            chunks_created = data.get("chunks_created")
            ok(f"Ingest succeeded (chunks_created={chunks_created})")
            return
        if status in terminal_failures:
            fail(f"Ingest failed: {status} {data.get('error_message') or ''}".strip())
        time.sleep(POLL_INTERVAL)
    fail(f"Ingest timeout after {POLL_TIMEOUT}s (last={last_status})")


def step_verify_owner_membership(workspace_id: str, owner_token: str) -> None:
    print("\n[5] Verify owner membership")
    with supabase_rest(owner_token, service_role=False) as rest:
        resp = rest.get(
            "/workspace_members",
            params={
                "workspace_id": f"eq.{workspace_id}",
                "select": "workspace_id,role",
            },
        )
    if resp.status_code != 200:
        fail(f"Owner membership query failed: {resp.status_code} {resp.text}")
    rows = resp.json()
    if not rows or rows[0].get("role") != "owner":
        fail(f"Owner membership missing or not owner: {rows}")
    ok("Owner membership visible through anon JWT")


def step_verify_source_contract(workspace_id: str, source_id: str, job_id: str) -> None:
    print("\n[6] Verify source/job contracts")
    with supabase_rest() as rest:
        source_resp = rest.get(
            "/sources",
            params={
                "id": f"eq.{source_id}",
                "workspace_id": f"eq.{workspace_id}",
                "select": "id,status,storage_path",
            },
        )
        job_resp = rest.get(
            "/processing_jobs",
            params={
                "id": f"eq.{job_id}",
                "workspace_id": f"eq.{workspace_id}",
                "select": "id,status,idempotency_key,metadata",
            },
        )
    if source_resp.status_code != 200:
        fail(f"Source query failed: {source_resp.status_code} {source_resp.text}")
    if job_resp.status_code != 200:
        fail(f"Job query failed: {job_resp.status_code} {job_resp.text}")
    sources = source_resp.json()
    jobs = job_resp.json()
    if not sources:
        fail("Uploaded source not found")
    if not jobs:
        fail("Processing job not found")
    storage_path = sources[0].get("storage_path")
    expected_prefix = f"workspaces/{workspace_id}/sources/{source_id}/original"
    if not isinstance(storage_path, str) or not storage_path.startswith(expected_prefix):
        fail(f"Storage path is not canonical: {storage_path}")
    if not jobs[0].get("idempotency_key"):
        fail("Processing job missing idempotency_key")
    ok("Source storage path and job idempotency_key OK")


def step_verify_chunks(workspace_id: str, source_id: str) -> list[str]:
    print("\n[7] Verify chunks created")
    with supabase_rest() as rest:
        resp = rest.get(
            "/chunks",
            params={
                "workspace_id": f"eq.{workspace_id}",
                "source_id": f"eq.{source_id}",
                "select": "id,status,chunk_index",
                "order": "chunk_index.asc",
            },
        )
    if resp.status_code != 200:
        fail(f"Chunks query failed: {resp.status_code} {resp.text}")
    chunks = resp.json()
    if not chunks:
        fail("No chunks created for source")
    failed_chunks = [
        chunk for chunk in chunks if chunk.get("status") in {"failed", "rejected"}
    ]
    if failed_chunks:
        fail(f"Chunks reached failed statuses: {failed_chunks}")
    statuses = sorted({str(chunk.get("status")) for chunk in chunks})
    ok(f"{len(chunks)} chunk(s) created — statuses: {', '.join(statuses)}")
    return [str(chunk["id"]) for chunk in chunks]


def step_rls_outsider(workspace_id: str) -> None:
    print("\n[8] RLS outsider check")
    ensure_user(SMOKE_EMAIL_OUTSIDER, SMOKE_PASSWORD_OUTSIDER)
    outsider_token = get_jwt(SMOKE_EMAIL_OUTSIDER, SMOKE_PASSWORD_OUTSIDER)
    with api(outsider_token) as outsider:
        resp = outsider.get("/workspaces")
    if resp.status_code != 200:
        fail(f"Outsider workspace list failed: {resp.status_code} {resp.text}")
    workspaces = resp.json()
    ids = [row.get("id") for row in workspaces] if isinstance(workspaces, list) else []
    if workspace_id in ids:
        fail(f"RLS leak: outsider can see workspace {workspace_id}")

    with supabase_rest(outsider_token, service_role=False) as rest:
        checks = {
            "workspaces": rest.get(
                "/workspaces",
                params={"id": f"eq.{workspace_id}", "select": "id"},
            ),
            "workspace_members": rest.get(
                "/workspace_members",
                params={"workspace_id": f"eq.{workspace_id}", "select": "workspace_id"},
            ),
            "sources": rest.get(
                "/sources",
                params={"workspace_id": f"eq.{workspace_id}", "select": "id"},
            ),
            "chunks": rest.get(
                "/chunks",
                params={"workspace_id": f"eq.{workspace_id}", "select": "id"},
            ),
            "extracted_facts": rest.get(
                "/extracted_facts",
                params={"workspace_id": f"eq.{workspace_id}", "select": "id"},
            ),
            "business_rules": rest.get(
                "/business_rules",
                params={"workspace_id": f"eq.{workspace_id}", "select": "id"},
            ),
            "unknown_facts_queue": rest.get(
                "/unknown_facts_queue",
                params={"workspace_id": f"eq.{workspace_id}", "select": "id"},
            ),
        }
    for table, table_resp in checks.items():
        if table in OUTSIDER_API_ONLY_TABLES and table_resp.status_code in {401, 403}:
            continue
        if table_resp.status_code != 200:
            fail(f"Outsider RLS query failed for {table}: {table_resp.status_code} {table_resp.text}")
        if table_resp.json():
            fail(f"RLS leak: outsider can see {table} rows for workspace {workspace_id}")
    ok("Outsider cannot see tenant rows through API or anon REST")


def step_poll_review_queue(client: httpx.Client, workspace_id: str, source_id: str) -> str:
    print("\n[9] Poll review queue")
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        resp = client.get(
            f"/workspaces/{workspace_id}/review",
            params={"source_id": source_id},
        )
        if resp.status_code != 200:
            fail(f"Review queue failed: {resp.status_code} {resp.text}")
        data = resp.json()
        items = data.get("items", [])
        ready = [
            item
            for item in items
            if item.get("facts_total", 0) > 0 or item.get("rules_total", 0) > 0
        ]
        if ready:
            chunk_id = str(ready[0]["chunk_id"])
            ok(f"Review queue ready: {len(items)} item(s), using chunk {chunk_id}")
            return chunk_id
        info(f"Review queue: {len(items)} item(s), waiting for facts/rules")
        time.sleep(POLL_INTERVAL)
    fail(f"Review queue timeout after {POLL_TIMEOUT}s")
    raise AssertionError("unreachable")


def step_approve_and_publish(client: httpx.Client, workspace_id: str, chunk_id: str) -> str:
    print("\n[10] Approve and publish first fact")
    resp = client.get(f"/workspaces/{workspace_id}/review/{chunk_id}")
    if resp.status_code != 200:
        fail(f"Chunk detail failed: {resp.status_code} {resp.text}")
    detail = resp.json()
    facts = detail.get("facts", [])
    if not facts:
        fail("No facts in chunk detail")
    fact = facts[0]
    fact_id = str(fact["id"])
    fact_type = fact.get("fact_type", "?")
    ok(f"Found fact: {fact_id} (type={fact_type})")

    approve = client.post(f"/workspaces/{workspace_id}/review/facts/{fact_id}/approve", json={})
    if approve.status_code not in (200, 201):
        fail(f"Approve failed: {approve.status_code} {approve.text}")
    ok("Fact approved")

    publish = client.post(f"/workspaces/{workspace_id}/review/facts/{fact_id}/publish")
    if publish.status_code not in (200, 201):
        fail(f"Publish failed: {publish.status_code} {publish.text}")
    ok("Fact published")
    return fact_id


def step_verify_published(workspace_id: str, fact_id: str) -> None:
    print("\n[11] Verify published fact")
    with supabase_rest() as rest:
        resp = rest.get(
            "/published_facts",
            params={"workspace_id": f"eq.{workspace_id}", "id": f"eq.{fact_id}"},
        )
    if resp.status_code != 200:
        fail(f"published_facts query failed: {resp.status_code} {resp.text}")
    rows = resp.json()
    if not rows:
        fail(f"Fact {fact_id} not found in published_facts")
    ok(f"Fact in published_facts (type={rows[0].get('fact_type')})")


def cleanup_smoke_data(workspace_id: str | None) -> None:
    if not workspace_id:
        return
    with supabase_rest() as rest:
        rest.patch(
            "/workspaces",
            params={"id": f"eq.{workspace_id}"},
            json={"status": "deleted"},
        )


def main() -> None:
    require_env()
    mode = "FULL" if FULL else "MINIMAL"
    report = SmokeReport(mode, API_BASE)
    print("=" * 60)
    print(f"Context Builder Supabase Smoke [{mode}]")
    print(f"API: {API_BASE}")
    print(f"Bucket: {WORKSPACE_STORAGE_BUCKET}")
    print("=" * 60)

    workspace_id: str | None = None
    success = False
    try:
        ensure_user(SMOKE_EMAIL, SMOKE_PASSWORD)
        owner_token = get_jwt(SMOKE_EMAIL, SMOKE_PASSWORD)
        with api(owner_token) as client:
            step_health(client)
            report.ok("health", "API is up")
            workspace_id = step_create_workspace(client)
            report.ok("workspace", "Workspace created", workspace_id=workspace_id)
            step_verify_owner_membership(workspace_id, owner_token)
            report.ok("membership", "Owner membership visible", workspace_id=workspace_id)
            source_id, job_id = step_upload(client, workspace_id)
            report.ok("upload", "Source uploaded", workspace_id=workspace_id, source_id=source_id, job_id=job_id)
            step_verify_source_contract(workspace_id, source_id, job_id)
            report.ok("source_contract", "Source and job contracts valid", workspace_id=workspace_id, source_id=source_id, job_id=job_id)
            step_poll_ingest(client, workspace_id, source_id)
            report.ok("ingest", "Ingest succeeded", workspace_id=workspace_id, source_id=source_id)
            step_verify_chunks(workspace_id, source_id)
            report.ok("chunks", "Chunks created", workspace_id=workspace_id, source_id=source_id)
            step_rls_outsider(workspace_id)
            report.ok("rls", "Outsider cannot see tenant rows", workspace_id=workspace_id)
            if FULL:
                chunk_id = step_poll_review_queue(client, workspace_id, source_id)
                report.ok("review_queue", "Review queue ready", workspace_id=workspace_id, source_id=source_id, chunk_id=chunk_id)
                fact_id = step_approve_and_publish(client, workspace_id, chunk_id)
                report.ok("approve_publish", "Fact approved and published", workspace_id=workspace_id, chunk_id=chunk_id, fact_id=fact_id)
                step_verify_published(workspace_id, fact_id)
                report.ok("published_view", "Fact visible in published_facts", workspace_id=workspace_id, fact_id=fact_id)
        success = True
    finally:
        if os.getenv("SMOKE_CLEANUP", "0") == "1":
            cleanup_smoke_data(workspace_id)
        if REPORT_JSON:
            if not success and report.data["status"] == "running":
                report.fail("fatal", "Smoke run did not complete", workspace_id=workspace_id)
            report.write(REPORT_JSON)

    print("=" * 60)
    print(f"{GREEN}SMOKE TEST PASSED{RESET}")
    print("=" * 60)


if __name__ == "__main__":
    main()
