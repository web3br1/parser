# TASK-015 - Real Smoke Readiness Cleanup

Status: done

## Objective

Decouple real smoke/readiness validation from local service startup scripts so
production gates test behavior, not developer machine process control.

## Scope

- Remove `--start-stack`, `--no-start`, `--skip-stack-check` and PowerShell
  dev-script coupling from `scripts/smoke/run_real_smoke.py`.
- Make smoke phases validate an already-running target.
- Update readiness checks so required scripts are smoke/ops scripts, not local
  stack lifecycle scripts.
- Update tests and runbook documentation.

## Constraints

- Smoke scripts must not start, stop or inspect local API/worker/Redis
  processes.
- Tool failures must produce safe messages and structured reports.
- Secret scan and redaction expectations remain part of readiness.

## Verification

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_real_readiness.py tests\smoke\test_real_smoke_orchestrator.py tests\smoke\test_task010_smoke_scripts.py -q
uv run --cache-dir .uv-cache ruff check scripts\smoke tests\smoke
```

Implemented in commit `e2bc738`.
