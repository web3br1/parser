# Supabase

Migrations iniciais para PostgreSQL/Supabase.

## Ordem

Aplicar os arquivos em `migrations/` na ordem numérica:

```text
000_extensions.sql
001_enums.sql
002_workspaces.sql
...
027_contradiction_helpers.sql
```

## Premissas

- Supabase Auth ativo.
- `auth.users.id` é a identidade do usuário.
- Autorização multi-tenant passa por `workspace_members`.
- RLS usa `public.is_workspace_member(workspace_id)` ou `public.has_workspace_role(...)`.
- Nunca usar `workspace_id = auth.uid()`.

## Migrations de fechamento já geradas

```text
022_publish_functions.sql
023_supersede_rollback_functions.sql
024_storage_policies.sql
025_workspace_schema_policies.sql
026_source_authority.sql
027_contradiction_helpers.sql
```

## Próximos artefatos esperados

```text
Pydantic schemas equivalentes aos JSON Schemas
Endpoints FastAPI que chamam essas tabelas e funções
Testes automatizados de RLS, storage, publicação e rollback
```
