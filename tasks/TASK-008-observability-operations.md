# TASK-008 - Observability and Operations

**Projeto:** Context Builder Empresarial  
**Status:** `ready`  
**Versao:** 1.0  
**Agente:** Claude Code / Codex  
**Estimativa:** 1 sessao
**Depende de:** TASK-005, TASK-006 (junto com 006.5)
**Bloqueia:** beta interno, debugging confiavel, SLOs, TASK-007 (hardened)

---

## Objetivo

Padronizar logs, correlacao de requests/jobs e taxonomia de erros na API e workers. A meta e conseguir diagnosticar falhas sem expor PII, secrets ou conteudo de documentos.

---

## Problemas que esta task fecha

| Achado | Risco | Status esperado |
|---|---|---|
| API retorna 500 generico sem correlacao | Debug lento | `request_id` em resposta e logs |
| Workers logam eventos sem padrao global | Rastreamento quebrado | JSON logs uniformes |
| Stack trace pode faltar ou vazar | Triagem ruim ou risco de dados | traceback interno, resposta sanitizada |
| Falhas de dominio e tecnica misturadas | Operacao nao sabe acao correta | error taxonomy |
| Arquivos temporarios podem sobrar | Risco operacional | cleanup observavel |

---

## Arquivos a criar ou modificar

```text
packages/
  observability/
    pyproject.toml
    src/observability/
      __init__.py
      logging.py
      context.py
      errors.py
      middleware.py
    tests/
      test_logging.py
      test_errors.py

apps/api/src/context_builder/
  main.py
  dependencies.py

workers/ingest/src/worker_ingest/
  logging.py
  tasks.py

workers/classification/src/worker_classification/
  logging.py
  tasks.py

workers/extraction/src/worker_extraction/
  logging.py
  tasks.py

workers/sync/src/worker_sync/
  logging.py

.env.example
.github/workflows/ci.yml
```

---

## Contrato de correlacao

### API

Todo request deve ter `request_id`:

```text
Header aceito: X-Request-ID
Se ausente: gerar uuid4
Header de resposta: X-Request-ID
```

Em erro 500:

```json
{
  "detail": "internal_server_error",
  "request_id": "<uuid>"
}
```

### Workers

Todo job deve propagar:

```text
job_id (UUID)
workspace_id (UUID)
source_id (UUID), quando existir
workflow_id (UUID), obrigatorio (source_id ou ingest_run_id)
request_id (UUID), obrigatorio em processing_jobs.metadata
```

---

## Formato de log JSON

Campos obrigatorios:

```json
{
  "timestamp": "ISO8601",
  "level": "INFO|WARNING|ERROR",
  "service": "api|worker-*",
  "event": "event_name",
  "request_id": "...",
  "workflow_id": "...",
  "job_id": "...",
  "workspace_id": "...",
  "error_type": null,
  "error_code": null,
  "stack": "traceback string (only on error)"
}
```

### Log Redaction (redact_payload)

Implementar `redact_payload(data: dict) -> dict` centralizado com denylist:
- `authorization`, `cookie`, `api_key`, `service_role`, `access_token`, `refresh_token`
- `password`, `raw_response`, `chunk.content`, `document_content`, `file_bytes`

Output deve ser JSON line-delimited para `sys.stdout`.

Campos proibidos:

```text
document content
chunk text
raw LLM response
SUPABASE_SERVICE_ROLE_KEY
API keys
Authorization header
original file bytes
```

---

## Error taxonomy

Criar `packages/observability/src/observability/errors.py`:

```python
class BaseAppError(Exception):
    code: str
    message: str
    retryable: bool
    safe_detail: dict

class DomainError(BaseAppError):
    retryable = False

class TechnicalError(BaseAppError):
    retryable = True
    provider: str = None
    operation: str = None
```

### Taxonomia:
- **Domain**: `FileValidationError`, `QualityGateError`, `WorkspaceMismatchError`, `ClassificationParseError`
- **Technical**: `DatabaseError`, `StorageError`, `QueueError`, `ModelProviderError`, `OperationTimeoutError`, `ProviderTimeoutError`

Regras:

```text
DomainError -> sem retry, status failed ou needs_review conforme fluxo
TechnicalError -> retry conforme policy do worker
Unexpected Exception -> retry se worker, 500 se API
```

---

## API exception handlers

Substituir handler generico por handler que:

```text
1. Gera/usa request_id
2. Loga traceback completo internamente
3. Remove headers/secrets do log
4. Retorna resposta sanitizada
5. Nunca mascara HTTPException existente
```

Resposta de erro tecnico:

```json
{
  "detail": "internal_server_error",
  "request_id": "<uuid>"
}
```

Resposta de erro de dominio:

```json
{
  "detail": {
    "code": "file_validation_failed",
    "reason": "magic_bytes_fail"
  },
  "request_id": "<uuid>"
}
```

---

## Temp file observability

Em upload e ingest:

```python
try:
    # operation
finally:
    # cleanup always here
    # log temp_file_deleted
    # if cleanup fails, log warning without masking original error
```

Nunca logar nome original do arquivo ou path local completo.

---

## Metricas MVP

Sem Prometheus obrigatorio nesta task. Registrar via logs estruturados:

```text
api_upload_started
api_upload_accepted
api_upload_failed
ingest_started
ingest_succeeded
ingest_failed
classification_started
classification_succeeded
classification_failed
extraction_started
extraction_succeeded
extraction_failed
storage_gc_started
storage_gc_finished
reenqueue_started
reenqueue_finished
```

---

## Testes obrigatorios

```text
[ ] API sem X-Request-ID gera um e retorna header
[ ] API com X-Request-ID preserva o valor
[ ] erro 500 retorna request_id sem stack trace
[ ] log interno de erro contem traceback e request_id
[ ] Authorization header nao aparece em log
[ ] SUPABASE_SERVICE_ROLE_KEY nao aparece em log
[ ] worker ingest loga job_id/source_id/workspace_id
[ ] worker classification loga chunk_id sem chunk.content
[ ] worker extraction loga fact_type sem raw_response
[ ] DomainError nao chama retry
[ ] TechnicalError chama retry conforme policy
```

---

## O que NAO fazer

- Nao implementar dashboards.
- Nao instalar stack externa de observabilidade.
- Nao enviar logs para SaaS externo.
- Nao logar conteudo de documentos para facilitar debug.
- Nao mudar contratos HTTP alem de adicionar `request_id`.

---

## Criterios de aceite

```text
[ ] packages/observability existe e e membro do uv workspace
[ ] todos os services usam logger JSON compartilhado
[ ] API retorna X-Request-ID
[ ] respostas 500 incluem request_id
[ ] traceback fica apenas em log interno
[ ] workers incluem job_id e ids de dominio nos logs
[ ] secrets e conteudo de documento nao aparecem em logs testados
[ ] pytest packages/observability tests/api workers/ passa
[ ] ruff check . retorna zero erros
[ ] mypy packages/observability apps/api workers/ retorna zero erros
```
