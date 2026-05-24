# Local Runtime

This project does not start or stop local services from smoke scripts. Keep
runtime management outside the repository-level smoke flow.

Docker is the preferred reproducible local pilot runtime. See
`docs/operations/DOCKER_LOCAL_RUNTIME.md`.

## Required Services

- Supabase project with migrations applied.
- Redis reachable through `REDIS_URL` when running Celery workers.
- FastAPI listening at `API_BASE_URL`, usually `http://localhost:8000`.
- Celery workers for `ingest`, `classification`, and `extraction` queues.

## Minimal Manual Commands

Run each process in its own terminal with the same `.env` values loaded.

```powershell
uv run --package context-builder-api uvicorn context_builder.main:app --host 127.0.0.1 --port 8000
```

```powershell
uv run --package worker-ingest python -m celery -A worker_ingest.celery_app:app worker --loglevel=INFO --pool=solo -Q ingest
```

```powershell
uv run --package worker-classification python -m celery -A worker_classification.celery_app:app worker --loglevel=INFO --pool=solo -Q classification
```

```powershell
uv run --package worker-extraction python -m celery -A worker_extraction.celery_app:app worker --loglevel=INFO --pool=solo -Q extraction
```

## Validation

```powershell
Invoke-RestMethod http://localhost:8000/health
```

```bash
uv run --cache-dir .uv-cache python scripts/smoke/run_real_smoke.py --target local --full --json-report .run/smoke-local-full.json
```

The smoke command validates the already-running runtime. It does not start
Redis, API, workers, or inspect local processes.
