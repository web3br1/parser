# Real Smoke Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic local readiness gate before real Supabase smoke testing.

**Architecture:** Implement a standalone Python CLI in `scripts/smoke/real_readiness.py` that performs local-only checks and emits human or JSON output. Keep remote schema validation in the existing contract checker and update docs so the real-test flow becomes readiness -> contracts -> local stack -> smoke.

**Tech Stack:** Python standard library, pytest, existing smoke script conventions.

---

## File Structure

- Create `scripts/smoke/real_readiness.py`: CLI, env parsing, check model, human and JSON renderers.
- Create `tests/smoke/test_real_readiness.py`: unit tests with temporary project roots and sanitized output assertions.
- Modify `tests/smoke/test_task010_smoke_scripts.py`: include the new required script in the TASK-010 smoke script inventory.
- Modify `docs/07-operations/SMOKE_TEST_SUPABASE.md`: add readiness command before contract/smoke commands.
- Modify `docs/07-operations/SUPABASE_REAL_ENVIRONMENT.md`: update migration range to current repo and add readiness to validation order.

## Task 1: Readiness CLI

**Files:**
- Create: `scripts/smoke/real_readiness.py`

- [ ] **Step 1: Implement the local-only checker**

Create a Python script with:

```python
@dataclass
class Check:
    name: str
    status: Literal["ok", "warn", "fail"]
    message: str
    details: dict[str, object]
```

Functions:

```python
def load_env_file(path: Path) -> dict[str, str]
def merged_env(env_file: Path, environ: Mapping[str, str]) -> dict[str, str]
def collect_checks(root: Path, env_file: Path, environ: Mapping[str, str], *, report_json: str | None, allow_missing_redis: bool) -> list[Check]
def build_report(checks: Sequence[Check]) -> dict[str, object]
def main(argv: Sequence[str] | None = None) -> int
```

Hard failures: missing env file, missing required secrets by name, no SQL access path (`psql` plus database URL, or access token plus project ref), wrong bucket, missing Supabase config, migration sequence gaps, missing required scripts.

Warnings: missing Redis only when `--allow-missing-redis`, missing JSON report path.

- [ ] **Step 2: Add CLI flags**

Support:

```text
--env-file PATH
--json
--report-json PATH
--allow-missing-redis
```

Default env file is `.env` at repo root. Default report path source is `SMOKE_REPORT_JSON`.

- [ ] **Step 3: Protect secrets**

Do not include env values in human output or JSON details. Allowed details: variable names, counts, migration numbers, paths relative to root.

## Task 2: Readiness Tests

**Files:**
- Create: `tests/smoke/test_real_readiness.py`
- Modify: `tests/smoke/test_task010_smoke_scripts.py`

- [ ] **Step 1: Test passing readiness**

Build a temporary root containing `.env`, `supabase/config.toml`, migrations `000_extensions.sql` and `001_enums.sql`, and the required scripts. Assert `build_report(...).status == "passed"`.

- [ ] **Step 2: Test missing env values fail without leaking values**

Use env values like `super-secret-service-role`. Assert the failure names the variable but the secret string is absent from both human and JSON render paths.

- [ ] **Step 3: Test migration gap fails**

Use migrations `000_extensions.sql` and `002_sources.sql`. Assert a failure mentions missing migration `001`.

- [ ] **Step 4: Test TASK-010 inventory**

Add an assertion that `scripts/smoke/real_readiness.py` exists in `test_required_task010_scripts_exist`.

## Task 3: Operational Docs

**Files:**
- Modify: `docs/07-operations/SMOKE_TEST_SUPABASE.md`
- Modify: `docs/07-operations/SUPABASE_REAL_ENVIRONMENT.md`

- [ ] **Step 1: Add readiness command**

Document:

```bash
python scripts/smoke/real_readiness.py
python scripts/smoke/real_readiness.py --json
```

Place it before `check_supabase_contracts.py`.

- [ ] **Step 2: Update migration range**

Update operational references from older ranges to the current repo range `000-045`.

- [ ] **Step 3: Clarify meaning**

State that readiness is local-only and does not replace the remote contract check.

## Verification

Run:

```bash
uv run --cache-dir .uv-cache pytest tests/smoke/test_real_readiness.py tests/smoke/test_task010_smoke_scripts.py
uv run --cache-dir .uv-cache ruff check scripts/smoke/real_readiness.py tests/smoke/test_real_readiness.py tests/smoke/test_task010_smoke_scripts.py
```

Expected: all commands pass.
