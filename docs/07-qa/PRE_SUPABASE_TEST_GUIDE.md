# Guia de Testes Pre-Supabase Real

## Objetivo

Garantir que o sistema esta coerente localmente antes da TASK-010. A TASK-010 deve validar infraestrutura real, nao descobrir bugs basicos de contrato, import, roteamento, idempotencia ou logs.

Regra:

```text
Se falha sem Supabase real, corrigir antes da TASK-010.
Se passa sem Supabase real e falha na TASK-010, investigar ambiente, migrations, RLS, Storage ou secrets.
```

---

## Ordem dos gates

```text
Gate 0 -> ambiente e imports
Gate 1 -> lint/type/syntax
Gate 2 -> packages puros
Gate 3 -> workers com mocks
Gate 4 -> API com mocks
Gate 5 -> contratos SQL estaticos
Gate 6 -> smoke local sem Supabase real
Gate 7 -> checklist de readiness para TASK-010
```

Nao pular gates. Um erro cedo costuma contaminar os proximos.

---

## Gate 0 - Ambiente e imports

Objetivo: confirmar que o workspace resolve imports locais.

Comandos:

```bash
python -c "from normalizers import normalize_currency, normalize_time, normalize_date"
python -c "from parsers import get_parser"
python -c "from security.file_validator import validate_file, magic_available"
python -c "from model_gateway import get_model_gateway"
python -c "from observability import get_logger, redact_payload"
python -c "from worker_ingest.tasks import ingest_source"
python -c "from worker_classification.tasks import classify_chunk_task"
python -c "from worker_extraction.tasks import extract_fact"
```

Aceite:

```text
zero ImportError
zero ModuleNotFoundError
```

---

## Gate 1 - Syntax, lint e typecheck

Comandos:

```bash
python -m compileall apps packages workers tests
ruff check .
mypy packages/ apps/api/ workers/
```

Se `ruff` ou `mypy` nao estiverem instalados:

```bash
uv sync --all-packages --dev
uv run ruff check .
uv run mypy packages/ apps/api/ workers/
```

Aceite:

```text
compileall sem erro
ruff sem erro
mypy sem erro
```

---

## Gate 2 - Packages puros

Rodar packages que nao precisam de Supabase real:

```bash
pytest packages/normalizers/tests -v
pytest packages/parsers/tests -v
pytest packages/schema_registry/tests -v
pytest packages/security/tests -v
pytest packages/model_gateway/tests -v
pytest packages/observability/tests -v
```

Aceite:

```text
todos verdes
nenhuma chamada real para LLM
nenhuma chamada real para Supabase
```

---

## Gate 3 - Workers com mocks

Rodar:

```bash
pytest workers/ingest/tests -v
pytest workers/classification/tests -v
pytest workers/extraction/tests -v
pytest workers/sync/tests -v
```

Validar manualmente no resultado:

```text
ingest: domain_failure nao chama retry
ingest: DB/RPC failure chama retry
classification: injection nao chama LLM
classification: parse_failed vira needs_review sem retry
classification: extraction jobs sao retornados para dispatch pos-commit
extraction: domain failure vira unknown_queue sem retry
extraction: records_created=0 vira needs_review
sync: reenqueue ignora jobs recentes e dispatcha jobs antigos
sync: storage_gc dry_run nao deleta
```

---

## Gate 4 - API com mocks

Rodar:

```bash
pytest tests/api -v
```

Validar:

```text
GET /health sem auth
POST /workspaces usa RPC create_workspace_with_owner
POST /upload role staff/reviewer bloqueia
POST /upload manager aceita
POST /upload fake.pdf retorna 422
POST /upload duplicado retorna 409
POST /upload valido cria source + job queued
X-Request-ID e gerado/preservado
500 retorna request_id sem stack trace
service role nao aparece em response
```

---

## Gate 5 - Contratos SQL estaticos

Rodar:

```bash
pytest tests/integrity -v
```

Checar manualmente:

```text
migrations 000-032 existem
uq_sources_workspace_file_hash_active existe
complete_ingest_job existe
complete_classification_job existe
complete_extraction_job existe
get_or_create_processing_job existe
```

Este gate nao prova que o SQL executa no Postgres. Isso fica para TASK-010.

---

## Gate 6 - Smoke local sem Supabase real

Objetivo: testar cadeia de codigo com mocks, sem banco real.

Fluxo esperado:

```text
API upload mockado
  -> storage mockado
  -> job mockado com request_id
  -> ingest task mockada
  -> classification task mockada
  -> extraction task mockada
```

Comando recomendado:

```bash
pytest tests/api workers/ingest/tests workers/classification/tests workers/extraction/tests -v
```

Aceite:

```text
request_id propagado no metadata
nenhum raw_response salvo
nenhum chunk.content em log
nenhum secret em log
```

---

## Gate 7 - Readiness para TASK-010

Antes de iniciar Supabase real, todos devem estar verdadeiros:

```text
[ ] pytest packages/ workers/ tests/api/ tests/integrity passa
[ ] ruff check . passa
[ ] mypy packages/ apps/api/ workers/ passa
[ ] Runtime local foi iniciado por Docker ou processo externo
[ ] Redis esta acessivel via REDIS_URL
[ ] .env.example tem todos os campos obrigatorios
[ ] migrations 000-045 estao em ordem
[ ] TASK-010 tem scripts de smoke planejados
```

---

## Interpretacao de falhas

| Falha | Provavel causa | Acao |
|---|---|---|
| ImportError | workspace/dependency | corrigir pyproject/uv workspace |
| Teste package falha | bug puro de codigo | corrigir antes de API/workers |
| Worker mock falha | contrato interno quebrado | corrigir worker/db/task |
| API mock falha | rota/schema/dependency | corrigir API antes de Supabase |
| SQL static falha | migration faltante/inconsistente | corrigir migrations |
| So falha no Supabase real | ambiente/RLS/policy/secret | tratar na TASK-010 |
