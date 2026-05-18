# TASK-007 - Integrity Hardening

**Projeto:** Context Builder Empresarial  
**Status:** `ready`  
**Versao:** 1.0  
**Agente:** Claude Code / Codex  
**Estimativa:** 1-2 sessoes  
**Depende de:** TASK-002, TASK-003, TASK-004, TASK-005  
**Bloqueia:** publication flow, query endpoint, uso em beta com dados reais

---

## Objetivo

Eliminar os riscos de perda de dados e inconsistencia em falhas parciais. Esta task troca a "atomicidade ilusoria" dos stubs de transacao por contratos executaveis no banco, fecha deduplicacao concorrente e garante que upload/ingest/classification/extraction nao deixem registros parcialmente aplicados.

Escopo:

```text
API upload
  -> dedupe garantido por constraint
  -> storage upload com rollback seguro
  -> job queued idempotente

worker-ingest
  -> quality report + chunks + source/job update em RPC atomica

worker-classification
  -> classification json + unknown queue + extraction job + job succeeded em RPC atomica
  -> dispatch Celery apenas apos commit

worker-extraction
  -> evidence + fact/rule + chunk/job update em RPC atomica
```

---

## Problemas que esta task fecha

| Achado | Risco | Status esperado |
|---|---|---|
| `db.transaction()` e apenas `yield` | Delete/insert parcial, perda de chunks | RPCs Postgres atomicas |
| Dedupe por check antes do insert | Race condition em uploads simultaneos | Unique constraint no banco |
| `python-magic` depende de `libmagic` | Validador pode falhar em container | Docker instala e valida `libmagic` |
| Storage pode ficar orfao | Custo, risco de dados binarios sem source | GC de storage orfao |
| Enqueue apos DB sem recuperacao | Jobs podem ficar `queued` sem dispatch | scheduler de reenqueue |

---

## Arquivos a criar ou modificar

```text
supabase/migrations/
  029_integrity_constraints.sql
  030_ingest_rpc.sql
  031_classification_rpc.sql
  032_extraction_rpc.sql

apps/api/src/context_builder/
  routers/sources.py
  services/ingest_queue.py

workers/ingest/src/worker_ingest/
  db.py
  tasks.py

workers/classification/src/worker_classification/
  db.py
  tasks.py
  extraction_queue.py

workers/extraction/src/worker_extraction/
  db.py
  tasks.py

workers/sync/src/worker_sync/
  storage_gc.py
  reenqueue.py

scripts/dev/
  check_local_stack.ps1
  start_local_stack.ps1
  stop_local_stack.ps1

tests/
  api/test_sources_upload.py
  integrity/test_rpc_contracts.py
  workers/test_reenqueue.py
  workers/test_storage_gc.py
```

---

## Decisoes fechadas

### 1. Transacoes reais via RPC

O Supabase/PostgREST nao oferece transacao multi-request pelo client Python. Portanto, qualquer fluxo com mais de um write que precise ser atomico deve virar RPC PL/pgSQL.

**Nao usar `db.transaction()` como garantia real** fora de testes unitarios. O stub pode continuar como interface de teste, mas producao deve chamar RPC.

### 2. Dedupe de source por workspace

Criar constraint no banco:

```sql
create unique index uq_sources_workspace_file_hash_active
on public.sources(workspace_id, file_hash)
where deleted_at is null and file_hash is not null;
```

Motivo: permite reupload depois de soft delete, mas impede duplicatas ativas sob concorrencia.

### 3. Job idempotente

`processing_jobs.idempotency_key` ja e `NOT NULL UNIQUE`. Toda criacao de job deve usar key deterministica:

```text
ingest:      sha256("ingest:{source_id}:{file_hash}")
classify:    sha256("{chunk_id}:{prompt_signature}:{provider}:{model}")
extraction:  sha256("extraction:{chunk_id}:{fact_type}:{prompt_signature}:{model}")
```

Se insert bater em conflito, buscar o job existente e retornar o `id` existente.

### 4. Storage GC

Arquivos em storage sem `sources.storage_path` correspondente devem ser removidos por job periodico.

Politica MVP:

```text
prefixo: workspaces/{workspace_id}/sources/{source_id}/
idade minima para delecao: 24h
dry_run default: true
delete real apenas quando DRY_RUN=false
```

### 5. Reenqueue de jobs `queued`

Criar scheduler para jobs que ficaram `queued` sem dispatch.

Politica MVP:

```text
processing_jobs.status = 'queued'
started_at is null
created_at < now() - interval '5 minutes'
job_type in ('ingest', 'classification', 'extraction')
```

O scheduler apenas reenvia ao Celery. Nao altera dados de negocio.

---

## RPCs obrigatorias

### `complete_ingest_job(...)`

Executa em uma transacao:

```text
upsert source_quality_reports
delete chunks by source
insert chunks
update source.status = 'processing'
update processing_jobs.status = 'succeeded'
```

Falha em qualquer passo deve rollbackar tudo.

### `complete_classification_job(...)`

Executa em uma transacao:

```text
update chunks.classification
insert unknown_facts_queue items
insert processing_jobs extraction queued
update chunks.status
update classification processing_jobs.status = 'succeeded'
```

Retorna lista de `extraction_job_ids` a despachar depois do commit.

### `complete_extraction_job(...)`

Executa em uma transacao:

```text
insert evidence_spans, se houver
insert extracted_facts ou business_rules
insert unknown_facts_queue em falha de dominio
update chunks.status
update extraction processing_jobs.status = 'succeeded'
```

Retorna `records_created` e `chunk_status`.

---

## API upload - ajuste obrigatorio

Em `sources.py`, remover dependencia exclusiva do pre-check de duplicidade.

Fluxo correto:

```text
1. Calcular file_hash
2. Tentar insert em sources
3. Se conflito unique workspace/file_hash:
   -> retornar 409 com existing_source_id
4. Continuar upload
```

O pre-check pode continuar como otimizacao UX, mas a garantia deve ser o banco.

---

## libmagic sem Docker

Docker nao faz parte do fluxo operacional. A dependencia `python-magic` continua exigindo a
biblioteca nativa `libmagic` no host ou runtime escolhido.

Windows dev:

```text
Instalar python-magic-bin ou garantir libmagic disponivel no PATH, conforme ambiente local.
```

Linux deploy/runtime:

```text
Instalar libmagic1 no host, VM ou imagem de deploy usada fora deste repositorio.
```

Adicionar teste de startup ou unitario:

```python
from security.file_validator import magic_available

assert magic_available() is True
```

---

## Testes obrigatorios

```text
[ ] Dois uploads simultaneos do mesmo arquivo no mesmo workspace -> apenas uma source ativa
[ ] Conflito unique retorna 409 com existing_source_id
[ ] complete_ingest_job rollbacka se insert_chunks falhar
[ ] complete_ingest_job nao deixa source sem chunks em falha parcial
[ ] complete_classification_job retorna extraction_job_ids para dispatch pos-commit
[ ] dispatch nao roda se RPC de classification falhar
[ ] complete_extraction_job com records_created=0 marca chunk needs_review
[ ] reenqueue encontra job queued antigo e chama .delay()
[ ] reenqueue ignora jobs recentes
[ ] storage_gc dry_run nao deleta
[ ] storage_gc delete remove apenas objetos orfaos com idade > 24h
[ ] check_local_stack documenta o requisito de Redis sem Docker
[ ] ambiente de runtime documenta libmagic fora do repositorio
```

---

## O que NAO fazer

- Nao implementar publication flow.
- Nao implementar query endpoint.
- Nao adicionar LLM.
- Nao chamar Celery `.delay()` dentro de RPC ou transacao.
- Nao depender de `db.transaction()` Python para atomicidade real.
- Nao apagar arquivo de storage com menos de 24h no GC.
- Nao alterar o contrato publico de upload alem do erro 409 ja existente.

---

## Criterios de aceite

```text
[ ] Migrations 029-032 aplicam sem erro em banco limpo
[ ] processing_jobs sempre recebe idempotency_key
[ ] sources tem unique index parcial por workspace_id + file_hash
[ ] ingest usa RPC atomica para persistencia final
[ ] classification usa RPC atomica para classification + unknown + extraction jobs
[ ] extraction usa RPC atomica para persistencia final
[ ] dispatch Celery acontece apenas apos commit confirmado
[ ] libmagic esta documentado como requisito do runtime sem Docker
[ ] storage GC existe com dry_run default
[ ] reenqueue de jobs queued existe
[ ] pytest tests/integrity/ tests/workers/ tests/api/ passa
[ ] ruff check . retorna zero erros
[ ] mypy apps/ workers/ packages/ retorna zero erros
```
