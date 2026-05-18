from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = ROOT / "scripts" / "smoke" / "supabase_smoke.py"

spec = importlib.util.spec_from_file_location("task010_supabase_smoke", SMOKE_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load smoke script: {SMOKE_SCRIPT}")

_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_module)

API_BASE = _module.API_BASE
FULL = _module.FULL
POLL_INTERVAL = _module.POLL_INTERVAL
POLL_TIMEOUT = _module.POLL_TIMEOUT
api = _module.api
ensure_user = _module.ensure_user
fail = _module.fail
get_jwt = _module.get_jwt
info = _module.info
main = _module.main
ok = _module.ok
step_approve_and_publish = _module.step_approve_and_publish
step_create_workspace = _module.step_create_workspace
step_health = _module.step_health
step_poll_ingest = _module.step_poll_ingest
step_poll_review_queue = _module.step_poll_review_queue
step_rls_outsider = _module.step_rls_outsider
step_upload = _module.step_upload
step_verify_chunks = _module.step_verify_chunks
step_verify_published = _module.step_verify_published
supabase_rest = _module.supabase_rest
sys = _module.sys
time = _module.time


if __name__ == "__main__":
    main()
