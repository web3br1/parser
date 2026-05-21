# Real Smoke Orchestrator Design

## Goal

Replace the manual chain of readiness, contracts, stack checks, health checks, and smoke commands with one orchestrator that can run the full real-test flow locally first and later against a cloud deployment.

## Approach

Create `scripts/smoke/run_real_smoke.py` as the single entrypoint. It coordinates existing scripts rather than duplicating their business logic:

```text
readiness -> contracts -> local stack/preflight -> health -> smoke-min -> smoke-full -> report
```

The orchestrator must keep each phase explicit, record stdout/stderr snippets, return a single exit code, and write a JSON report when requested.

## Targets

### Local

`--target local` validates the developer machine and local FastAPI/Celery workers against the real Supabase dev project.

Default behavior:

- Run `real_readiness.py`.
- Run `check_supabase_contracts.py`.
- Run `check_local_stack.ps1`.
- Check API health at `API_BASE_URL` or `http://localhost:8000`.
- Run `supabase_smoke.py`.
- Run `supabase_smoke.py --full` when `--full` is set.

Optional behavior:

- `--start-stack` runs `setup_redis_windows.ps1` and `start_local_stack.ps1` before health/smoke.
- `--skip-contracts`, `--skip-readiness`, and `--skip-stack-check` are allowed for focused reruns.

### Cloud

`--target cloud` validates a deployed API and the same Supabase project without starting local services.

Behavior:

- Run `real_readiness.py`.
- Run `check_supabase_contracts.py`.
- Skip Redis/start-stack/local process checks.
- Require an API base URL through `--api-base-url` or `API_BASE_URL`.
- Run health, smoke minimum, and optionally smoke full.

## CLI

```bash
uv run python scripts/smoke/run_real_smoke.py --target local
uv run python scripts/smoke/run_real_smoke.py --target local --full --json-report .run/smoke-local-full.json
uv run python scripts/smoke/run_real_smoke.py --target local --full --start-stack
uv run python scripts/smoke/run_real_smoke.py --target cloud --full --api-base-url https://api.example.com
```

Useful control flags:

- `--full`: run smoke full after smoke minimum.
- `--json-report PATH`: write one orchestration report and pass a smoke report path to `supabase_smoke.py`.
- `--api-base-url URL`: override `API_BASE_URL` for health and smoke subprocesses.
- `--start-stack`: local only, start Redis and local stack.
- `--no-start`: default-safe alias that refuses to start local services.
- `--continue-on-failure`: collect later diagnostics where safe, but final status remains failed.
- `--dry-run`: print phases and commands without executing them.

## Reporting

The report shape is:

```json
{
  "target": "local",
  "mode": "full",
  "status": "passed",
  "started_at": "...",
  "finished_at": "...",
  "phases": [
    {
      "name": "readiness",
      "status": "passed",
      "command": ["python", "scripts/smoke/real_readiness.py"],
      "returncode": 0,
      "duration_seconds": 1.2
    }
  ]
}
```

Outputs must be sanitized by default. The report can include short stdout/stderr tails, but must not include Supabase keys, model keys, or database URLs.

## Failure Behavior

- Stop at the first failing phase unless `--continue-on-failure` is passed.
- Print the failing phase and next suggested command.
- Treat local stack process-inspection warnings as non-blocking when the existing preflight returns success.
- If `--target cloud` is used with `--start-stack`, fail before executing phases.

## Tests

Unit tests should monkeypatch command execution and HTTP health checks. They must not start Redis, run PowerShell services, call Supabase, or hit a real API.

Required coverage:

- Local full builds the phase order including readiness, contracts, stack check, health, min smoke, full smoke.
- Cloud full skips local stack phases and uses `--api-base-url`.
- Failure stops subsequent phases by default.
- `--continue-on-failure` records later safe phases.
- `--dry-run` records planned commands without execution.
- Report output is written and does not leak sentinel secrets from environment or command output.
