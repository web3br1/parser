# Pilot Local Runbook

Runbook para rodar o piloto local decidido em `DECISOES_PENDENTES.md`.

## Estado atual

```text
Inferencia: Ollama local
API: FastAPI local
Workers: Celery
Banco/Auth/Storage: Supabase dev real
Broker decidido para piloto: Redis local
Fallback permitido apenas para smoke local: filesystem broker
```

## Preflight obrigatorio

Se Redis nao estiver rodando no Windows, iniciar o Redis portatil do workspace:

```powershell
.\scripts\dev\setup_redis_windows.ps1
```

O script baixa o port Windows `tporadowski/redis` em `.run\redis` e inicia o
processo sem instalar servico no sistema.

```powershell
.\scripts\dev\check_local_stack.ps1
```

O piloto so esta no modo decidido quando Redis responde em:

```text
redis://localhost:6379/0
```

Se `redis tcp` falhar, o ambiente ainda nao esta pronto para piloto real. O smoke pode
ser repetido com `-FilesystemBroker`, mas isso valida apenas desenvolvimento local.

## Variaveis principais

```dotenv
MODEL_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
CLASSIFICATION_MODEL=gemma4:31b
EXTRACTION_MODEL=hf.co/hesamation/Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:Q4_K_M
EXTRACTION_MODEL_FALLBACK=kwangsuklee/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:latest
REDIS_URL=redis://localhost:6379/0
```

## Start

Com Redis real:

```powershell
.\scripts\dev\start_local_stack.ps1 -Port 8000
```

Fallback de desenvolvimento, sem Redis:

```powershell
.\scripts\dev\start_local_stack.ps1 -FilesystemBroker -Port 8000
```

Nao use `-FilesystemBroker` para o piloto validado.

Health:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

## Smoke gate

O gate obrigatorio antes do piloto e:

```powershell
python scripts\smoke\supabase_smoke.py `
  --full `
  --no-color `
  --poll-timeout 300 `
  --json-report .run\smoke-full-pilot.json
```

Resultado esperado:

```text
SMOKE TEST PASSED
```

## Diagnostico de falha

Primeiro comando para qualquer falha por source:

```powershell
python scripts\smoke\diagnose_source.py --workspace-id <workspace-id> --source-id <source-id>
```

Campos que precisam aparecer em logs de erro:

```text
request_id
job_id
source_id
workspace_id
```

## Metricas do piloto

Gerar relatorio por workspace:

```powershell
python scripts\pilot\pilot_metrics.py --workspace-id <workspace-id>
```

O comando sai com codigo diferente de zero quando qualquer gate mecanico falha.

Com periodo:

```powershell
python scripts\pilot\pilot_metrics.py `
  --workspace-id <workspace-id> `
  --since 2026-05-01T00:00:00Z `
  --until 2026-05-12T23:59:59Z `
  --output .run\pilot-metrics.json
```

Gates decididos:

```text
approval_rate >= 0.70
edit_rate <= 0.30
unknown_rate <= 0.25
critical_error = 0
RLS violations = 0
```

`RLS violations` e medido pelo smoke full, no passo outsider/RLS.

## Readiness gates

Antes de liberar o piloto/release, todos estes gates precisam estar verdes:

```text
CI: ruff, pytest -q, pip-audit, pnpm audit, frontend typecheck/build, secret scan
Smoke: tests/smoke incluido em pytest padrao
Supabase smoke full: passed, incluindo outsider/RLS
Pilot metrics: approval_rate >= 0.70, edit_rate <= 0.30, unknown_rate <= 0.25, critical_error = 0
RLS violations: 0
Semantic metrics: precision >= 0.85, recall >= 0.75, critical_false_positives = 0, negative_test_false_positives = 0
```

Sem arquivo de predictions ou `--pilot-report` com `semantic_predictions`, o
semantic gate fica `not_evaluated`. Esse estado e esperado para smoke sem
predictions, mas nao libera piloto/release.

O secret scan deve bloquear valores reais vazados, nao simples mencoes a nomes de
variaveis como `SUPABASE_SERVICE_ROLE_KEY` ou `OPENAI_API_KEY`.

## Supabase contract smoke

O contrato real de Supabase pode executar SQL por dois caminhos:

```powershell
python scripts\smoke\check_supabase_contracts.py
```

Opcoes de credencial:

```text
1. psql no PATH + SUPABASE_DB_URL ou DATABASE_URL
2. psql no PATH + SUPABASE_POOLER_DB_URL para ambientes onde o host direto IPv6 nao resolve
3. SUPABASE_ACCESS_TOKEN + SUPABASE_PROJECT_REF para fallback via Management API
```

Se o host `db.<project-ref>.supabase.co` falhar por DNS/IPv6 na maquina local,
use a connection string do pooler/IPv4 em `SUPABASE_POOLER_DB_URL` ou rode com
`SUPABASE_ACCESS_TOKEN`.

## Gate semantico

Comparar predicoes publicadas/exportadas contra o manifesto semi-real:

```powershell
python scripts\pilot\semantic_metrics.py `
  --workspace-id <workspace-id> `
  --manifest examples\pilot_semireal\manifest.json `
  --predictions .run\semantic-predictions.json `
  --output .run\semantic-report.json
```

Gates minimos:

```text
precision >= 0.85
recall >= 0.75
critical_false_positives = 0
negative_test_false_positives = 0
```

Rodar `semantic_metrics.py` apenas com o manifesto deve produzir
`status=not_evaluated`. Nao registrar isso como gate semantico aprovado.

Antes de dados reais, tambem rode localmente:

```powershell
uv run pytest -q
uv run ruff check .
corepack pnpm --filter @context-builder/web typecheck
corepack pnpm --filter @context-builder/web build
python scripts\smoke\check_supabase_contracts.py
```

## Cleanup

Workspaces de smoke:

```powershell
python scripts\smoke\cleanup_smoke.py
```

Parar stack:

```powershell
.\scripts\dev\stop_local_stack.ps1
```
