# Regression Gates

## Objetivo

Definir os gates que devem rodar antes de qualquer task grande, especialmente TASK-010 e futuras tasks de publicacao/query.

---

## Gate rapido

Usar quando a mudanca foi pequena:

```bash
python -m compileall apps packages workers tests
pytest packages/observability/tests tests/api/test_observability.py -q
```

Aceite:

```text
sem erro de sintaxe
observability continua verde
```

---

## Gate backend

Usar antes de mexer em Supabase real:

```bash
pytest packages/ workers/ tests/api/ tests/integrity -v
```

Aceite:

```text
todos os testes passam
nenhuma chamada real para Supabase exceto suites explicitamente marcadas
nenhuma chamada real para LLM
```

---

## Gate qualidade

Usar antes de merge/release:

```bash
ruff check .
npm run typecheck:python
npm run typecheck:python:strict-full
corepack pnpm --filter @context-builder/web typecheck
node scripts/smoke/frontend_console_smoke.mjs
uv run --cache-dir .uv-cache python scripts/ci/secret_scan.py
```

Aceite:

```text
zero lint error
zero type error nos pacotes Python cobertos pelo gate atual e pelo strict amplo de API/workers
frontend typecheck executa pacote real e nao passa por ausencia de script
smoke frontend executa browser headless e falha em console/page errors
secret scan bloqueia segredos reais em codigo, docs e fixtures
```

Comandos Python obrigatorios:

```bash
npm run typecheck:python
npm run typecheck:python:strict-full
```

`typecheck:python` cobre os pacotes compartilhados e bibliotecas locais usados
por API/workers (`normalizers`, `parsers`, `schema_registry`, `security`,
`observability`, `model_gateway`, `domain`). `typecheck:python:strict-full`
tambem cobre `context_builder` e todos os workers Python. Ambos devem passar
antes de release/piloto.

---

## Gate operacional local

Usar para validar uma stack local ja iniciada. O smoke nao inicia nem para API,
Redis ou workers:

```powershell
uv run --cache-dir .uv-cache python scripts\smoke\run_real_smoke.py --target local --full --json-report .run\smoke-local-full.json
```

Validar manualmente:

```text
.env.example tem Supabase, Redis, models e bucket
WORKSPACE_STORAGE_BUCKET definido
REDIS_URL aponta para Redis local ou gerenciado acessivel
API_BASE_URL aponta para a API em execucao
workers de ingest, classification e extraction estao em execucao
```

---

## Gate pre-Supabase real

Checklist:

```text
[ ] Gate backend passou
[ ] Gate qualidade passou
[ ] Gate operacional passou
[ ] migrations 000-042 presentes
[ ] `run_real_smoke.py --target local --full` passa contra runtime ja iniciado
[ ] nenhum teste depende de dado real de cliente
[ ] service role nao aparece em logs/test outputs
[ ] Gate context bundle passou
```

Se qualquer item falhar, nao iniciar TASK-010.

---

## Gate context bundle

Usar antes de alterar exportacao, knowledge, published views, query readiness ou
contratos consumidos pelo chatbot externo:

```bash
uv run --cache-dir .uv-cache pytest tests/api/test_context_bundle.py tests/api/test_knowledge.py tests/integrity -q
uv run --cache-dir .uv-cache ruff check apps/api tests/api
uv run --cache-dir .uv-cache python scripts/ci/secret_scan.py
npm run typecheck:python
npm run typecheck:python:strict-full
```

Aceite:

```text
context_bundle.v1 retorna somente conhecimento publicado
readiness bloqueia unknowns e contradicoes abertas
hash do bundle e deterministico
export cria audit log seguro
nenhum campo sensivel, prompt cru, path local ou conteudo nao publicado aparece no bundle
secret scan nao encontra segredo real
```
