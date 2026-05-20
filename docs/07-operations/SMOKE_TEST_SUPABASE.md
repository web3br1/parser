# Smoke Test Supabase

Procedimento da TASK-010 para validar o ambiente Supabase real.

## Comandos oficiais

Readiness local:

```bash
python scripts/smoke/real_readiness.py
python scripts/smoke/real_readiness.py --json
```

O readiness valida pre-condicoes locais e nao chama Supabase. Ele nao substitui
`check_supabase_contracts.py`, que continua sendo o gate remoto de contratos.
Para SQL, ele exige `psql` no `PATH` junto de uma DB URL, ou
`SUPABASE_ACCESS_TOKEN` com project ref.

Contratos estaticos:

```bash
python scripts/smoke/check_supabase_contracts.py
```

Smoke minimo:

```bash
python scripts/smoke/supabase_smoke.py
```

Smoke completo:

```bash
python scripts/smoke/supabase_smoke.py --full
```

O smoke completo depende do smoke minimo passar primeiro.

Relatorio JSON opcional:

```powershell
$env:SMOKE_REPORT_JSON=".run\smoke-full.json"
python scripts/smoke/supabase_smoke.py --full
```

## Antes de rodar

- `.env` local existe e foi criado a partir de `.env.example`.
- `WORKSPACE_STORAGE_BUCKET=context-builder-private`.
- Migrations `000-045` foram aplicadas.
- Bucket `context-builder-private` existe e e privado.
- SQL esta acionavel via `psql` + DB URL, ou via `SUPABASE_ACCESS_TOKEN` + project ref.
- Redis esta acessivel via `REDIS_URL`.
- Stack local esta de pe:

```powershell
.\scripts\dev\check_local_stack.ps1
.\scripts\dev\start_local_stack.ps1
```

O `start_local_stack.ps1` usa workers reais por padrao (`CELERY_TASK_ALWAYS_EAGER=0`).
Use `-Eager` apenas para debug local sem validar Redis/Celery reais.

- API responde:

```bash
curl http://localhost:8000/health
```

## Smoke minimo

Execute da raiz do projeto:

```bash
python scripts/smoke/supabase_smoke.py
```

Validacoes minimas esperadas:

```text
1. Auth owner ok
2. Auth outsider ok
3. Health check API 200
4. Workspace criado pelo owner
5. owner aparece em workspace_members
6. Upload de fixture txt retorna source_id e job_id
7. Storage path usa bucket privado e path canonico
8. processing_job de ingest foi criado
9. worker-ingest cria chunks
10. chunks existem sem status failed/rejected (podem estar pending ou ja processados)
11. outsider nao ve dados do owner
12. stdout/stderr nao contem service role
```

Resultado esperado:

```text
SMOKE TEST PASSED
```

## Smoke completo

Depois do minimo:

```bash
python scripts/smoke/supabase_smoke.py --full
```

Validacoes adicionais esperadas:

```text
1. classification processa chunks
2. extraction cria extracted_facts
3. review queue retorna facts
4. approve fact conclui sem erro
5. publish fact conclui sem erro
6. published_facts contem o fato publicado
```

## Dados de teste

Fixture preferencial:

```text
examples/good.txt
```

Se o script precisar gerar fixture temporaria:

```text
Servico: Corte feminino
Preco: R$ 120
Horario: Segunda a sexta, 09:00 as 18:00
Pagamento: pix e cartao
```

Dados de smoke devem ser prefixados com timestamp ou identificador `smoke`.

## Falhas comuns

### `bucket not found`

Confirme:

```sql
select id, public
from storage.buckets
where id = 'context-builder-private';
```

### `permission denied`

Confirme que:

- API e workers usam `SUPABASE_SERVICE_ROLE_KEY`.
- Testes de RLS usam anon/JWT.
- A service role nao foi trocada pela anon key no `.env`.

### timeout no ingest

```powershell
Get-Content .run\logs\worker-ingest.err.log -Tail 100
Get-Content .run\logs\api.err.log -Tail 100
```

SQL:

```sql
select id, job_type, status, created_at, metadata
from processing_jobs
order by created_at desc
limit 20;
```

### smoke full falha, minimo passa

Verifique primeiro workers e variaveis de modelo:

```bash
Get-Content .run\logs\worker-classification.err.log -Tail 100
Get-Content .run\logs\worker-extraction.err.log -Tail 100
```

Confirme que a key de modelo existe no `.env` local. Nao registre essa key no output.

### Diagnosticar uma rodada por source

Use o script abaixo para ver source, jobs, chunks, facts, rules e unknowns via HTTP:

```bash
python scripts/smoke/diagnose_source.py --workspace-id <workspace-id> --source-id <source-id>
```

### Limpar dados de smoke

Soft-delete dos workspaces com slug `smoke-*`:

```bash
python scripts/smoke/cleanup_smoke.py
```

## Checklist de aceite

- [ ] Readiness local passa.
- [ ] Contratos estaticos passam.
- [ ] Smoke minimo passa.
- [ ] Smoke completo passa depois do minimo.
- [ ] Smoke real foi rodado com workers separados, sem modo eager.
- [ ] Relatorio JSON foi gerado quando necessario.
- [ ] Diagnostico por `source_id` funciona para a rodada.
- [ ] RLS bloqueia outsider.
- [ ] Bucket privado confirmado.
- [ ] Nenhum secret aparece em stdout/stderr.
- [ ] Registro de execucao contem data/hora, project ref e resultado, sem secrets.
