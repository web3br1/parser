# TASK-013 - Docker Local Runtime

Status: done

## Objective

Provide a reproducible local pilot runtime while keeping smoke scripts focused
on validation instead of process lifecycle.

## Scope

- Add Dockerfiles for Python services and the Next.js web console.
- Add `compose.yaml` with Redis, API, ingest worker, classification worker,
  extraction worker and web.
- Add `.env.docker.example` without real secrets.
- Document startup, validation and troubleshooting in
  `docs/operations/DOCKER_LOCAL_RUNTIME.md`.
- Keep Docker positioned as local runtime only, not a deployment contract.

## Constraints

- `.env` remains untracked.
- Compose must pass Supabase, Redis and Ollama settings through environment
  variables.
- Smoke scripts must validate the running stack and must not start, stop or
  inspect local processes.

## Verification

```powershell
docker compose config --quiet
docker compose build
docker compose up -d redis api
Invoke-RestMethod http://localhost:8000/health
docker compose down
uv run --cache-dir .uv-cache pytest tests\smoke\test_task010_smoke_scripts.py -q
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Implemented in commit `acc31aa`.
