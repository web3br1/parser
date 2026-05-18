# Matriz de Testes Pre-Supabase

## Objetivo

Mapear o que precisa estar coberto antes de usar Supabase real. Esta matriz evita confundir teste unitario, contrato local, smoke mockado e smoke real.

---

## Matriz por camada

| Camada | Suite | Supabase real? | LLM real? | Status esperado antes TASK-010 |
|---|---|---:|---:|---|
| Normalizers | `packages/normalizers/tests` | Nao | Nao | Obrigatorio |
| Parsers | `packages/parsers/tests` | Nao | Nao | Obrigatorio |
| Security | `packages/security/tests` | Nao | Nao | Obrigatorio |
| Schema registry | `packages/schema_registry/tests` | Nao | Nao | Obrigatorio |
| Model gateway | `packages/model_gateway/tests` | Nao | Nao, mock | Obrigatorio |
| Observability | `packages/observability/tests` | Nao | Nao | Obrigatorio |
| Ingest worker | `workers/ingest/tests` | Nao, mock | Nao | Obrigatorio |
| Classification worker | `workers/classification/tests` | Nao, mock | Nao, mock | Obrigatorio |
| Extraction worker | `workers/extraction/tests` | Nao, mock | Nao, mock | Obrigatorio |
| Sync worker | `workers/sync/tests` | Nao, mock | Nao | Obrigatorio |
| API | `tests/api` | Nao, mock | Nao | Obrigatorio |
| SQL contracts | `tests/integrity` | Nao | Nao | Obrigatorio |
| Supabase smoke | `scripts/smoke/supabase_smoke.py` | Sim | Opcional | TASK-010 |

---

## Cobertura minima por feature

### Upload

```text
[ ] arquivo valido retorna 202
[ ] fake.pdf retorna 422
[ ] extensao bloqueada retorna 422
[ ] duplicado retorna 409
[ ] staff/reviewer retorna 403
[ ] storage_path nao usa filename original
[ ] request_id entra no job metadata
```

### Ingest

```text
[ ] job succeeded retorna cached
[ ] idempotency por source/file_hash
[ ] invalid file falha sem retry
[ ] workspace mismatch falha sem retry
[ ] zero chunks falha sem retry
[ ] RPC failure chama retry
[ ] temp file cleanup logado
```

### Classification

```text
[ ] injection bloqueia LLM
[ ] classification fora da allowlist vai unknown
[ ] confidence abaixo do threshold vai unknown
[ ] parse_failed vira succeeded + needs_review
[ ] job extraction e criado com idempotency_key
[ ] dispatch acontece apenas depois do commit/RPC
[ ] raw_response completo nao e salvo
```

### Extraction

```text
[ ] validation_failed vira unknown
[ ] contact_info vazio vira unknown
[ ] business_rules sem evidence vira unknown
[ ] business_hours multi gera N records
[ ] records_created=0 vira needs_review
[ ] token usage logado mesmo em falha de dominio
```

### Review

```text
[ ] reviewer/manager/owner acessam
[ ] staff nao acessa
[ ] approve usa RPC existente
[ ] edit cria nova versao quando aplicavel
[ ] reject registra evento correto
[ ] unknown reclassify enfileira extraction
```

### Observability

```text
[ ] X-Request-ID gerado
[ ] X-Request-ID preservado
[ ] 500 inclui request_id
[ ] stack so em log
[ ] Authorization redigido
[ ] raw_response redigido
[ ] chunk.content redigido
```

### Integrity

```text
[ ] unique source workspace/file_hash existe
[ ] complete_ingest_job existe
[ ] complete_classification_job existe
[ ] complete_extraction_job existe
[ ] get_or_create_processing_job existe
```

---

## Comando consolidado local

Quando o ambiente estiver com dependencias:

```bash
pytest packages/ workers/ tests/api/ tests/integrity -v
ruff check .
mypy packages/ apps/api/ workers/
```

Resultado esperado:

```text
100% verde antes da TASK-010
```

