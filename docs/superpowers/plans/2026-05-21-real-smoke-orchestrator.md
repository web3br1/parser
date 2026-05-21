# Real Smoke Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one command that orchestrates local-first and cloud smoke validation.

**Architecture:** Add a Python CLI that wraps existing readiness, contract, PowerShell stack, health, and smoke scripts as named phases. Tests monkeypatch execution so the orchestration behavior is verified without network or service side effects.

**Tech Stack:** Python standard library, httpx, pytest, existing smoke/dev scripts.

---

## File Structure

- Create `scripts/smoke/run_real_smoke.py`: orchestrator CLI, phase runner, report writer, sanitization.
- Create `tests/smoke/test_real_smoke_orchestrator.py`: unit tests for phase order, target differences, failure behavior, dry-run, and report sanitization.
- Modify `tests/smoke/test_task010_smoke_scripts.py`: assert the orchestrator exists.
- Modify `docs/07-operations/SMOKE_TEST_SUPABASE.md`: document the new entrypoint.
- Modify `docs/07-operations/SUPABASE_REAL_ENVIRONMENT.md`: update validation order to use the orchestrator.

## Task 1: Orchestrator CLI

**Files:**
- Create: `scripts/smoke/run_real_smoke.py`

- [ ] Implement dataclasses `PhaseResult` and `RunReport`.
- [ ] Implement `sanitize_text(text: str, env: Mapping[str, str]) -> str`.
- [ ] Implement `build_phases(args, env)` returning ordered phase definitions.
- [ ] Implement subprocess execution with timeout, captured stdout/stderr, duration, and env overrides.
- [ ] Implement health phase with `httpx.get(f"{API_BASE_URL}/health")`.
- [ ] Implement `--dry-run` without executing subprocesses or HTTP.
- [ ] Implement JSON report writing through `--json-report`.
- [ ] Exit `0` only when all executed required phases pass.

## Task 2: Tests

**Files:**
- Create: `tests/smoke/test_real_smoke_orchestrator.py`
- Modify: `tests/smoke/test_task010_smoke_scripts.py`

- [ ] Test local full phase order.
- [ ] Test cloud full skips local stack and uses provided API URL.
- [ ] Test first failure stops later phases.
- [ ] Test `--continue-on-failure` keeps collecting safe later phases.
- [ ] Test `--dry-run` produces planned phases without execution.
- [ ] Test JSON report is written and sentinel secrets are redacted.
- [ ] Add orchestrator existence assertion to TASK-010 script inventory.

## Task 3: Docs

**Files:**
- Modify: `docs/07-operations/SMOKE_TEST_SUPABASE.md`
- Modify: `docs/07-operations/SUPABASE_REAL_ENVIRONMENT.md`

- [ ] Put `run_real_smoke.py --target local --full` as the preferred local command.
- [ ] Document `--start-stack` as explicit opt-in.
- [ ] Put `run_real_smoke.py --target cloud --full --api-base-url ...` as the cloud path.
- [ ] Keep individual scripts documented as lower-level troubleshooting commands.

## Verification

Run:

```bash
uv run --cache-dir .uv-cache pytest tests/smoke/test_real_smoke_orchestrator.py tests/smoke/test_task010_smoke_scripts.py
uv run --cache-dir .uv-cache ruff check scripts/smoke/run_real_smoke.py tests/smoke/test_real_smoke_orchestrator.py tests/smoke/test_task010_smoke_scripts.py
uv run --cache-dir .uv-cache python scripts/smoke/run_real_smoke.py --target local --full --dry-run --json-report .run/orchestrator-dry-run.json
```
