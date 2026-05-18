# TASK-010 - Supabase Real Environment

**Projeto:** Context Builder Empresarial  
**Status:** `ready`  
**Versao:** 1.0  
**Agente:** Claude Code / Codex  
**Estimativa:** 1 sessao  
**Depende de:** TASK-007  
**Bloqueia:** beta interno, testes end-to-end reais, deploy

---

## Objetivo

Provisionar e validar um ambiente Supabase real para o Context Builder, aplicando migrations, configurando Auth/Storage/RLS e executando um smoke test ponta a ponta.

Esta task nao implementa novas features. Ela transforma o schema e os workers existentes em um ambiente real verificavel.

Fluxo alvo:

```text
Supabase project
  -> migrations 000-033 aplicadas
  -> bucket privado context-builder-private criado
  -> env real configurado
  -> user Auth real
  -> workspace criado via API/RPC
  -> upload real
  -> ingest worker grava chunks
  -> classification/extraction podem ser enfileirados
```

---

## Escopo

```text
IN:
- Criar ou configurar projeto Supabase real
- Aplicar migrations
- Criar bucket privado
- Configurar .env local
- Validar Auth real
- Validar RLS
- Validar Storage
- Rodar smoke minimo com API + Redis + worker-ingest
- Rodar smoke completo com --full somente depois do minimo passar
- Documentar comandos usados

OUT:
- Deploy cloud da API
- Frontend production
- OCR
- Observability completa
- Billing/plan limits
- Query endpoint
```

---

## Pre-requisitos

Ferramentas locais:

```text
Supabase CLI
Python 3.12
uv
pnpm
Redis acessivel via REDIS_URL (local, WSL, Memurai ou gerenciado)
npx disponivel para executar Supabase CLI
```

Secrets necessarios:

```text
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
WORKSPACE_STORAGE_BUCKET=context-builder-private
REDIS_URL
OPENAI_API_KEY, apenas se classification/extraction forem testados com LLM real
```

---

## Arquivos a criar ou modificar

```text
docs/
  07-operations/
    SUPABASE_REAL_ENVIRONMENT.md
    SMOKE_TEST_SUPABASE.md

scripts/
  smoke/
    supabase_smoke.py
    check_supabase_contracts.py

.env.example
scripts/dev/check_local_stack.ps1
scripts/dev/start_local_stack.ps1
scripts/dev/stop_local_stack.ps1
```

Nao commitar `.env` real.

---

## Decisoes fechadas

### Ambiente alvo

Usar um projeto Supabase separado para desenvolvimento real:

```text
Nome sugerido: context-builder-dev
Regiao: mais proxima do usuario/time
Banco: Postgres gerenciado pelo Supabase
```

Nao usar ambiente de producao para esta task.

### Bucket canonico

```text
context-builder-private
```

Privado. Sem acesso publico.

Paths validos:

```text
workspaces/{workspace_id}/sources/{source_id}/original{suffix}
```

### Migrations

Aplicar todas em ordem:

```text
000_extensions.sql
...
033_security_definer_grants.sql
```

Se alguma migration falhar:

```text
1. Parar
2. Registrar migration + erro
3. Corrigir migration
4. Recriar banco dev ou aplicar rollback manual documentado
```

### Auth

Criar ao menos dois usuarios:

```text
owner@example.test
outsider@example.test
```

Validar:

```text
owner acessa workspace proprio
outsider nao acessa workspace do owner
```

### RLS

RLS deve ser testado pelo cliente anon/JWT, nao apenas service role.

Obrigatorio validar:

```text
workspaces
workspace_members
sources
chunks
extracted_facts
business_rules
unknown_facts_queue
fact_type_schemas
```

### Service role

Service role pode ser usada apenas por:

```text
API backend
workers
scripts locais de smoke/admin
```

Nunca expor no browser ou logs.

---

## Passo a passo

### 1. Linkar projeto Supabase

```bash
supabase login
supabase link --project-ref <project-ref>
```

Registrar o project ref em `docs/07-operations/SUPABASE_REAL_ENVIRONMENT.md`, sem secrets.

### 2. Aplicar migrations

```bash
supabase db push
```

Ou, para banco dev descartavel:

```bash
supabase db reset --linked
```

Registrar:

```text
migration inicial
migration final
timestamp
resultado
```

### 3. Criar bucket privado

Via Dashboard ou script:

```text
Bucket: context-builder-private
Public: false
```

Validar policies de `024_storage_policies.sql`.

### 4. Configurar `.env`

Criar `.env` local com:

```dotenv
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
WORKSPACE_STORAGE_BUCKET=context-builder-private
REDIS_URL=redis://localhost:6379/0
APP_ENV=development
MODEL_PROVIDER=openai
CLASSIFICATION_MODEL=gpt-4o-mini
EXTRACTION_MODEL=gpt-4o
QUERY_MODEL=gpt-4o
```

### 5. Validar infraestrutura local

```powershell
.\scripts\dev\check_local_stack.ps1
```

### 6. Subir stack local

```powershell
.\scripts\dev\start_local_stack.ps1
```

Isso inicia API, worker-ingest, worker-classification e worker-extraction como processos locais via `uv`.

### 7. Validar API

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

Parar stack:

```powershell
.\scripts\dev\stop_local_stack.ps1
```

### 8. Rodar smoke test

```bash
python scripts/smoke/check_supabase_contracts.py
python scripts/smoke/supabase_smoke.py
python scripts/smoke/supabase_smoke.py --full
```

O script deve:

```text
1. Criar/login user owner
2. Criar/login user outsider
3. Criar workspace via API
4. Confirmar owner em workspace_members
5. Fazer upload de good.txt
6. Confirmar source.status = uploaded ou processing
7. Confirmar processing_job ingest queued/running/succeeded
8. Aguardar chunks
9. Confirmar chunks criados sem status failed/rejected
10. Testar outsider sem acesso ao workspace
11. Testar storage path canonico
```

---

## Scripts obrigatorios

### `scripts/smoke/check_supabase_contracts.py`

Valida contratos estaticos contra o banco:

```text
- extensions instaladas
- migrations esperadas presentes
- tabelas principais existem
- RPCs existem
- bucket existe
- RLS habilitado nas tabelas principais
- unique index uq_sources_workspace_file_hash_active existe
```

### `scripts/smoke/supabase_smoke.py`

Executa fluxo real usando API + Supabase.

Regras:

```text
- Nao imprimir secrets
- Nao depender de dados existentes
- Prefixar dados de teste com smoke timestamp
- Limpar dados criados quando possivel
- Em falha, imprimir etapa e request_id/job_id/source_id quando houver
```

---

## Smoke test minimo primeiro

Arquivo fixture:

```text
examples/good.txt
```

Se nao existir, criar temporario em `/tmp` durante o script:

```text
Servico: Corte feminino
Preco: R$ 120
Horario: Segunda a sexta, 09:00 as 18:00
Pagamento: pix e cartao
```

Resultado esperado:

```text
workspace criado
source criada
arquivo no storage privado
processing_job ingest criado
worker ingest processa
chunks criados
RLS bloqueia outsider
```

---

## Validacoes SQL obrigatorias

Rodar via Supabase SQL editor ou script:

```sql
select to_regclass('public.sources');
select to_regclass('public.processing_jobs');
select to_regprocedure('public.complete_ingest_job(uuid,uuid,uuid,jsonb,jsonb)');
select to_regprocedure('public.complete_classification_job(uuid,uuid,uuid,uuid,jsonb,text,jsonb,jsonb,text)');
select to_regprocedure('public.complete_extraction_job(uuid,uuid,uuid,uuid,text,text,jsonb,jsonb,jsonb,jsonb)');
select indexname from pg_indexes where indexname = 'uq_sources_workspace_file_hash_active';
```

RLS:

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
);
```

---

## Rollback

Ambiente dev:

```bash
supabase db reset --linked
```

Ou apagar/recriar projeto dev se necessario.

Nunca rodar reset em producao.

Se a falha for apenas bucket:

```text
remover bucket context-builder-private
recriar bucket privado
reaplicar storage policies se necessario
```

---

## O que NAO fazer

- Nao commitar `.env`.
- Nao imprimir service role em terminal/log.
- Nao usar projeto de producao.
- Nao desabilitar RLS para passar smoke test.
- Nao criar policy permissiva `using (true)`.
- Nao testar com dados reais de cliente.
- Nao implementar features novas.

---

## Testes obrigatorios

```text
[ ] supabase db push aplica migrations 000-033 sem erro
[ ] bucket context-builder-private existe e e privado
[ ] check_supabase_contracts.py passa
[ ] GET /health retorna 200
[ ] owner cria workspace via API
[ ] owner vira membro role=owner
[ ] outsider nao acessa workspace do owner
[ ] upload good.txt retorna 202
[ ] source tem storage_path canonico
[ ] processing_job ingest tem idempotency_key
[ ] worker ingest cria chunks sem status failed/rejected
[ ] service role nao aparece em stdout/stderr
[ ] smoke test pode rodar duas vezes sem quebrar por duplicidade
[ ] smoke completo com --full roda somente depois do minimo passar
```

---

## Criterios de aceite

```text
[ ] docs/07-operations/SUPABASE_REAL_ENVIRONMENT.md criado
[ ] docs/07-operations/SMOKE_TEST_SUPABASE.md criado
[ ] scripts/smoke/check_supabase_contracts.py criado
[ ] scripts/smoke/supabase_smoke.py criado
[ ] migrations 000-033 aplicadas em projeto Supabase dev
[ ] bucket privado criado
[ ] Auth real validado com owner e outsider
[ ] RLS validado com anon/JWT
[ ] upload real validado
[ ] worker ingest processa arquivo real
[ ] chunks existem no banco sem status failed/rejected
[ ] resultados documentados com data/hora e project ref sem secrets
```

---

## Referencias

- `supabase/migrations/`
- `apps/api/src/context_builder/`
- `workers/ingest/src/worker_ingest/`
- `tasks/TASK-007-integrity-hardening.md`
