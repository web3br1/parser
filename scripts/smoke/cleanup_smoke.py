from __future__ import annotations

import argparse
import os
from pathlib import Path

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
            "Prefer": "return=representation",
        },
        timeout=30.0,
    )


def mark_smoke_workspaces_deleted(rest: httpx.Client, *, slug_prefix: str) -> int:
    response = rest.patch(
        "/workspaces",
        params={"slug": f"like.{slug_prefix}*", "status": "neq.deleted", "select": "id"},
        json={"status": "deleted"},
    )
    if response.status_code not in (200, 204):
        raise RuntimeError(f"cleanup failed: {response.status_code} {response.text}")
    if response.status_code == 204 or not response.text:
        return 0
    data = response.json()
    return len(data) if isinstance(data, list) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Soft-delete smoke test workspaces.")
    parser.add_argument("--slug-prefix", default="smoke-")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    with supabase_rest() as rest:
        count = mark_smoke_workspaces_deleted(rest, slug_prefix=args.slug_prefix)
    print(f"marked_deleted={count}")


if __name__ == "__main__":
    main()
