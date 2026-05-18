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
```

Aceite:

```text
zero lint error
zero type error nos pacotes Python cobertos pelo gate atual e pelo strict amplo de API/workers
frontend typecheck executa pacote real e nao passa por ausencia de script
smoke frontend executa browser headless e falha em console/page errors
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

## Gate operacional

Usar antes de subir a stack local:

```powershell
.\scripts\dev\check_local_stack.ps1
```

Validar manualmente:

```text
.env.example tem Supabase, Redis, models e bucket
WORKSPACE_STORAGE_BUCKET definido
REDIS_URL aponta para Redis local ou gerenciado acessivel
```

---

## Gate pre-Supabase real

Checklist:

```text
[ ] Gate backend passou
[ ] Gate qualidade passou
[ ] Gate operacional passou
[ ] migrations 000-032 presentes
[ ] scripts de smoke da TASK-010 prontos ou planejados
[ ] nenhum teste depende de dado real de cliente
[ ] service role nao aparece em logs/test outputs
```

Se qualquer item falhar, nao iniciar TASK-010.
