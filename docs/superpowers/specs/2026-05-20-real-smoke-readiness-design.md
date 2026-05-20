# Real Smoke Readiness Design

## Goal

Add a local readiness gate that tells us whether the project is prepared to run the real Supabase smoke flow before we spend time starting workers or touching the remote environment.

## Problem

The real test path is documented, but it is still easy to start the smoke flow with missing `.env` values, stale migration expectations, absent local scripts, wrong bucket configuration, or no JSON report path. The existing `check_supabase_contracts.py` validates the remote Supabase schema and policies; this new gate validates the local preconditions around that step without making network calls or printing secrets.

## Scope

- Create `scripts/smoke/real_readiness.py`.
- Add tests for deterministic local checks.
- Update operational docs to put readiness before contract and smoke commands.
- Do not call Supabase, Redis, API, npm, or PowerShell services from the readiness script.
- Do not print secret values.
- Preserve existing smoke behavior.

## Readiness Checks

The script must inspect:

- `.env` exists by default, with `--env-file` override.
- Required variables are present: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.
- SQL access is actionable through either `psql` on `PATH` plus `SUPABASE_DB_URL` / `DATABASE_URL`, `psql` on `PATH` plus `SUPABASE_POOLER_DB_URL` / `SUPABASE_IPV4_DB_URL` / `DATABASE_POOLER_URL`, or `SUPABASE_ACCESS_TOKEN` plus a project ref from `SUPABASE_PROJECT_REF` or `SUPABASE_URL`.
- `WORKSPACE_STORAGE_BUCKET` resolves to `context-builder-private`.
- `REDIS_URL` is present unless `--allow-missing-redis` is passed.
- `SMOKE_REPORT_JSON` is present or `--report-json` is provided.
- `supabase/config.toml` exists.
- `supabase/migrations/*.sql` contains a contiguous sequence from `000` through the highest migration currently in the repo.
- Required real-test scripts exist: contract checker, smoke runner, local stack checker, local stack starter, source diagnostic, smoke cleanup.

## CLI Contract

```bash
python scripts/smoke/real_readiness.py
python scripts/smoke/real_readiness.py --json
python scripts/smoke/real_readiness.py --env-file .env.real --report-json .run/smoke-full.json
python scripts/smoke/real_readiness.py --allow-missing-redis
```

Exit code:

- `0` when all hard checks pass.
- `1` when any hard check fails.

Output:

- Human mode prints `OK`, `WARN`, and `FAIL` lines with variable names only.
- JSON mode prints a single JSON object with `status`, `checks`, and sanitized `summary`.

## Confidence Target

After this slice, confidence for “ready to attempt real smoke” should move from medium-low to medium-high locally. It does not prove remote Supabase state; `check_supabase_contracts.py` remains the remote contract gate.
