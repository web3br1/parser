# Docker Local Runtime

This runbook starts the local pilot runtime without making smoke scripts own
process lifecycle. Docker owns Redis and the long-running API/workers for local
development only; it is not a deployment contract.

## Services

- `redis`: Celery broker/result backend.
- `api`: FastAPI on `http://localhost:8000`.
- `worker-ingest`: consumes the `ingest` queue.
- `worker-classification`: consumes the `classification` queue.
- `worker-extraction`: consumes the `extraction` queue.
- `web`: Next.js on `http://localhost:3000`, with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.

The browser reaches the API through `localhost:8000`. Containers reach host-local
Ollama through `host.docker.internal:11434`.

## First-Time Setup

1. Install Docker Desktop and start it once.
2. Copy `.env.docker.example` to `.env`.
3. Fill these real Supabase values in `.env`:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `WORKSPACE_STORAGE_BUCKET=context-builder-private`
4. Keep Docker Redis values:
   - `REDIS_URL=redis://redis:6379/0`
   - `API_BASE_URL=http://localhost:8000`
5. If using local Ollama, keep:
   - `MODEL_PROVIDER=ollama`
   - `OLLAMA_BASE_URL=http://host.docker.internal:11434`

Do not commit `.env`.

## Start

```bash
docker compose up --build
```

Open:

- API health: `http://localhost:8000/health`
- Web console: `http://localhost:3000`

Stop:

```bash
docker compose down
```

Reset Redis only:

```bash
docker compose down -v
```

## Validation

With the compose stack running:

```bash
uv run --cache-dir .uv-cache python scripts/smoke/run_real_smoke.py --target local --full --json-report .run/smoke-local-docker-full.json
```

For front-only route checks:

```bash
corepack pnpm --filter @context-builder/web build
node scripts/smoke/frontend_console_smoke.mjs --fetch-only
```

## Troubleshooting

- `docker` command missing: restart the terminal after Docker Desktop install.
- Docker daemon unavailable: open Docker Desktop and wait until it is running.
- API fails at startup: check `.env` has real Supabase URL and service role key.
- Upload accepted but no progress: check `worker-ingest`, `worker-classification`, and `worker-extraction` logs.
- Ollama connection fails inside containers: confirm Ollama is running on Windows and listening on `localhost:11434`.
- Redis state is stale: run `docker compose down -v` and then `docker compose up --build`.
