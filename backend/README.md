# Backend

Base inicial para FastAPI + workers.

Arquivos criados nesta etapa:

| Arquivo | Papel |
|---------|-------|
| `app/schemas/mvp.py` | Pydantic schemas equivalentes à migration `021_seed_mvp_schemas.sql` |
| `app/normalization.py` | Normalizadores determinísticos iniciais |

Próximo passo de implementação: criar endpoints FastAPI que chamem as tabelas e funções SQL em `supabase/migrations`.
