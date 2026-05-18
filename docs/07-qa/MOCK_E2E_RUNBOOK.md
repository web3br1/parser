# Mock E2E Runbook

## Objetivo

Executar um ensaio ponta a ponta sem Supabase real. Este runbook valida contratos entre API, workers, filas e persistencia mockada.

---

## Caminho feliz mockado

```text
1. API recebe upload
2. API valida arquivo
3. API cria source mockada
4. API cria job ingest mockado
5. API chama ingest_source.delay mockado
6. ingest baixa arquivo mockado
7. ingest extrai texto/chunks
8. ingest chama complete_ingest_job mockado
9. classification classifica chunk mockado
10. classification chama complete_classification_job mockado
11. classification faz dispatch pos-commit mockado
12. extraction persiste fact/rule via complete_extraction_job mockado
```

---

## Comando recomendado

```bash
pytest \
  tests/api/test_sources_upload.py \
  workers/ingest/tests/test_ingest_tasks.py \
  workers/classification/tests/test_classification_tasks.py \
  workers/extraction/tests/test_extraction_tasks.py \
  -v
```

---

## Evidencias obrigatorias

Durante a execucao, confirmar via asserts/logs:

```text
request_id existe
job_id existe
workflow_id = source_id no caminho ingest
storage_path canonico
idempotency_key presente
raw_text truncado em unknown_queue
raw_response completo ausente
dispatch depois de complete_classification_job
domain failures sem retry
technical failures com retry
```

---

## Casos negativos obrigatorios

```text
fake.pdf
arquivo vazio
arquivo duplicado
workspace_mismatch
classification_parse_failed
injection_suspected
contact_info vazio
business_rule sem evidence
records_created=0
storage rollback
job insert failure
```

---

## Sinais de bloqueio para TASK-010

Nao seguir para Supabase real se ocorrer:

```text
teste unitario precisa de Supabase real
teste de API imprime stack trace ao cliente
service role aparece em stdout/stderr
request_id nao chega em job metadata
worker chama .delay() dentro de transacao/RPC
raw_response completo salvo em classification
```
