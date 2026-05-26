# Smoke Runbook - Supabase real

Runbook operacional para validar um ambiente Supabase real do Context Compiler.
Este projeto compila contexto validado e exporta `context_bundle.v1`; o chatbot
final vive em outro projeto.

Escopo canonico:

- migrations `000` a `047` aplicadas no projeto Supabase dev
- bucket privado `context-builder-private`
- API, Redis e workers iniciados por Docker ou outro runtime externo ao
  orquestrador de smoke
- smoke minimo primeiro
- smoke completo apenas depois do minimo passar
- scripts oficiais em `scripts/smoke/*.py`

Nao coloque secrets neste documento, em logs ou em outputs compartilhados.

## Pre-requisitos

- Supabase CLI autenticado.
- Projeto Supabase dev linkado.
- Redis acessivel via `REDIS_URL` (Docker, local, WSL, Memurai ou servico
  gerenciado).
- `uv` instalado e disponivel no PATH.
- Supabase CLI acessivel via `npx supabase`.
- Python 3.12 com dependencias do projeto instaladas.
- `.env` local criado a partir de `.env.example`.
- Bucket `context-builder-private` criado como privado.

Variaveis obrigatorias no `.env` local:

```dotenv
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
WORKSPACE_STORAGE_BUCKET=context-builder-private
REDIS_URL=redis://localhost:6379/0
API_BASE_URL=http://localhost:8000
APP_ENV=development
LOG_LEVEL=INFO

MODEL_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_TIMEOUT_SECONDS=300
CLASSIFICATION_MODEL=gemma4:31b
EXTRACTION_MODEL=hf.co/hesamation/Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:Q4_K_M
EXTRACTION_MODEL_FALLBACK=kwangsuklee/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:latest

SMOKE_USER_EMAIL=owner@example.test
SMOKE_USER_PASSWORD=
SMOKE_OUTSIDER_EMAIL=outsider@example.test
SMOKE_OUTSIDER_PASSWORD=
```

Use valores reais apenas no `.env`, nunca em `.env.example`.

Para o piloto local, use `MODEL_PROVIDER=ollama`. `OPENAI_API_KEY` e
`ANTHROPIC_API_KEY` ficam vazios a menos que uma rodada de fallback externo seja
explicitamente necessaria.

## 1. Aplicar migrations

Na raiz do projeto:

```bash
npx supabase login
npx supabase link --project-ref <project-ref>
npx supabase db push
```

Migrations esperadas:

```text
000_extensions.sql
...
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
046_source_pack_import_runs.sql
047_context_build_runs.sql
```

Validacao rapida no SQL Editor:

```sql
select count(*)
from supabase_migrations.schema_migrations;

select to_regclass('public.sources');
select to_regclass('public.processing_jobs');
select to_regprocedure('public.complete_ingest_job(uuid,uuid,uuid,jsonb,jsonb)');
select to_regprocedure('public.complete_classification_job(uuid,uuid,uuid,uuid,jsonb,text,jsonb,jsonb,text)');
select to_regprocedure('public.complete_extraction_job(uuid,uuid,uuid,uuid,text,text,jsonb,jsonb,jsonb,jsonb)');
```

Se alguma migration falhar, pare o smoke, registre a migration e o erro, corrija em ambiente dev e reaplique. Nao desabilite RLS para fazer o smoke passar.

## 2. Validar bucket

No Supabase Dashboard, confirme:

- bucket: `context-builder-private`
- public: `false`
- paths esperados: `workspaces/{workspace_id}/sources/{source_id}/original{suffix}`

Validacao via SQL:

```sql
select id, public
from storage.buckets
where id = 'context-builder-private';
```

## 3. Subir runtime local

Use Docker como runtime reproduzivel preferencial:

```bash
docker compose up --build
```

Tambem e valido iniciar Redis, API e workers por outro supervisor externo. O
script `scripts/smoke/run_real_smoke.py` valida a stack ja iniciada; ele nao
inicia, para, nem inspeciona processos locais. Para detalhes, veja
`docs/operations/DOCKER_LOCAL_RUNTIME.md` e `docs/operations/LOCAL_RUNTIME.md`.

## 4. Validar runtime local

Health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Resultado esperado:

```json
{"status":"ok"}
```

Servicos esperados:

| Servico | Porta | Funcao |
| --- | --- | --- |
| redis externo/Docker/local | conforme `REDIS_URL` | broker Celery |
| api | 8000 | FastAPI |
| worker-ingest | - | parse, quality gate e chunks |
| worker-classification | - | classificacao de chunks |
| worker-extraction | - | extracao estruturada |

Use os logs do processo externo escolhido para API e workers.

## 5. Rodar contratos estaticos

Na raiz do projeto:

```bash
python scripts/smoke/check_supabase_contracts.py
```

O script deve validar, no minimo:

- migrations `000-047`
- tabelas principais
- RPCs de ingest, classification e extraction
- bucket `context-builder-private`
- RLS habilitado
- indice `uq_sources_workspace_file_hash_active`

## 6. Rodar smoke minimo

Rode primeiro pelo orquestrador canonico:

```bash
uv run --cache-dir .uv-cache python scripts/smoke/run_real_smoke.py --target local --json-report .run/smoke-local-minimal.json
```

`supabase_smoke.py` continua existindo como subfase/debug, mas nao e o comando
primario de readiness.

Se precisar diagnosticar a subfase diretamente:

```powershell
$env:SMOKE_REPORT_JSON=".run\smoke-minimal.json"
python scripts/smoke/supabase_smoke.py
```

Escopo minimo esperado:

```text
owner auth ok
outsider auth ok
workspace criado
owner vira membro
upload retorna source/job
arquivo cai em storage privado
processing_job de ingest existe
worker ingest cria chunks sem status failed/rejected
outsider nao acessa workspace do owner
service role nao aparece em stdout/stderr
```

O smoke minimo e o gate para qualquer validacao mais cara com modelo.

## 7. Rodar smoke completo

Depois do minimo passar, rode o smoke completo pelo orquestrador canonico:

```bash
uv run --cache-dir .uv-cache python scripts/smoke/run_real_smoke.py --target local --full --json-report .run/smoke-local-full.json
```

Para provar importacao pelo runtime consumidor, defina o comando real de import
antes do smoke completo:

```powershell
$env:CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND="python -m runtime.importer --bundle {bundle}"
uv run --cache-dir .uv-cache python scripts\smoke\run_real_smoke.py --target local --full --json-report .run\smoke-local-full.json
```

Substitua o exemplo pelo comando do runtime consumidor. O placeholder `{bundle}`
deve permanecer no comando para o orquestrador injetar o caminho do
`context_bundle.v1` gerado. Nao coloque secrets no comando, em variaveis
registradas, logs ou relatorios.

Se precisar diagnosticar uma execucao especifica:

```bash
python scripts/smoke/diagnose_source.py --workspace-id <workspace-id> --source-id <source-id>
```

Escopo adicional esperado:

```text
classification enfileirada/processada
extraction enfileirada/processada
review queue retorna facts
approve fact funciona
publish fact funciona
published_facts contem o fato publicado
```

## Troubleshooting

### Runtime local nao responde

Confirme que `.env` existe, nao contem valores vazios para Supabase, que
`REDIS_URL` aponta para um Redis acessivel e que API/workers foram iniciados
pelo Docker ou processo externo escolhido. O orquestrador de smoke nao inicia
nem para servicos locais.

### Pipeline fica parado

Consulte os logs do processo externo que iniciou `worker-ingest`,
`worker-classification` e `worker-extraction`.

SQL util:

```sql
select id, job_type, status, created_at, metadata
from processing_jobs
where status in ('queued', 'running', 'retrying')
order by created_at desc
limit 20;
```

Diagnostico HTTP equivalente, sem porta Postgres direta:

```bash
python scripts/smoke/diagnose_source.py --workspace-id <workspace-id> --source-id <source-id>
```

### Limpar workspaces de smoke

Por padrao o cleanup faz soft-delete dos workspaces com slug `smoke-*`:

```bash
python scripts/smoke/cleanup_smoke.py
```

### Remover storage de deletes LGPD

Depois de uma confirmacao de delete LGPD que retorna `pending_storage_delete`,
rode primeiro o dry-run:

```bash
python scripts/ops/storage_gc.py --mode privacy-deleted --older-than-hours 0
```

Para apagar os objetos de sources ja soft-deletadas:

```bash
python scripts/ops/storage_gc.py --mode privacy-deleted --older-than-hours 0 --apply
```

Use `--mode orphans` apenas para objetos antigos sem referencia em `sources`.

### RLS bloqueia API ou workers

- API e workers devem usar `SUPABASE_SERVICE_ROLE_KEY`.
- Cliente anon/JWT deve ser usado para validar isolamento entre owner e outsider.
- Nunca troque policies por `using (true)` para passar smoke.

### Storage falha no upload

- Confirme que o bucket `context-builder-private` existe.
- Confirme que ele e privado.
- Confirme que `WORKSPACE_STORAGE_BUCKET=context-builder-private`.
- Confirme que o path segue `workspaces/{workspace_id}/sources/{source_id}/original{suffix}`.

## Checklist final

- [ ] Migrations `000-047` aplicadas sem erro.
- [ ] Migrations `046_source_pack_import_runs.sql` e `047_context_build_runs.sql` aplicadas sem erro.
- [ ] Bucket `context-builder-private` existe e e privado.
- [ ] Redis esta acessivel via `REDIS_URL`.
- [ ] API, Redis e workers foram iniciados por Docker ou runtime externo ao orquestrador de smoke.
- [ ] `GET /health` retorna 200.
- [ ] `scripts/smoke/check_supabase_contracts.py` passa.
- [ ] `scripts/smoke/run_real_smoke.py --target local` passa no modo minimo.
- [ ] `scripts/smoke/run_real_smoke.py --target local --full` passa depois do minimo.
- [ ] `CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND` aponta para o runtime consumidor com placeholder `{bundle}`.
- [ ] Runtime consumidor importa `context_bundle.v1` sem edicao manual.
- [ ] `scripts/smoke/supabase_smoke.py` foi usado apenas como subfase/debug quando necessario.
- [ ] Relatorio JSON foi gerado quando a rodada precisa ser auditavel.
- [ ] `scripts/smoke/diagnose_source.py` consegue explicar a rodada por `source_id`.
- [ ] RLS bloqueia outsider.
- [ ] Service role nao aparece em logs.
- [ ] Resultados foram registrados sem secrets.
