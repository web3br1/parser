# SECURITY_RLS.md — Segurança e Isolamento Multi-Tenant

Fonte executável: `supabase/migrations/020_rls.sql` e `025_workspace_schema_policies.sql`.

## Princípio

Todo acesso multi-tenant passa por RLS no Supabase/Postgres.
Nenhuma query de aplicação deve depender apenas de filtro manual por `workspace_id`.

## Decisao MVP: API-only para dados de revisao

O frontend nao deve consultar diretamente as tabelas de dados brutos, revisao
ou conflito pelo Supabase client. O caminho suportado para o MVP e:

```text
browser -> API backend -> Supabase service_role -> Postgres/RLS/funcoes
```

As seguintes tabelas sao consideradas sensiveis para acesso direto por client:

- `public.chunks`
- `public.evidence_spans`
- `public.extracted_facts`
- `public.business_rules`
- `public.unknown_facts_queue`
- `public.contradictions`

`anon` e `authenticated` nao podem ter privilegios de tabela sobre elas. Isso
impede que conteudo nao publicado, chunks em `needs_review`, unknowns abertos
ou contradicoes pendentes sejam lidos por um browser mesmo quando o usuario e
membro do workspace. A API deve expor apenas respostas publicadas ou estados de
revisao agregados, sem vazar payload bruto de revisao.

Qualquer mudanca para Supabase direto no frontend precisa ser tratada como nova
decisao de seguranca: criar policies por role e status, atualizar
`supabase/migrations/020_rls.sql`, `tests/integrity/test_migration_contracts.py`
e `scripts/smoke/check_supabase_contracts.py`, e provar negativos por role para
chunks, facts/rules nao publicados, unknowns e contradictions.

## Auth

O projeto usa Supabase Auth nativo:

```sql
auth.uid()
```

`auth.users.id` se conecta a `workspace_members.user_id`.

## Helpers Obrigatórios

```sql
public.is_workspace_member(workspace_id)
public.has_workspace_role(workspace_id, array['owner','manager']::workspace_role[])
```

Nunca usar:

```sql
workspace_id = auth.uid()
current_setting('app.current_user_id')
SET LOCAL app.current_user_id
```

## Roles

| Role | Uso no MVP |
|------|------------|
| owner | gerencia workspace, membros, conectores, auditoria e solicita delete LGPD |
| manager | upload, revisão, publicação, rollback, consulta |
| reviewer | revisão, aprovação, edição e rejeição de facts/rules; sem publicação |
| staff | consulta e visualização permitida por RLS/API |

## Storage privado

O bucket privado existe apenas como backend storage. Browser/client roles nao
devem ter policies diretas de `SELECT`, `INSERT`, `UPDATE` ou `DELETE` em
`storage.objects` para `context-builder-private`.

O caminho suportado e:

```text
browser -> API backend -> service_role -> Supabase Storage
```

Isso garante que upload/delete passem por validacao de MIME/magic bytes, limite
de tamanho, criacao de `sources`, job idempotente, auditoria e fluxo LGPD. Uma
mudanca para signed upload direto precisa de novo desenho de seguranca, com
token curto, policy limitada por path, validacao posterior obrigatoria e teste
negativo em `scripts/smoke/check_supabase_contracts.py`.

## Criação de Workspace

Workspace deve ser criado pela função:

```sql
public.create_workspace_with_owner(workspace_name, workspace_slug, workspace_settings)
```

Ela cria o workspace e insere o usuário autenticado como `owner` em uma operação controlada por `security definer`.

## O Que Nunca Fazer

- Nunca desabilitar RLS para simplificar query.
- Nunca filtrar workspace apenas na camada de aplicação.
- Nunca usar superuser em runtime.
- Nunca expor arquivo privado sem checar membership.
- Nunca criar policy baseada em `workspace_id = auth.uid()`.
- Nunca usar Supabase direto no browser para tabelas de revisao sem revisar as
  policies e os contratos de smoke acima.
