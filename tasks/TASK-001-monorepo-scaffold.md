# TASK-001 — Monorepo Scaffold

> Historical task. Some runtime notes below predate TASK-013/TASK-015.
> Canonical local runtime docs are now `docs/operations/LOCAL_RUNTIME.md` and
> `docs/operations/DOCKER_LOCAL_RUNTIME.md`; smoke scripts validate an
> already-running stack.

**Projeto:** Context Builder Empresarial  
**Status:** `ready`  
**Agente:** Claude Code / Codex  
**Estimativa:** 1 sessão  
**Depende de:** nada  
**Bloqueia:** TASK-002 (ingest worker), TASK-003 (FastAPI base)

---

## Objetivo

Criar a estrutura completa de pastas e arquivos de configuração do monorepo.  
**Não implementar lógica de negócio.** Apenas boilerplate funcional que permita as próximas tasks começarem sem atrito.

---

## Estado atual do repositório

Já existem no repo — **não tocar, não mover, não recriar:**

```
supabase/migrations/         ← 25 migrations prontas (000–024)
docs/                        ← documentação completa
examples/                    ← fixtures de fact types
prototype/                   ← wireframe estático
backend/app/normalization.py ← mover para packages/normalizers/ (ver abaixo)
CLAUDE.md                    ← manter, não sobrescrever
```

---

## Estrutura alvo

Após a task, o repo deve ter exatamente esta estrutura (além do que já existe):

```
apps/
  web/                       ← Next.js App Router
    package.json
    tsconfig.json
    next.config.ts
    tailwind.config.ts
    postcss.config.js
    src/
      app/
        layout.tsx
        page.tsx
        globals.css
      lib/
        .gitkeep
      components/
        .gitkeep

  api/                       ← FastAPI
    pyproject.toml
    Makefile
    src/
      context_builder/
        __init__.py
        main.py              ← FastAPI app factory (sem routers ainda)
        config.py            ← Settings via pydantic-settings
        dependencies.py      ← supabase client factory (sem lógica)

workers/
  ingest/
    pyproject.toml
    src/
      worker_ingest/
        __init__.py
        celery_app.py        ← Celery app factory, broker via env
  classification/
    pyproject.toml
    src/
      worker_classification/
        __init__.py
        celery_app.py
  review/
    pyproject.toml
    src/
      worker_review/
        __init__.py
        celery_app.py
  sync/
    pyproject.toml
    src/
      worker_sync/
        __init__.py
        celery_app.py

packages/
  normalizers/
    pyproject.toml
    src/
      normalizers/
        __init__.py
        currency.py          ← mover lógica de normalization.py
        time.py              ← mover lógica de normalization.py
        date.py              ← mover lógica de normalization.py
        percent.py           ← mover lógica de normalization.py
    tests/
      test_currency.py       ← testes básicos de normalize_currency
      test_time.py
      test_date.py
  schema_registry/
    pyproject.toml
    src/
      schema_registry/
        __init__.py
        types.py             ← TypedDicts/dataclasses dos 7 fact types MVP
  model_gateway/
    pyproject.toml
    src/
      model_gateway/
        __init__.py
        base.py              ← interface abstrata ModelClient
        openai_client.py     ← stub, não implementar chamadas ainda
        anthropic_client.py  ← stub, não implementar chamadas ainda
  domain/
    pyproject.toml
    src/
      domain/
        __init__.py
        models.py            ← dataclasses: Source, Chunk, Fact, Rule, Unknown
        states.py            ← enums de estado (source, chunk, fact, answer)
  security/
    pyproject.toml
    src/
      security/
        __init__.py
        file_validator.py    ← interface + magic bytes check stub

scripts/
  dev/
    check_local_stack.ps1    ← valida .env, uv, npx e Redis via REDIS_URL
    start_local_stack.ps1    ← inicia API + workers como processos locais
    stop_local_stack.ps1     ← encerra processos locais iniciados pelo script

.github/
  workflows/
    ci.yml                   ← lint + typecheck + pytest (sem deploy)

pyproject.toml               ← root Python workspace (uv workspaces)
package.json                 ← root JS workspace (pnpm workspaces)
pnpm-workspace.yaml
.env.example
.gitignore
```

---

## Regras de implementação

### Geral

- Boilerplate real, sem `# TODO` sem contexto. Se um módulo é stub, deixar o corpo com `pass` ou `raise NotImplementedError`.
- Nenhuma variável de ambiente hardcoded. Usar `.env.example` como fonte da verdade.
- Sem dependência circular entre packages.

### Python

- Python `>=3.12`
- Usar `uv` como gerenciador de pacotes. Cada package/app/worker tem seu próprio `pyproject.toml`.
- Root `pyproject.toml` declara o workspace uv com todos os membros.
- Dependências compartilhadas ficam nos packages, não duplicadas em apps.
- `ruff` para lint, `mypy` para typecheck — configurados no root `pyproject.toml`.
- Todos os imports usam caminho absoluto (`from normalizers.currency import normalize_currency`).

### TypeScript / Next.js

- TypeScript strict mode.
- `pnpm` workspaces.
- `apps/web/` usa Next.js 14+ App Router.
- shadcn/ui como dependência (não instalar componentes ainda, apenas configurar).
- `tailwind.config.ts` preparado para dark mode.

### Migração de `normalization.py`

O arquivo `backend/app/normalization.py` deve ser refatorado:

1. Mover cada função para o módulo correspondente em `packages/normalizers/src/normalizers/`:
   - `normalize_currency` → `currency.py`
   - `normalize_time` → `time.py`
   - `normalize_date` → `date.py`
   - `normalize_percent` → `percent.py`
2. Manter as assinaturas e lógica idênticas (zero alteração de comportamento).
3. Criar `packages/normalizers/src/normalizers/__init__.py` exportando todas as funções.
4. Apagar `backend/app/normalization.py` após mover.
5. Apagar `backend/app/__init__.py` apenas se o diretório `backend/app/` ficar vazio após a migração.

### `domain/states.py`

Implementar os enums exatamente conforme o CLAUDE.md do projeto:

```python
from enum import StrEnum

class SourceState(StrEnum):
    DRAFT = "draft"
    UPLOADED = "uploaded"
    QUALITY_CHECKED = "quality_checked"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    PUBLISHED = "published"
    FAILED = "failed"
    DEPRECATED = "deprecated"
    DELETED = "deleted"

class ChunkState(StrEnum):
    PENDING = "pending"
    CLASSIFIED = "classified"
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"

class FactState(StrEnum):
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"
    CONFLICTED = "conflicted"

class AnswerState(StrEnum):
    VALID_ANSWER = "valid_answer"
    NOT_FOUND = "not_found"
    CONFLICTING_SOURCES = "conflicting_sources"
    NEEDS_HUMAN_VALIDATION = "needs_human_validation"
    PARTIAL_ANSWER = "partial_answer"
```

### `schema_registry/types.py`

Implementar os 7 fact types do MVP como `TypedDict` com `Required`/`NotRequired`:

- `service_price@1.0.0`
- `business_hours@1.0.0`
- `payment_method@1.0.0`
- `discount_rule@1.0.0`
- `cancellation_policy@1.0.0`
- `contact_info@1.0.0`
- `faq_item@1.0.0`

Campos conforme `docs/00-start-here/MVP_DECISIONS.md`. Adicionar `contact_info` e `faq_item` seguindo o padrão dos existentes.

### `.env.example`

```dotenv
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# Redis
REDIS_URL=redis://localhost:6379/0

# OpenAI
OPENAI_API_KEY=

# Anthropic
ANTHROPIC_API_KEY=

# App
APP_ENV=development
LOG_LEVEL=INFO
WORKSPACE_STORAGE_BUCKET=context-builder-private
```

### Stack local sem Docker

O scaffold não usa Docker. Serviços mínimos para dev local:

```powershell
.\scripts\dev\check_local_stack.ps1
.\scripts\dev\start_local_stack.ps1
.\scripts\dev\stop_local_stack.ps1
```

`REDIS_URL` deve apontar para Redis local, WSL, Memurai ou serviço gerenciado. Supabase real
é gerenciado pelo CLI `npx supabase`, não por Postgres local.

### `ci.yml`

Jobs:

1. `lint-py` — `ruff check .`
2. `typecheck-py` — `mypy packages/ apps/api/ workers/`
3. `test-py` — `pytest packages/`
4. `typecheck-ts` — `pnpm -r tsc --noEmit`

Trigger: `push` e `pull_request` em `main`.

---

## O que NÃO fazer

- Não implementar endpoints FastAPI (TASK-003).
- Não implementar tasks Celery (TASK-002).
- Não criar componentes React/shadcn (TASK-004+).
- Não conectar ao Supabase de verdade (apenas factory stub).
- Não alterar nenhum arquivo em `supabase/migrations/`.
- Não alterar nenhum arquivo em `docs/`.
- Não criar `README.md` em nenhum subdiretório.
- Não usar `poetry` — apenas `uv`.
- Não usar `yarn` ou `npm` — apenas `pnpm`.

---

## Critérios de aceite

A task está pronta quando todos os itens abaixo forem verdadeiros:

```
[ ] pnpm install na raiz não dá erro
[ ] cd apps/web && pnpm dev inicia sem erro (página em branco é ok)
[ ] cd apps/api && uvicorn context_builder.main:app --reload inicia sem erro
[ ] python -c "from normalizers import normalize_currency, normalize_time, normalize_date, normalize_percent" não dá ImportError
[ ] python -c "from domain.states import SourceState, ChunkState, FactState, AnswerState" não dá ImportError
[ ] python -c "from schema_registry.types import ServicePrice, BusinessHours" não dá ImportError
[ ] pytest packages/ -v passa todos os testes de packages
[ ] ruff check . retorna zero erros
[ ] backend/app/normalization.py não existe mais
[ ] .\scripts\dev\check_local_stack.ps1 valida o ambiente local
```

---

## Referências

- `CLAUDE.md` — princípios absolutos e stack
- `docs/00-start-here/MVP_DECISIONS.md` — fact types e estados canônicos
- `docs/02-architecture/` — arquitetura de referência
- `docs/04-data/DATA_MODEL.md` — modelos de domínio
- `supabase/migrations/` — schema do banco (não alterar)
