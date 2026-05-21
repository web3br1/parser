# Supabase Real Environment

Documento operacional da TASK-010 para provisionar e validar um ambiente Supabase real de desenvolvimento.

## Principios

- Use um projeto Supabase dev separado de producao.
- Aplique migrations `000` a `045`, em ordem.
- Crie o bucket privado `context-builder-private`.
- Execute a stack local com `scripts/dev/start_local_stack.ps1`.
- Rode o smoke real pelo orquestrador; ele executa minimo antes de `--full`.
- Use os scripts oficiais em `scripts/smoke/*.py`.
- Nunca registre secrets em docs, terminal compartilhado, screenshots ou logs.

## Ambiente alvo

```text
Projeto: context-builder-dev
Tipo: Supabase managed Postgres
Uso: desenvolvimento real e smoke end-to-end
Bucket: context-builder-private
```

Registre localmente o `project-ref` usado, mas nao registre keys neste arquivo.

## Setup Supabase

Na raiz do projeto:

```bash
npx supabase login
npx supabase link --project-ref <project-ref>
npx supabase db push
```

Migrations esperadas:

```text
000_extensions.sql
001_enums.sql
002_workspaces.sql
003_security_helpers.sql
004_sources.sql
005_quality_reports.sql
006_chunks.sql
007_evidence_spans.sql
008_schema_registry.sql
009_extracted_facts.sql
010_business_rules.sql
011_unknown_queue.sql
012_contradictions.sql
013_validation_events.sql
014_published_views.sql
015_query_audit.sql
016_jobs.sql
017_token_usage.sql
018_audit_logs.sql
019_connectors_mcp.sql
020_rls.sql
021_seed_mvp_schemas.sql
022_publish_functions.sql
023_supersede_rollback_functions.sql
024_storage_policies.sql
025_workspace_schema_policies.sql
026_source_authority.sql
027_contradiction_helpers.sql
028_review_functions.sql
029_integrity_constraints.sql
030_ingest_rpc.sql
031_classification_rpc.sql
032_extraction_rpc.sql
033_security_definer_grants.sql
034_cast_validation_action_in_approval_functions.sql
035_unknown_queue_metadata.sql
036_lock_down_security_definer_rpc.sql
037_job_claim_and_source_state.sql
038_privacy_requests.sql
039_source_state_on_publish.sql
040_lock_down_storage_read_policy.sql
041_lock_down_client_writes.sql
042_storage_file_size_100mb.sql
043_lock_down_storage_client_writes.sql
044_restrict_publish_to_managers.sql
045_backfill_source_state.sql
```

## Storage

Crie ou confirme o bucket:

```text
Nome: context-builder-private
Public: false
```

Path canonico para originais:

```text
workspaces/{workspace_id}/sources/{source_id}/original{suffix}
```

Validacao SQL:

```sql
select id, public
from storage.buckets
where id = 'context-builder-private';
```

## Auth

Usuarios de smoke:

```text
owner@example.test
outsider@example.test
```

O owner deve criar workspace e dados. O outsider deve autenticar, mas nao deve enxergar workspace, sources, chunks, facts ou filas do owner.

## RLS

Validar RLS com cliente anon/JWT. Service role pode confirmar estado administrativo, mas nao prova isolamento de tenant.

Tabelas obrigatorias:

```sql
select relname, relrowsecurity
from pg_class
where relname in (
  'workspaces',
  'workspace_members',
  'sources',
  'chunks',
  'extracted_facts',
  'business_rules',
  'unknown_facts_queue',
  'fact_type_schemas'
)
order by relname;
```

Todas devem retornar `relrowsecurity = true`, quando forem tabelas com RLS.

## Validacao preferencial

Na raiz do projeto, valide o fluxo local completo com:

```bash
uv run python scripts/smoke/run_real_smoke.py --target local --full --json-report .run/smoke-local-full.json
```

Esse comando orquestra readiness, contratos, preflight da stack local, health da
API, smoke minimo e smoke completo. Ele nao inicia Redis, API ou workers por
padrao.

Se quiser que o orquestrador tente iniciar Redis e a stack local antes do
health/smoke, use `--start-stack` de forma explicita:

```bash
uv run python scripts/smoke/run_real_smoke.py --target local --full --start-stack --json-report .run/smoke-local-full.json
```

Para validar uma API publicada contra o mesmo ambiente Supabase:

```bash
uv run python scripts/smoke/run_real_smoke.py --target cloud --full --api-base-url <url> --json-report .run/smoke-cloud-full.json
```

## Contratos estaticos e troubleshooting

Readiness local, antes do gate remoto:

```bash
uv run python scripts/smoke/real_readiness.py
uv run python scripts/smoke/real_readiness.py --json
```

Este passo valida apenas pre-condicoes locais e nao chama Supabase. Ele nao
substitui `check_supabase_contracts.py`, que continua validando contratos
remotos de schema, bucket e RPCs. Para SQL, ele exige `psql` no `PATH` ou
`PSQL_BIN` junto de uma DB URL, ou `SUPABASE_ACCESS_TOKEN` com project ref.

Se `psql` existir fora do `PATH`, configure o caminho explicitamente:

```powershell
$env:PSQL_BIN="C:\Program Files\PostgreSQL\16\bin\psql.exe"
uv run python scripts/smoke/real_readiness.py --psql-bin "$env:PSQL_BIN"
uv run python scripts/smoke/check_supabase_contracts.py
```

Na raiz:

```bash
uv run python scripts/smoke/check_supabase_contracts.py
```

Este passo deve rodar antes do smoke funcional para detectar schema incompleto, bucket ausente ou RPCs faltantes.

## Stack local

Preflight:

```powershell
.\scripts\dev\check_local_stack.ps1
```

Suba a stack local, ou use `--start-stack` no orquestrador quando quiser que
ele tente iniciar estes servicos:

```powershell
.\scripts\dev\start_local_stack.ps1
```

O comando acima forca `CELERY_TASK_ALWAYS_EAGER=0` para validar Redis/Celery e
workers separados. Use `.\scripts\dev\start_local_stack.ps1 -Eager` apenas para
debug local sem fila real.

API:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Logs:

```powershell
Get-Content .run\logs\api.err.log -Tail 100
Get-Content .run\logs\worker-ingest.err.log -Tail 100
Get-Content .run\logs\worker-classification.err.log -Tail 100
Get-Content .run\logs\worker-extraction.err.log -Tail 100
```

## Ordem de validacao

1. `npx supabase db push`
2. confirmar bucket `context-builder-private`
3. garantir stack local de pe, ou optar por `--start-stack`
4. `uv run python scripts/smoke/run_real_smoke.py --target local --full --json-report .run/smoke-local-full.json`
5. `uv run python scripts/smoke/run_real_smoke.py --target cloud --full --api-base-url <url> --json-report .run/smoke-cloud-full.json` quando validar deploy
6. `uv run python scripts/smoke/diagnose_source.py --workspace-id <workspace-id> --source-id <source-id>` quando precisar explicar uma rodada
7. `uv run python scripts/ops/storage_gc.py --mode privacy-deleted` para dry-run de objetos pendentes de delete LGPD

Para troubleshooting, rode os scripts individuais na mesma ordem usada pelo
orquestrador: readiness, contratos, preflight local, health, smoke minimo e
smoke completo.

## Registro de execucao

Use este bloco no relatorio da execucao, sem secrets:

```text
Data/hora:
Project ref:
Migrations: 000-045
Bucket privado: context-builder-private
Readiness local:
Contratos estaticos:
Smoke minimo:
Smoke full:
Relatorio JSON:
Diagnostico source:
Observacoes:
```

## Rollback dev

Somente em projeto dev:

```bash
supabase db reset --linked
```

Se a falha estiver restrita ao storage, remova e recrie o bucket privado `context-builder-private` e reaplique/valide as policies de storage.

Nunca rode reset contra producao.
