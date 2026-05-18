# TASK-006 — Human Review Endpoints

**Projeto:** Context Builder Empresarial  
**Status:** `ready`  
**Versão:** 2.1 (hardening — 12 bloqueadores corrigidos)  
**Agente:** Claude Code / Codex  
**Estimativa:** 1–2 sessões  
**Depende de:** TASK-003 ✅, TASK-005 ✅  
**Bloqueia:** TASK-007 (publication flow)

---

## Objetivo

Implementar os endpoints FastAPI de revisão humana. O revisor vê o chunk original ao lado dos fatos/regras extraídos e executa: aprovar, editar (com versionamento), rejeitar. A unknown queue permite reclassificar itens que o pipeline não conseguiu extrair.

Escopo desta task:

```
[TASK-005] extracted_facts / business_rules (status="extracted")
  → [TASK-006] GET  /workspaces/{id}/review             ← fila de revisão
  → [TASK-006] GET  /workspaces/{id}/review/{chunk_id}  ← detalhe do chunk
  → [TASK-006] POST .../facts/{id}/approve              ← extracted → approved
  → [TASK-006] POST .../facts/{id}/edit                 ← nova versão + approved
  → [TASK-006] POST .../facts/{id}/reject               ← extracted → rejected
  → [TASK-006] POST .../rules/{id}/approve
  → [TASK-006] POST .../rules/{id}/edit
  → [TASK-006] POST .../rules/{id}/reject
  → [TASK-006] GET  /workspaces/{id}/unknown            ← unknown queue
  → [TASK-006] POST .../unknown/{id}/reclassify         ← re-enfileira extração
  → [TASK-006] POST .../unknown/{id}/ignore
       [TASK-007] publication flow ←
```

**Não implementar:** publicação (`published`), contradiction detection, query. Esses são TASK-007 e TASK-008.

---

## Decisões fechadas

### Patch 1 — validation_events: usar DDL existente (013)

A migration `013_validation_events.sql` já existe. O schema real é:

```
actor_user_id  uuid FK auth.users
action         validation_action (enum)
target_type    text
target_id      uuid
previous_status text
new_status      text
previous_value  jsonb
new_value       jsonb
reason          text
metadata        jsonb
```

O enum `validation_action` já contém: `'approved', 'edited', 'rejected', 'published', 'deprecated', 'superseded', 'conflict_marked', 'manual_created'`.

**Não criar nova tabela.** Não usar campos `reviewer_id`, `event_type`, `before_content`, `after_content`. Usar exatamente os campos acima.

### Patch 2 — Aprovar: delegar ao RPC existente; sem evento duplicado

As migrations `022_publish_functions.sql` já contêm `approve_fact(target_fact_id, replacement_content, reason)` e `approve_rule(target_rule_id, replacement_condition, replacement_action, reason)`. Esses RPCs:

- Executam dentro de uma transação PL/pgSQL.
- Inserem `validation_events` internamente (com os campos corretos do DDL).
- Fazem `FOR UPDATE` no registro antes de atualizar.
- Verificam `has_workspace_role` internamente.

**O Python NÃO deve inserir validation_event para approve.** Apenas chamar:

```python
db.rpc("approve_fact", {"target_fact_id": str(fact_id), "reason": note}).execute()
```

**Idempotência:** `approve_fact` aceita `status IN ('extracted', 'needs_review', 'approved')`, portanto reaprovar um fato já `approved` é idempotente por design do RPC. O RPC insere um evento a cada chamada — a idempotência real está em não retornar erro. Se o produto precisar de idempotência estrita (sem evento duplicado), adicionar guard no Python antes de chamar o RPC:

```python
if fact["status"] == "approved":
    return {"status": "approved", "resource_id": fact_id}
# só chama RPC se não estava approved
```

### Patch 3 — Edit: atômico via nova migration (028)

O DDL existente tem `supersede_fact(old_fact_id, replacement_fact_id, reason)`, mas este RPC exige que o novo fato já exista. O INSERT no novo fato + a chamada ao RPC não são atômicos.

**Solução:** adicionar migration `028_review_functions.sql` com RPCs atômicos:

```
create_fact_version(old_fact_id, new_content, new_normalized_content, reason) → new_fact_id
create_rule_version(old_rule_id, new_condition, new_action, reason) → new_rule_id
reject_fact(target_fact_id, reason)
reject_rule(target_rule_id, reason)
```

Cada função executa em transação única, faz ownership check via `has_workspace_role`, e insere `validation_event` internamente.

O Python valida com Pydantic e normaliza **antes** de chamar o RPC. O RPC recebe dados já validados.

**Para approve-com-edição inline** (pequenas correções sem versionamento), usar o `approve_fact` existente com `replacement_content`. Para **nova versão** (edição estrutural), usar `create_fact_version`.

Esta task define como "edit" = sempre `create_fact_version` (nova versão). A distinção inline/versioned pode ser adicionada em TASK-007 se necessário.

### Patch 4 — maybe_single() em todas as leituras de ownership

`.single()` lança exceção se não encontrar registro. Usar `.maybe_single()` em todas as queries de ownership. Se `result.data` for `None` → `HTTPException(status_code=404)`.

```python
result = db.table("extracted_facts").select("*").eq("id", fact_id).maybe_single().execute()
if not result.data:
    raise HTTPException(status_code=404, detail="extracted_fact_not_found")
```

### Patch 5 — require_review_role: build sobre require_workspace_member

`require_workspace_member` já existe em `dependencies.py` (TASK-003). Adicionar no mesmo arquivo:

```python
REVIEW_ALLOWED_ROLES: frozenset[str] = frozenset({"reviewer", "manager", "owner"})

async def require_review_role(
    membership: dict = Depends(require_workspace_member),
) -> dict:
    if membership["role"] not in REVIEW_ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "insufficient_role",
                "required": sorted(REVIEW_ALLOWED_ROLES),
                "current": membership["role"],
            },
        )
    return membership
```

### Patch 6 — unknown_queue: status conforme DDL 011

O DDL real (`011_unknown_queue.sql`) define:

```sql
check (status in ('open', 'mapped', 'ignored', 'schema_requested', 'resolved'))
```

Mapeamento correto:
- Reclassify → `status = 'mapped'`
- Ignore → `status = 'ignored'`

Colunas existentes para resolução:
- `resolution text` — armazenar JSON: `'{"fact_type": "...", "destination": "...", "extraction_job_id": "..."}'`
- `resolved_by uuid FK auth.users`
- `resolved_at timestamptz`

**Não usar** `reclassified_as`, `reclassified_by`, `reclassified_at` (não existem no DDL).

### Patch 7 — unknown_queue: sem migration de colunas novas

As colunas `resolution`, `resolved_by`, `resolved_at` já existem no DDL 011. Nenhuma migration adicional é necessária para reclassify/ignore. A TASK-005 usou `metadata jsonb` para contexto interno do worker — esse campo também já existe no DDL da `processing_jobs`, não no `unknown_facts_queue`.

**A migration 028 abrange apenas as novas funções PL/pgSQL** de review (Patch 3).

### Patch 8 — edit_rule: validação Pydantic obrigatória

Para regras, o Pydantic valida o dict completo:

```python
# discount_rule: modelo tem {condition: DiscountConditionModel, action: DiscountActionModel}
validate_extraction("discount_rule", {"condition": new_condition, "action": new_action})

# cancellation_policy: modelo tem campos flat (notice_required_hours, penalty_*)
# → merge condition+action em dict flat antes de validar
validate_extraction("cancellation_policy", {**new_condition, **new_action})
```

Adicionar helper `_validate_rule_edit(rule_type, condition, action) → ValidationResult` no `review_service.py` que faz o dispatch correto por `rule_type`.

Se validação falhar → `422` com erros Pydantic. **O RPC não é chamado se Pydantic falhar.**

### Patch 9 — ActionResponse: resource_id genérico

`ActionResponse` deve ser agnóstico de tipo:

```python
class ActionResponse(BaseModel):
    status: str                   # "approved" | "rejected" | "superseded"
    resource_id: UUID             # fact_id, rule_id, ou new_fact_id (pós-edit)
    resource_type: str            # "extracted_fact" | "business_rule"
    # validation_event_id omitido: o RPC insere internamente, sem retornar o id
```

Para **edit** (que retorna novo id):
```json
{"status": "superseded", "resource_id": "<new_fact_id>", "resource_type": "extracted_fact"}
```

Para **approve**:
```json
{"status": "approved", "resource_id": "<fact_id>", "resource_type": "extracted_fact"}
```

### Patch 11 — Unknown queue: audit trail via RPCs atômicos

Reclassify e ignore são **decisões humanas críticas** — sem `validation_events`, todo o histórico de curadoria da unknown queue se perde. Isso cria um "buraco negro" exatamente onde mais decisão humana acontece.

**Solução:** adicionar ao `028_review_functions.sql` dois RPCs:

- `reclassify_unknown_item(item_id, fact_type, destination, chunk_id, source_id, reason)` → retorna `job_id uuid`
  - UPDATE `unknown_facts_queue` status → `'mapped'`
  - INSERT `processing_jobs` (cria o job de extração **dentro da transação**)
  - INSERT `validation_events` com `action='manual_created'`

- `ignore_unknown_item(item_id, reason)` → void
  - UPDATE `unknown_facts_queue` status → `'ignored'`
  - INSERT `validation_events` com `action='rejected'`

O Python não insere `validation_events` diretamente para essas ações — o RPC faz tudo atomicamente.

### Patch 12 — Eliminar risco de job órfão: job criado dentro do RPC

O fluxo anterior tinha risco de inconsistência:
```
enqueue_extraction_job() → INSERT processing_jobs  ← pode cometer
db.update(unknown_queue)                            ← pode falhar após commit anterior
```

Solução: o `reclassify_unknown_item` RPC cria o `processing_job` **dentro da mesma transação** que atualiza o `unknown_facts_queue`. O Python só chama `dispatch_extraction_job(job_id)` **após** o RPC retornar com sucesso.

```python
# Correto (outbox via RPC):
rpc_result = db.rpc("reclassify_unknown_item", {...}).execute()
job_id = rpc_result.data           # job criado atomicamente no RPC
dispatch_extraction_job(job_id)    # dispatch após commit — pode falhar; job fica queued para re-dispatch
```

Se o dispatch falhar: o item está `mapped`, o job está `queued` no DB, o `validation_event` existe. O scheduler periódico re-enfileira jobs `queued`. Zero estado inconsistente.

### Patch 10 — dispatch_extraction_job: contrato confirmado (TASK-005)

`dispatch_extraction_job(job_id)` existe em `workers/classification/src/worker_classification/extraction_queue.py` (implementado na TASK-005). O import em `unknown_service.py` é:

```python
from worker_classification.extraction_queue import (
    enqueue_extraction_job,
    dispatch_extraction_job,
)
```

Para reclassify na unknown queue, o `confidence` passa como `0.5` (iniciado por humano, não pelo classificador). O `dispatch_extraction_job` é chamado **após** o `UPDATE` no `unknown_facts_queue` para garantir que o estado persiste antes do enqueue.

---

## Arquivos a criar ou modificar

```
apps/api/
  src/context_builder/
    routers/
      review.py              ← NOVO
      unknown.py             ← NOVO
    schemas/
      review.py              ← NOVO
    services/
      review_service.py      ← NOVO
      unknown_service.py     ← NOVO
    dependencies.py          ← MODIFICAR: +require_review_role

supabase/migrations/
  028_review_functions.sql   ← NOVO: RPCs atômicos de revisão

tests/api/
  test_review.py             ← NOVO
  test_unknown.py            ← NOVO
```

---

## `supabase/migrations/028_review_functions.sql`

```sql
-- ─────────────────────────────────────────────────────────────────
-- Reclassify unknown item
-- Atômico: UPDATE unknown_queue + INSERT processing_jobs + validation_event
-- Retorna o job_id para o Python chamar dispatch depois
-- ─────────────────────────────────────────────────────────────────
create or replace function public.reclassify_unknown_item(
  p_item_id     uuid,
  p_fact_type   text,
  p_destination text,
  p_chunk_id    uuid,
  p_source_id   uuid,
  p_confidence  numeric  default 0.5,
  p_reason      text     default null
)
returns uuid    -- job_id
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row   public.unknown_facts_queue%rowtype;
  v_job_id uuid;
  v_resolution jsonb;
begin
  select * into v_row
  from public.unknown_facts_queue
  where id = p_item_id
  for update;

  if not found then
    raise exception 'unknown_item_not_found';
  end if;

  if not public.has_workspace_role(v_row.workspace_id, array['owner','manager','reviewer']::workspace_role[]) then
    raise exception 'permission_denied';
  end if;

  if v_row.status = 'mapped' then
    raise exception 'already_mapped';
  end if;
  if v_row.status = 'ignored' then
    raise exception 'already_ignored';
  end if;

  -- Criar processing_job atomicamente (outbox: job nasce queued dentro da transação)
  insert into public.processing_jobs (
    workspace_id, source_id, chunk_id,
    job_type, status,
    metadata
  )
  values (
    v_row.workspace_id, p_source_id, p_chunk_id,
    'extraction', 'queued',
    jsonb_build_object(
      'fact_type',                   p_fact_type,
      'destination',                 p_destination,
      'classification_confidence',   p_confidence,
      'classification_prompt_version', 'manual_reclassify',
      'classification_model',        'human'
    )
  )
  returning id into v_job_id;

  -- Resolução armazenada no item
  v_resolution := jsonb_build_object(
    'fact_type',          p_fact_type,
    'destination',        p_destination,
    'extraction_job_id',  v_job_id
  );

  update public.unknown_facts_queue
  set status      = 'mapped',
      resolution  = v_resolution::text,
      resolved_by = auth.uid(),
      resolved_at = now()
  where id = p_item_id;

  insert into public.validation_events (
    workspace_id, actor_user_id, action,
    target_type, target_id,
    previous_status, new_status,
    previous_value, new_value, reason,
    metadata
  ) values (
    v_row.workspace_id, auth.uid(), 'manual_created',
    'unknown_item', p_item_id,
    v_row.status, 'mapped',
    jsonb_build_object('suggested_fact_type', v_row.suggested_fact_type),
    v_resolution,
    p_reason,
    jsonb_build_object('extraction_job_id', v_job_id, 'fact_type', p_fact_type)
  );

  return v_job_id;
end;
$$;


-- ─────────────────────────────────────────────────────────────────
-- Ignore unknown item
-- Atômico: UPDATE unknown_queue + validation_event
-- ─────────────────────────────────────────────────────────────────
create or replace function public.ignore_unknown_item(
  p_item_id uuid,
  p_reason  text default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.unknown_facts_queue%rowtype;
begin
  select * into v_row
  from public.unknown_facts_queue
  where id = p_item_id
  for update;

  if not found then
    raise exception 'unknown_item_not_found';
  end if;

  if not public.has_workspace_role(v_row.workspace_id, array['owner','manager','reviewer']::workspace_role[]) then
    raise exception 'permission_denied';
  end if;

  -- idempotente
  if v_row.status = 'ignored' then
    return;
  end if;

  if v_row.status = 'mapped' then
    raise exception 'already_mapped';
  end if;

  update public.unknown_facts_queue
  set status      = 'ignored',
      resolved_by = auth.uid(),
      resolved_at = now()
  where id = p_item_id;

  insert into public.validation_events (
    workspace_id, actor_user_id, action,
    target_type, target_id,
    previous_status, new_status,
    previous_value, new_value, reason
  ) values (
    v_row.workspace_id, auth.uid(), 'rejected',
    'unknown_item', p_item_id,
    v_row.status, 'ignored',
    jsonb_build_object('suggested_fact_type', v_row.suggested_fact_type),
    null,
    p_reason
  );
end;
$$;


-- ─────────────────────────────────────────────────────────────────
-- Reject fact (atômico: status transition + validation_event)
-- ─────────────────────────────────────────────────────────────────
create or replace function public.reject_fact(
  target_fact_id uuid,
  reason         text default null
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.extracted_facts%rowtype;
begin
  select * into v_row
  from public.extracted_facts
  where id = target_fact_id
  for update;

  if not found then
    raise exception 'fact_not_found';
  end if;

  if not public.has_workspace_role(v_row.workspace_id, array['owner','manager','reviewer']::workspace_role[]) then
    raise exception 'permission_denied';
  end if;

  -- idempotente: já rejected → ok
  if v_row.status = 'rejected' then
    return target_fact_id;
  end if;

  if v_row.status in ('published', 'deprecated', 'superseded') then
    raise exception 'invalid_fact_status_for_rejection: %', v_row.status;
  end if;

  update public.extracted_facts
  set status = 'rejected',
      reviewed_by = auth.uid(),
      reviewed_at = now()
  where id = target_fact_id;

  insert into public.validation_events (
    workspace_id, actor_user_id, action,
    target_type, target_id,
    previous_status, new_status,
    previous_value, new_value, reason
  ) values (
    v_row.workspace_id, auth.uid(), 'rejected',
    'extracted_fact', target_fact_id,
    v_row.status::text, 'rejected',
    v_row.content, null, reason
  );

  return target_fact_id;
end;
$$;


-- ─────────────────────────────────────────────────────────────────
-- Reject rule
-- ─────────────────────────────────────────────────────────────────
create or replace function public.reject_rule(
  target_rule_id uuid,
  reason         text default null
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.business_rules%rowtype;
begin
  select * into v_row
  from public.business_rules
  where id = target_rule_id
  for update;

  if not found then
    raise exception 'rule_not_found';
  end if;

  if not public.has_workspace_role(v_row.workspace_id, array['owner','manager','reviewer']::workspace_role[]) then
    raise exception 'permission_denied';
  end if;

  if v_row.status = 'rejected' then
    return target_rule_id;
  end if;

  if v_row.status in ('published', 'deprecated', 'superseded') then
    raise exception 'invalid_rule_status_for_rejection: %', v_row.status;
  end if;

  update public.business_rules
  set status = 'rejected',
      reviewed_by = auth.uid(),
      reviewed_at = now()
  where id = target_rule_id;

  insert into public.validation_events (
    workspace_id, actor_user_id, action,
    target_type, target_id,
    previous_status, new_status,
    previous_value, new_value, reason
  ) values (
    v_row.workspace_id, auth.uid(), 'rejected',
    'business_rule', target_rule_id,
    v_row.status::text, 'rejected',
    jsonb_build_object('condition', v_row.condition, 'action', v_row.action),
    null, reason
  );

  return target_rule_id;
end;
$$;


-- ─────────────────────────────────────────────────────────────────
-- Create fact version (edit — nova versão, não edição in-place)
-- Python insere conteúdo já validado via Pydantic.
-- ─────────────────────────────────────────────────────────────────
create or replace function public.create_fact_version(
  old_fact_id              uuid,
  new_content              jsonb,
  new_normalized_content   jsonb,
  reason                   text default null
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  old_row      public.extracted_facts%rowtype;
  new_fact_id  uuid;
begin
  select * into old_row
  from public.extracted_facts
  where id = old_fact_id
  for update;

  if not found then
    raise exception 'fact_not_found';
  end if;

  if not public.has_workspace_role(old_row.workspace_id, array['owner','manager','reviewer']::workspace_role[]) then
    raise exception 'permission_denied';
  end if;

  if old_row.superseded_by is not null then
    raise exception 'fact_already_superseded: %', old_row.superseded_by;
  end if;

  if old_row.status in ('published', 'deprecated') then
    raise exception 'invalid_fact_status_for_versioning: %', old_row.status;
  end if;

  -- Inserir nova versão
  insert into public.extracted_facts (
    workspace_id, source_id, chunk_id, evidence_span_id,
    fact_type, schema_version,
    content, normalized_content,
    status,
    confidence, model_name, model_provider, prompt_version, extraction_run_id,
    supersedes,
    created_by, reviewed_by, reviewed_at
  )
  values (
    old_row.workspace_id, old_row.source_id, old_row.chunk_id, old_row.evidence_span_id,
    old_row.fact_type, old_row.schema_version,
    new_content, new_normalized_content,
    'approved',
    old_row.confidence, old_row.model_name, old_row.model_provider,
    old_row.prompt_version, old_row.extraction_run_id,
    old_fact_id,
    auth.uid(), auth.uid(), now()
  )
  returning id into new_fact_id;

  -- Marcar original como superseded
  update public.extracted_facts
  set status = 'superseded',
      superseded_by = new_fact_id
  where id = old_fact_id;

  insert into public.validation_events (
    workspace_id, actor_user_id, action,
    target_type, target_id,
    previous_status, new_status,
    previous_value, new_value, reason,
    metadata
  ) values (
    old_row.workspace_id, auth.uid(), 'edited',
    'extracted_fact', old_fact_id,
    old_row.status::text, 'superseded',
    old_row.content, new_content, reason,
    jsonb_build_object('new_fact_id', new_fact_id)
  );

  return new_fact_id;
end;
$$;


-- ─────────────────────────────────────────────────────────────────
-- Create rule version (edit — nova versão, não edição in-place)
-- ─────────────────────────────────────────────────────────────────
create or replace function public.create_rule_version(
  old_rule_id    uuid,
  new_condition  jsonb,
  new_action     jsonb,
  reason         text default null
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  old_row      public.business_rules%rowtype;
  new_rule_id  uuid;
begin
  select * into old_row
  from public.business_rules
  where id = old_rule_id
  for update;

  if not found then
    raise exception 'rule_not_found';
  end if;

  if not public.has_workspace_role(old_row.workspace_id, array['owner','manager','reviewer']::workspace_role[]) then
    raise exception 'permission_denied';
  end if;

  if old_row.superseded_by is not null then
    raise exception 'rule_already_superseded: %', old_row.superseded_by;
  end if;

  if old_row.status in ('published', 'deprecated') then
    raise exception 'invalid_rule_status_for_versioning: %', old_row.status;
  end if;

  -- Inserir nova versão
  insert into public.business_rules (
    workspace_id, source_id, chunk_id, evidence_span_id,
    rule_type, schema_version,
    condition, action,
    status, priority,
    confidence, model_name, model_provider, prompt_version, extraction_run_id,
    supersedes,
    created_by, reviewed_by, reviewed_at
  )
  values (
    old_row.workspace_id, old_row.source_id, old_row.chunk_id, old_row.evidence_span_id,
    old_row.rule_type, old_row.schema_version,
    new_condition, new_action,
    'approved', old_row.priority,
    old_row.confidence, old_row.model_name, old_row.model_provider,
    old_row.prompt_version, old_row.extraction_run_id,
    old_rule_id,
    auth.uid(), auth.uid(), now()
  )
  returning id into new_rule_id;

  update public.business_rules
  set status = 'superseded',
      superseded_by = new_rule_id
  where id = old_rule_id;

  insert into public.validation_events (
    workspace_id, actor_user_id, action,
    target_type, target_id,
    previous_status, new_status,
    previous_value, new_value, reason,
    metadata
  ) values (
    old_row.workspace_id, auth.uid(), 'edited',
    'business_rule', old_rule_id,
    old_row.status::text, 'superseded',
    jsonb_build_object('condition', old_row.condition, 'action', old_row.action),
    jsonb_build_object('condition', new_condition, 'action', new_action),
    reason,
    jsonb_build_object('new_rule_id', new_rule_id)
  );

  return new_rule_id;
end;
$$;
```

---

## `dependencies.py` — adição

Adicionar ao arquivo existente (após `require_upload_permission` da TASK-003):

```python
REVIEW_ALLOWED_ROLES: frozenset[str] = frozenset({"reviewer", "manager", "owner"})


async def require_review_role(
    membership: dict = Depends(require_workspace_member),
) -> dict:
    """
    Verifica que o membro tem role para revisar fatos.
    reviewer, manager e owner podem revisar. staff não pode.
    Construído sobre require_workspace_member (TASK-003).
    """
    if membership["role"] not in REVIEW_ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "insufficient_role",
                "required": sorted(REVIEW_ALLOWED_ROLES),
                "current": membership["role"],
            },
        )
    return membership
```

---

## `schemas/review.py`

```python
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ── Requests ────────────────────────────────────────────────────────────────

class ApproveRequest(BaseModel):
    note: str | None = None


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=1)
    note: str | None = None


class EditFactRequest(BaseModel):
    content: dict[str, Any] = Field(...)
    note: str | None = None


class EditRuleRequest(BaseModel):
    condition: dict[str, Any] = Field(...)
    action: dict[str, Any] = Field(...)
    note: str | None = None


class ReclassifyRequest(BaseModel):
    fact_type: str = Field(...)
    destination: str = Field(...)    # "extracted_facts" | "business_rules"
    note: str | None = None


class IgnoreRequest(BaseModel):
    note: str | None = None


# ── Responses ────────────────────────────────────────────────────────────────

class EvidenceSpanResponse(BaseModel):
    id: UUID
    quote: str
    char_start: int | None
    char_end: int | None
    page_number: int | None
    sheet_name: str | None
    row_number: int | None


class ExtractedFactResponse(BaseModel):
    id: UUID
    fact_type: str
    schema_version: str
    content: dict[str, Any]
    normalized_content: dict[str, Any]
    status: str
    confidence: float | None
    model_name: str | None
    prompt_version: str | None
    evidence_span: EvidenceSpanResponse | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    supersedes: UUID | None
    superseded_by: UUID | None
    created_at: datetime


class BusinessRuleResponse(BaseModel):
    id: UUID
    rule_type: str
    schema_version: str
    condition: dict[str, Any]
    action: dict[str, Any]
    status: str
    confidence: float | None
    model_name: str | None
    prompt_version: str | None
    evidence_span: EvidenceSpanResponse | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    supersedes: UUID | None
    superseded_by: UUID | None
    created_at: datetime


class ChunkReviewItem(BaseModel):
    """Item na fila de revisão — chunk com resumo de pendências."""
    chunk_id: UUID
    source_id: UUID
    source_name: str
    chunk_index: int
    content_preview: str          # primeiros 200 chars do chunk
    facts_total: int
    facts_pending: int            # status IN ('extracted', 'needs_review')
    rules_total: int
    rules_pending: int
    unknown_total: int
    has_ambiguities: bool         # se algum fato tem ambiguities não vazias
    created_at: datetime


class ChunkDetailResponse(BaseModel):
    """Detalhe completo de um chunk para a tela de revisão."""
    chunk_id: UUID
    source_id: UUID
    source_name: str
    chunk_index: int
    content: str
    facts: list[ExtractedFactResponse]
    rules: list[BusinessRuleResponse]


class ReviewQueueResponse(BaseModel):
    items: list[ChunkReviewItem]
    total: int
    page: int
    per_page: int
    pages: int


class ActionResponse(BaseModel):
    """
    Resposta genérica para approve / reject / edit.
    resource_id é o ID do recurso afetado (ou do novo recurso em caso de edit).
    """
    status: str            # "approved" | "rejected" | "superseded"
    resource_id: UUID
    resource_type: str     # "extracted_fact" | "business_rule"


class UnknownQueueItem(BaseModel):
    id: UUID
    chunk_id: UUID
    source_id: UUID
    raw_text: str
    suggested_fact_type: str | None
    confidence: float | None
    status: str                   # "open" | "mapped" | "ignored" | "schema_requested" | "resolved"
    resolution: str | None        # JSON string com fact_type + job_id (para mapped)
    resolved_by: UUID | None
    resolved_at: datetime | None
    created_at: datetime


class UnknownQueueResponse(BaseModel):
    items: list[UnknownQueueItem]
    total: int
    page: int
    per_page: int
    pages: int


class ReclassifyResponse(BaseModel):
    status: str                   # "mapped"
    extraction_job_id: str


class IgnoreResponse(BaseModel):
    status: str                   # "ignored"
```

---

## `services/review_service.py`

```python
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException
from supabase import Client

from normalizers.pre_extract import pre_normalize
from schema_registry.validators import validate_extraction

logger = logging.getLogger("review_service")

_RULE_TYPES = frozenset({"discount_rule", "cancellation_policy"})
_FACT_TYPES = frozenset({
    "service_price", "business_hours", "payment_method",
    "contact_info", "faq_item",
})


def _rpc_exception_to_http(exc: Exception) -> HTTPException:
    """
    Converte exceptions do RPC Postgres em HTTPException.
    Os RPCs levantam texto com padrão 'code: detail'.
    """
    msg = str(exc)
    if "not_found" in msg:
        return HTTPException(status_code=404, detail=msg.split(":")[-1].strip())
    if "permission_denied" in msg:
        return HTTPException(status_code=403, detail="permission_denied")
    if "already_superseded" in msg:
        return HTTPException(status_code=409, detail={"code": "already_superseded"})
    if "invalid_" in msg:
        return HTTPException(status_code=409, detail={"code": "invalid_transition", "detail": msg})
    return HTTPException(status_code=500, detail="rpc_error")


def _validate_rule_edit(
    rule_type: str,
    condition: dict[str, Any],
    action: dict[str, Any],
) -> None:
    """
    Valida condição e ação editadas pelo revisor contra o schema Pydantic.
    discount_rule: modelo tem condition e action como nested objects.
    cancellation_policy: modelo tem campos flat — merge condition+action.
    """
    if rule_type == "discount_rule":
        raw = {"condition": condition, "action": action}
    elif rule_type == "cancellation_policy":
        raw = {**condition, **action}
    else:
        # fact_types que vão para extracted_facts, não business_rules
        # não deveriam chegar aqui, mas proteger
        raw = {**condition, **action}

    vr = validate_extraction(rule_type, raw)
    if not vr.valid:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "rule_type": rule_type, "errors": vr.errors[:5]},
        )


# ── Review queue ─────────────────────────────────────────────────────────────

def get_review_queue(
    db: Client,
    *,
    workspace_id: str,
    page: int,
    per_page: int,
    fact_type: str | None = None,
    source_id: str | None = None,
) -> dict:
    """
    Lista chunks com fatos/regras pendentes de revisão (status extracted ou needs_review).
    Um chunk aparece se tem ao menos um pendente.
    """
    raise NotImplementedError("get_review_queue: implementar query via supabase")


def get_chunk_detail(
    db: Client,
    *,
    workspace_id: str,
    chunk_id: str,
) -> dict:
    """
    Retorna chunk completo com facts, rules e evidence_spans.
    Inclui superseded para histórico de versões.
    Verifica ownership via workspace_id.
    """
    raise NotImplementedError("get_chunk_detail: implementar query via supabase")


# ── Approve ──────────────────────────────────────────────────────────────────

def approve_fact(
    db: Client,
    *,
    workspace_id: str,
    fact_id: str,
    note: str | None,
) -> dict:
    """
    Delega ao RPC approve_fact (022_publish_functions.sql).
    Idempotente: se já approved, retorna sem chamar o RPC.
    """
    # Leitura para ownership check e idempotência
    result = (
        db.table("extracted_facts")
        .select("id, workspace_id, status")
        .eq("id", fact_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="extracted_fact_not_found")
    fact = result.data
    if fact["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="extracted_fact_not_found")

    # Idempotência: já aprovado → retornar sem criar evento duplicado
    if fact["status"] == "approved":
        return {"status": "approved", "resource_id": fact_id, "resource_type": "extracted_fact"}

    try:
        db.rpc("approve_fact", {"target_fact_id": fact_id, "reason": note}).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    logger.info("fact_approved fact_id=%s workspace_id=%s", fact_id, workspace_id)
    return {"status": "approved", "resource_id": fact_id, "resource_type": "extracted_fact"}


def approve_rule(
    db: Client,
    *,
    workspace_id: str,
    rule_id: str,
    note: str | None,
) -> dict:
    """
    Delega ao RPC approve_rule (022_publish_functions.sql).
    Idempotente: se já approved, retorna sem chamar o RPC.
    """
    result = (
        db.table("business_rules")
        .select("id, workspace_id, status")
        .eq("id", rule_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="business_rule_not_found")
    rule = result.data
    if rule["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="business_rule_not_found")

    if rule["status"] == "approved":
        return {"status": "approved", "resource_id": rule_id, "resource_type": "business_rule"}

    try:
        db.rpc("approve_rule", {"target_rule_id": rule_id, "reason": note}).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    logger.info("rule_approved rule_id=%s workspace_id=%s", rule_id, workspace_id)
    return {"status": "approved", "resource_id": rule_id, "resource_type": "business_rule"}


# ── Reject ───────────────────────────────────────────────────────────────────

def reject_fact(
    db: Client,
    *,
    workspace_id: str,
    fact_id: str,
    reason: str,
    note: str | None,
) -> dict:
    """Delega ao RPC reject_fact (028_review_functions.sql)."""
    result = (
        db.table("extracted_facts")
        .select("id, workspace_id, status")
        .eq("id", fact_id)
        .maybe_single()
        .execute()
    )
    if not result.data or result.data["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="extracted_fact_not_found")

    combined_reason = f"{reason}" + (f" | {note}" if note else "")
    try:
        db.rpc("reject_fact", {"target_fact_id": fact_id, "reason": combined_reason}).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    logger.info("fact_rejected fact_id=%s workspace_id=%s", fact_id, workspace_id)
    return {"status": "rejected", "resource_id": fact_id, "resource_type": "extracted_fact"}


def reject_rule(
    db: Client,
    *,
    workspace_id: str,
    rule_id: str,
    reason: str,
    note: str | None,
) -> dict:
    """Delega ao RPC reject_rule (028_review_functions.sql)."""
    result = (
        db.table("business_rules")
        .select("id, workspace_id, status")
        .eq("id", rule_id)
        .maybe_single()
        .execute()
    )
    if not result.data or result.data["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="business_rule_not_found")

    combined_reason = f"{reason}" + (f" | {note}" if note else "")
    try:
        db.rpc("reject_rule", {"target_rule_id": rule_id, "reason": combined_reason}).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    logger.info("rule_rejected rule_id=%s workspace_id=%s", rule_id, workspace_id)
    return {"status": "rejected", "resource_id": rule_id, "resource_type": "business_rule"}


# ── Edit (nova versão) ────────────────────────────────────────────────────────

def edit_fact(
    db: Client,
    *,
    workspace_id: str,
    fact_id: str,
    new_content: dict[str, Any],
    note: str | None,
) -> dict:
    """
    Pré-normaliza e valida new_content antes de chamar RPC create_fact_version.
    O RPC cria a nova versão e supersede o original atomicamente.
    """
    result = (
        db.table("extracted_facts")
        .select("id, workspace_id, fact_type")
        .eq("id", fact_id)
        .maybe_single()
        .execute()
    )
    if not result.data or result.data["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="extracted_fact_not_found")

    fact_type = result.data["fact_type"]
    normalized = pre_normalize(fact_type, new_content)
    vr = validate_extraction(fact_type, normalized)
    if not vr.valid:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "fact_type": fact_type, "errors": vr.errors[:5]},
        )

    try:
        rpc_result = db.rpc("create_fact_version", {
            "old_fact_id": fact_id,
            "new_content": new_content,
            "new_normalized_content": normalized,
            "reason": note,
        }).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    new_fact_id = str(rpc_result.data)
    logger.info(
        "fact_versioned old=%s new=%s workspace=%s", fact_id, new_fact_id, workspace_id,
    )
    return {"status": "superseded", "resource_id": new_fact_id, "resource_type": "extracted_fact"}


def edit_rule(
    db: Client,
    *,
    workspace_id: str,
    rule_id: str,
    new_condition: dict[str, Any],
    new_action: dict[str, Any],
    note: str | None,
) -> dict:
    """
    Valida condition+action antes de chamar RPC create_rule_version.
    O RPC cria a nova versão e supersede o original atomicamente.
    """
    result = (
        db.table("business_rules")
        .select("id, workspace_id, rule_type")
        .eq("id", rule_id)
        .maybe_single()
        .execute()
    )
    if not result.data or result.data["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="business_rule_not_found")

    rule_type = result.data["rule_type"]
    _validate_rule_edit(rule_type, new_condition, new_action)

    try:
        rpc_result = db.rpc("create_rule_version", {
            "old_rule_id": rule_id,
            "new_condition": new_condition,
            "new_action": new_action,
            "reason": note,
        }).execute()
    except Exception as exc:
        raise _rpc_exception_to_http(exc) from exc

    new_rule_id = str(rpc_result.data)
    logger.info(
        "rule_versioned old=%s new=%s workspace=%s", rule_id, new_rule_id, workspace_id,
    )
    return {"status": "superseded", "resource_id": new_rule_id, "resource_type": "business_rule"}
```

---

## `services/unknown_service.py`

```python
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from supabase import Client

logger = logging.getLogger("unknown_service")

_MVP_FACT_TYPES = frozenset({
    "service_price", "business_hours", "payment_method",
    "contact_info", "faq_item", "discount_rule", "cancellation_policy",
})
_DESTINATIONS = frozenset({"extracted_facts", "business_rules"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_unknown_queue(
    db: Client,
    *,
    workspace_id: str,
    page: int,
    per_page: int,
    status_filter: str | None = None,
) -> dict:
    raise NotImplementedError("get_unknown_queue: implementar query via supabase")


def _rpc_unknown_exception_to_http(exc: Exception) -> HTTPException:
    msg = str(exc)
    if "not_found" in msg:
        return HTTPException(status_code=404, detail="unknown_item_not_found")
    if "permission_denied" in msg:
        return HTTPException(status_code=403, detail="permission_denied")
    if "already_mapped" in msg:
        return HTTPException(status_code=409, detail={"code": "already_mapped"})
    if "already_ignored" in msg:
        return HTTPException(status_code=409, detail={"code": "already_ignored"})
    return HTTPException(status_code=500, detail="rpc_error")


def reclassify_unknown(
    db: Client,
    *,
    workspace_id: str,
    item_id: str,
    fact_type: str,
    destination: str,
    reviewer_id: str,
    note: str | None,
) -> dict:
    """
    Delega ao RPC reclassify_unknown_item (028_review_functions.sql).
    O RPC cria o processing_job + atualiza o item + insere validation_event atomicamente.
    Python só despacha o job para o Celery após o RPC confirmar.

    Se dispatch falhar: job permanece queued no DB, item está mapped, evento existe.
    O scheduler re-enfileira jobs queued — zero inconsistência.
    """
    if fact_type not in _MVP_FACT_TYPES:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_fact_type", "valid": sorted(_MVP_FACT_TYPES)},
        )
    if destination not in _DESTINATIONS:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_destination", "valid": sorted(_DESTINATIONS)},
        )

    # Leitura mínima para ownership check — o RPC também verifica, mas 404 antes é UX melhor
    result = (
        db.table("unknown_facts_queue")
        .select("id, workspace_id, chunk_id, source_id")
        .eq("id", item_id)
        .maybe_single()
        .execute()
    )
    if not result.data or result.data.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="unknown_item_not_found")

    item = result.data

    # RPC: atômico — UPDATE + INSERT processing_jobs + INSERT validation_event
    try:
        rpc_result = db.rpc("reclassify_unknown_item", {
            "p_item_id":     item_id,
            "p_fact_type":   fact_type,
            "p_destination": destination,
            "p_chunk_id":    item["chunk_id"],
            "p_source_id":   item["source_id"],
            "p_confidence":  0.5,
            "p_reason":      note,
        }).execute()
    except Exception as exc:
        raise _rpc_unknown_exception_to_http(exc) from exc

    job_id = str(rpc_result.data)

    # Dispatch APÓS o RPC confirmar (job está queued no DB)
    from worker_classification.extraction_queue import dispatch_extraction_job
    dispatch_extraction_job(job_id)

    logger.info(
        "unknown_reclassified item_id=%s fact_type=%s job_id=%s",
        item_id, fact_type, job_id,
    )
    return {"status": "mapped", "extraction_job_id": job_id}


def ignore_unknown(
    db: Client,
    *,
    workspace_id: str,
    item_id: str,
    reviewer_id: str,
    note: str | None,
) -> dict:
    """
    Delega ao RPC ignore_unknown_item (028_review_functions.sql).
    O RPC atualiza o item + insere validation_event atomicamente.
    Idempotente: já ignored → RPC retorna sem erro.
    """
    # Ownership check antes do RPC
    result = (
        db.table("unknown_facts_queue")
        .select("id, workspace_id")
        .eq("id", item_id)
        .maybe_single()
        .execute()
    )
    if not result.data or result.data.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="unknown_item_not_found")

    try:
        db.rpc("ignore_unknown_item", {
            "p_item_id": item_id,
            "p_reason":  note,
        }).execute()
    except Exception as exc:
        raise _rpc_unknown_exception_to_http(exc) from exc

    logger.info("unknown_ignored item_id=%s workspace_id=%s", item_id, workspace_id)
    return {"status": "ignored"}
```

---

## `routers/review.py`

```python
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from supabase import Client

from ..dependencies import (
    get_current_user,
    get_supabase_service,
    require_review_role,
)
from ..schemas.review import (
    ActionResponse,
    ApproveRequest,
    ChunkDetailResponse,
    EditFactRequest,
    EditRuleRequest,
    RejectRequest,
    ReviewQueueResponse,
)
from ..services import review_service

router = APIRouter()


@router.get("", response_model=ReviewQueueResponse)
async def list_review_queue(
    workspace_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    fact_type: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    membership: dict = Depends(require_review_role),
    db: Client = Depends(get_supabase_service),
) -> ReviewQueueResponse:
    result = review_service.get_review_queue(
        db,
        workspace_id=workspace_id,
        page=page, per_page=per_page,
        fact_type=fact_type, source_id=source_id,
    )
    return ReviewQueueResponse(**result)


@router.get("/{chunk_id}", response_model=ChunkDetailResponse)
async def get_chunk_detail(
    workspace_id: str,
    chunk_id: UUID,
    membership: dict = Depends(require_review_role),
    db: Client = Depends(get_supabase_service),
) -> ChunkDetailResponse:
    result = review_service.get_chunk_detail(
        db, workspace_id=workspace_id, chunk_id=str(chunk_id),
    )
    return ChunkDetailResponse(**result)


@router.post("/facts/{fact_id}/approve", response_model=ActionResponse)
async def approve_fact(
    workspace_id: str,
    fact_id: UUID,
    body: ApproveRequest,
    membership: dict = Depends(require_review_role),
    db: Client = Depends(get_supabase_service),
) -> ActionResponse:
    result = review_service.approve_fact(
        db, workspace_id=workspace_id, fact_id=str(fact_id), note=body.note,
    )
    return ActionResponse(**result)


@router.post("/facts/{fact_id}/reject", response_model=ActionResponse)
async def reject_fact(
    workspace_id: str,
    fact_id: UUID,
    body: RejectRequest,
    membership: dict = Depends(require_review_role),
    db: Client = Depends(get_supabase_service),
) -> ActionResponse:
    result = review_service.reject_fact(
        db, workspace_id=workspace_id, fact_id=str(fact_id),
        reason=body.reason, note=body.note,
    )
    return ActionResponse(**result)


@router.post("/facts/{fact_id}/edit", response_model=ActionResponse)
async def edit_fact(
    workspace_id: str,
    fact_id: UUID,
    body: EditFactRequest,
    membership: dict = Depends(require_review_role),
    db: Client = Depends(get_supabase_service),
) -> ActionResponse:
    result = review_service.edit_fact(
        db, workspace_id=workspace_id, fact_id=str(fact_id),
        new_content=body.content, note=body.note,
    )
    return ActionResponse(**result)


@router.post("/rules/{rule_id}/approve", response_model=ActionResponse)
async def approve_rule(
    workspace_id: str,
    rule_id: UUID,
    body: ApproveRequest,
    membership: dict = Depends(require_review_role),
    db: Client = Depends(get_supabase_service),
) -> ActionResponse:
    result = review_service.approve_rule(
        db, workspace_id=workspace_id, rule_id=str(rule_id), note=body.note,
    )
    return ActionResponse(**result)


@router.post("/rules/{rule_id}/reject", response_model=ActionResponse)
async def reject_rule(
    workspace_id: str,
    rule_id: UUID,
    body: RejectRequest,
    membership: dict = Depends(require_review_role),
    db: Client = Depends(get_supabase_service),
) -> ActionResponse:
    result = review_service.reject_rule(
        db, workspace_id=workspace_id, rule_id=str(rule_id),
        reason=body.reason, note=body.note,
    )
    return ActionResponse(**result)


@router.post("/rules/{rule_id}/edit", response_model=ActionResponse)
async def edit_rule(
    workspace_id: str,
    rule_id: UUID,
    body: EditRuleRequest,
    membership: dict = Depends(require_review_role),
    db: Client = Depends(get_supabase_service),
) -> ActionResponse:
    result = review_service.edit_rule(
        db, workspace_id=workspace_id, rule_id=str(rule_id),
        new_condition=body.condition, new_action=body.action, note=body.note,
    )
    return ActionResponse(**result)
```

---

## `routers/unknown.py`

```python
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from supabase import Client

from ..dependencies import (
    get_current_user,
    get_supabase_service,
    require_review_role,
)
from ..schemas.review import (
    IgnoreRequest,
    IgnoreResponse,
    ReclassifyRequest,
    ReclassifyResponse,
    UnknownQueueResponse,
)
from ..services import unknown_service

router = APIRouter()


@router.get("", response_model=UnknownQueueResponse)
async def list_unknown_queue(
    workspace_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    membership: dict = Depends(require_review_role),
    db: Client = Depends(get_supabase_service),
) -> UnknownQueueResponse:
    result = unknown_service.get_unknown_queue(
        db, workspace_id=workspace_id,
        page=page, per_page=per_page, status_filter=status,
    )
    return UnknownQueueResponse(**result)


@router.post("/{item_id}/reclassify", response_model=ReclassifyResponse)
async def reclassify_unknown(
    workspace_id: str,
    item_id: UUID,
    body: ReclassifyRequest,
    membership: dict = Depends(require_review_role),
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_service),
) -> ReclassifyResponse:
    result = unknown_service.reclassify_unknown(
        db, workspace_id=workspace_id, item_id=str(item_id),
        fact_type=body.fact_type, destination=body.destination,
        reviewer_id=user["id"], note=body.note,
    )
    return ReclassifyResponse(**result)


@router.post("/{item_id}/ignore", response_model=IgnoreResponse)
async def ignore_unknown(
    workspace_id: str,
    item_id: UUID,
    body: IgnoreRequest,
    membership: dict = Depends(require_review_role),
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_service),
) -> IgnoreResponse:
    result = unknown_service.ignore_unknown(
        db, workspace_id=workspace_id, item_id=str(item_id),
        reviewer_id=user["id"], note=body.note,
    )
    return IgnoreResponse(**result)
```

---

## `main.py` — adição obrigatória

Adicionar ao `create_app()` existente (após os routers da TASK-003):

```python
from .routers import health, workspaces, sources, review, unknown

# ...após include_router(sources.router):
app.include_router(
    review.router,
    prefix="/workspaces/{workspace_id}/review",
    tags=["review"],
)
app.include_router(
    unknown.router,
    prefix="/workspaces/{workspace_id}/unknown",
    tags=["unknown"],
)
```

---

## Testes obrigatórios

### `tests/api/test_review.py`

```
Autenticação / autorização:
✓ GET /review sem Bearer → 401
✓ GET /review role=staff → 403 insufficient_role
✓ GET /review role=reviewer → 200
✓ require_review_role usa require_workspace_member como base (não reimplementa auth)

Fila de revisão:
✓ GET /review sem fatos pendentes → {"items": [], "total": 0}
✓ GET /review?fact_type=service_price → filtra por tipo
✓ GET /review?page=2&per_page=5 → paginação correta
✓ GET /review/{chunk_id} → retorna facts + rules
✓ GET /review/{chunk_id} de outro workspace → 404

Approve — delega ao RPC (mockar db.rpc):
✓ POST /facts/{id}/approve → 200 {"status": "approved", "resource_id": ..., "resource_type": "extracted_fact"}
✓ POST /facts/{id}/approve fato já approved → 200 SEM chamar RPC (idempotente)
✓ POST /facts/{id}/approve de outro workspace → 404 (maybe_single retorna None)
✓ POST /facts/{id}/approve → db.rpc("approve_fact") chamado com target_fact_id e reason
✓ POST /rules/{id}/approve → 200 {"resource_type": "business_rule"}
✓ POST /rules/{id}/approve regra já approved → 200 SEM chamar RPC

Reject — delega ao RPC (028):
✓ POST /facts/{id}/reject sem reason → 422
✓ POST /facts/{id}/reject com reason → 200 {"status": "rejected"}
✓ POST /facts/{id}/reject → db.rpc("reject_fact") chamado
✓ POST /facts/{id}/reject fato published → 409 (rpc lança, _rpc_exception_to_http converte)
✓ POST /facts/{id}/reject de outro workspace → 404
✓ POST /rules/{id}/reject com reason → 200
✓ POST /rules/{id}/reject de outro workspace → 404

Edit — delega ao RPC (028):
✓ POST /facts/{id}/edit conteúdo válido → 200 {"status": "superseded", "resource_id": <new_id>}
✓ POST /facts/{id}/edit → pre_normalize chamado sobre new_content
✓ POST /facts/{id}/edit → validate_extraction chamado; 422 se inválido
✓ POST /facts/{id}/edit → db.rpc("create_fact_version") chamado com new_content e new_normalized
✓ POST /facts/{id}/edit fato already_superseded → 409
✓ POST /facts/{id}/edit de outro workspace → 404
✓ POST /rules/{id}/edit discount_rule → _validate_rule_edit com {"condition":..., "action":...}
✓ POST /rules/{id}/edit cancellation_policy → _validate_rule_edit com merge flat
✓ POST /rules/{id}/edit inválido → 422 antes de chamar RPC
✓ POST /rules/{id}/edit → db.rpc("create_rule_version") chamado
✓ POST /rules/{id}/edit já superseded → 409

ActionResponse:
✓ approve → resource_type="extracted_fact"
✓ approve rule → resource_type="business_rule"
✓ edit → resource_id é o novo fact_id (retorno do RPC)
✓ resource_id presente em todos os casos
```

### `tests/api/test_unknown.py`

```
Autenticação:
✓ GET /unknown sem Bearer → 401
✓ GET /unknown role=staff → 403

Unknown queue:
✓ GET /unknown → lista com paginação e status_filter
✓ GET /unknown?status=open → apenas itens open

Reclassify — delega ao RPC reclassify_unknown_item (028):
✓ POST /unknown/{id}/reclassify → 200 {"status": "mapped", "extraction_job_id": <uuid>}
✓ POST /unknown/{id}/reclassify → db.rpc("reclassify_unknown_item") chamado com p_item_id, p_fact_type, p_chunk_id, p_source_id
✓ POST /unknown/{id}/reclassify → dispatch_extraction_job chamado com job_id retornado pelo RPC
✓ POST /unknown/{id}/reclassify → dispatch chamado APÓS o RPC (não antes)
✓ POST /unknown/{id}/reclassify → validation_event existe (gerado pelo RPC, verificar via mock ou integração)
✓ POST /unknown/{id}/reclassify fact_type inválido → 422 (validado antes do RPC)
✓ POST /unknown/{id}/reclassify destination inválido → 422 (validado antes do RPC)
✓ POST /unknown/{id}/reclassify já mapped → 409 already_mapped (RPC lança, _rpc_unknown_exception_to_http converte)
✓ POST /unknown/{id}/reclassify já ignored → 409 already_ignored
✓ POST /unknown/{id}/reclassify de outro workspace → 404 (ownership check Python antes do RPC)
✓ Se dispatch falhar: job permanece queued no DB, item permanece mapped (sem rollback do RPC)

Ignore — delega ao RPC ignore_unknown_item (028):
✓ POST /unknown/{id}/ignore → 200 {"status": "ignored"}
✓ POST /unknown/{id}/ignore → db.rpc("ignore_unknown_item") chamado com p_item_id e p_reason
✓ POST /unknown/{id}/ignore idempotente → 200 sem erro (RPC é idempotente)
✓ POST /unknown/{id}/ignore → validation_event existe (gerado pelo RPC)
✓ POST /unknown/{id}/ignore já mapped → 409 (RPC lança already_mapped)
✓ POST /unknown/{id}/ignore de outro workspace → 404
```

---

## O que NÃO fazer

- Não criar tabela `validation_events` nova — usar a existente (migration 013).
- Não usar campos `reviewer_id`, `event_type`, `before_content`, `after_content` na `validation_events` — não existem.
- Não inserir `validation_events` diretamente do Python para approve/reject/edit — o RPC insere internamente.
- Não usar `.single()` — sempre `.maybe_single()` para ownership checks.
- Não chamar `require_workspace_member` diretamente nos routers de review — usar `require_review_role`.
- Não usar `status='pending'`, `'reclassified'` na `unknown_facts_queue` — usar `'open'`, `'mapped'`, `'ignored'` (DDL real).
- Não criar colunas `reclassified_as/by/at` — usar `resolution`, `resolved_by`, `resolved_at` (DDL real).
- Não fazer INSERT + UPDATE separados no Python para edit/versionamento — usar o RPC `create_fact_version`/`create_rule_version` (atômico).
- Não chamar `dispatch_extraction_job` antes do RPC `reclassify_unknown_item` confirmar — o job deve existir no DB antes do dispatch.
- Não inserir `validation_events` do Python para reclassify/ignore — o RPC insere internamente.
- Não chamar `enqueue_extraction_job` diretamente do Python para reclassify — o RPC `reclassify_unknown_item` já cria o `processing_job` internamente.
- Não implementar publicação (`published`) — isso é TASK-007.
- Não implementar contradiction detection — TASK-007.
- Não modificar `chunks.status` automaticamente nesta task.
- Não logar `content` de fatos em logs de info — apenas IDs e tipos.
- Não usar inline imports — todos os imports no topo do módulo.

---

## Critérios de aceite

```
[ ] pytest tests/api/test_review.py -v → todos passam
[ ] pytest tests/api/test_unknown.py -v → todos passam
[ ] GET /review role=staff → 403
[ ] GET /review role=reviewer → 200
[ ] approve fato já approved → 200 SEM chamar RPC (idempotente)
[ ] approve delega ao rpc("approve_fact"), não insere validation_event do Python
[ ] reject delega ao rpc("reject_fact") (migration 028)
[ ] edit delega ao rpc("create_fact_version") (migration 028)
[ ] edit → pre_normalize + validate_extraction ANTES do RPC
[ ] edit → 422 se Pydantic falha (antes de chamar RPC)
[ ] edit fato already_superseded → 409
[ ] edit_rule discount_rule → validate com nested {"condition": ..., "action": ...}
[ ] edit_rule cancellation_policy → validate com flat merge {**condition, **action}
[ ] ActionResponse tem resource_id (não fact_id), resource_type
[ ] reclassify → db.rpc("reclassify_unknown_item") chamado (não update direto)
[ ] reclassify → dispatch_extraction_job chamado com job_id retornado pelo RPC
[ ] reclassify → dispatch APÓS RPC confirmar (não antes)
[ ] reclassify → validation_event gerado pelo RPC (action='manual_created')
[ ] reclassify já mapped → 409
[ ] ignore → db.rpc("ignore_unknown_item") chamado (não update direto)
[ ] ignore → validation_event gerado pelo RPC (action='rejected')
[ ] ignore idempotente → 200 (RPC não lança para status já ignored)
[ ] Se dispatch falhar: item permanece mapped, job permanece queued (sem estado inconsistente)
[ ] migration 028_review_functions.sql criada com 6 RPCs: reject_fact, reject_rule, create_fact_version, create_rule_version, reclassify_unknown_item, ignore_unknown_item
[ ] ruff check . → zero erros
[ ] mypy apps/api → zero erros
[ ] maybe_single() em todas as leituras de ownership (sem .single())
[ ] Nenhum log expõe conteúdo de fatos — apenas IDs e tipos
```

---

## Referências

- `CLAUDE.md` — estados de facts/rules, pipeline, RBAC
- `docs/01-product/USER_FLOWS.md` — Fluxo 2 (revisão), Fluxo 3 (unknown)
- `docs/01-product/VALIDATION_UX.md` — UX de validação
- `tasks/TASK-003-api-endpoints.md` — auth infrastructure
- `tasks/TASK-005-extraction-worker.md` — enqueue/dispatch pattern
- `supabase/migrations/001_enums.sql` — validation_action enum
- `supabase/migrations/009_extracted_facts.sql` — colunas reviewed_by, supersedes etc.
- `supabase/migrations/010_business_rules.sql` — idem
- `supabase/migrations/011_unknown_queue.sql` — status check, resolution, resolved_by
- `supabase/migrations/013_validation_events.sql` — schema real (actor_user_id, action enum)
- `supabase/migrations/022_publish_functions.sql` — approve_fact, approve_rule (já existem)
- `supabase/migrations/023_supersede_rollback_functions.sql` — supersede_fact, supersede_rule
