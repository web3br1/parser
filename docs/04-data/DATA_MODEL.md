# DATA_MODEL.md — Modelo de Dados Real

As migrations em `supabase/migrations/` são a fonte de verdade executável do modelo de dados.

Este documento resume o schema real atual e substitui o modelo legado anterior. Em caso de divergência, prevalecem:

1. `docs/00-start-here/MVP_DECISIONS.md`
2. `supabase/migrations/*.sql`
3. este resumo

## Decisões Fechadas

| Tema | Decisão |
|------|---------|
| Status de facts/rules | Coluna `status`, usando enums `fact_status` e `rule_status` |
| Validação humana | `reviewed_by`, `reviewed_at`, `validation_events` |
| Publicação | `published_by`, `published_at`, views `published_facts` e `published_rules` |
| Versionamento de edição | `supersedes`, `superseded_by` + `validation_events` |
| Schemas e prompts | Tabela unificada `fact_type_schemas` |
| Business rules | `condition JSONB` + `action JSONB`, sem `rule_text` livre |
| Contradições | `fact_ids uuid[]` e `rule_ids uuid[]` |
| Auth/RLS | Supabase Auth com `auth.uid()` via helpers `is_workspace_member` e `has_workspace_role` |

## Fact Types MVP

O MVP usa somente 5 tipos:

| fact_type | Destino | Versão |
|-----------|---------|--------|
| `service_price` | `extracted_facts` | `1.0.0` |
| `business_hours` | `extracted_facts` | `1.0.0` |
| `payment_method` | `extracted_facts` | `1.0.0` |
| `discount_rule` | `business_rules` | `1.0.0` |
| `cancellation_policy` | `business_rules` | `1.0.0` |

Tipos antigos como `price_table`, `service_catalog`, `payment_policy`, `booking_policy` e similares ficam fora do MVP até nova decisão.

## Tabelas Principais

| Tabela | Migration | Papel |
|--------|-----------|-------|
| `workspaces` | `002` | Tenant principal |
| `workspace_members` | `002` | Membership e roles |
| `sources` | `004` | Arquivos e fontes de entrada |
| `source_quality_reports` | `005` | Resultado do quality gate |
| `chunks` | `006` | Trechos processáveis |
| `evidence_spans` | `007` | Evidência textual vinculada ao fato/regra |
| `fact_type_schemas` | `008`, `021` | Registry versionado de schemas/prompts/policies |
| `extracted_facts` | `009` | Fatos extraídos |
| `business_rules` | `010` | Regras condicionais |
| `unknown_facts_queue` | `011` | Revisão manual de desconhecidos |
| `contradictions` | `012` | Conflitos detectados |
| `validation_events` | `013` | Auditoria de validação humana |
| `query_audits` | `015` | Auditoria de consultas internas |
| `processing_jobs` | `016` | Idempotência e execução assíncrona |
| `token_usage_log` | `017` | Custo e tokens |
| `audit_logs` | `018` | Auditoria operacional genérica |
| `source_pack_import_runs` | `046` | Preflight/compile lifecycle de source packs, `input_hash`, readiness e bundle hashes |

## Views Publicadas

`published_facts` e `published_rules` usam apenas registros com:

```sql
status = 'published'
and superseded_by is null
and dentro da janela valid_from/valid_until
```

Dados não publicados nunca devem ser usados pela consulta auditável.

## RLS

Todas as tabelas multi-tenant devem usar:

```sql
public.is_workspace_member(workspace_id)
public.has_workspace_role(workspace_id, ...)
```

Nunca usar:

```sql
workspace_id = auth.uid()
current_setting('app.current_user_id')
```

O projeto está padronizado em Supabase Auth nativo.

## Observabilidade

`pipeline_metrics`, `fact_type_metrics` e `unsupported_sources` são pós-MVP até nova migration. No MVP, a observabilidade mínima vem de:

- `processing_jobs`
- `query_audits`
- `token_usage_log`
- `audit_logs`
- `validation_events`
- `source_quality_reports`

## Quality Gate

A migration `005` armazena scores:

```sql
readability_score
structure_score
extractability_score
noise_score
final_score
is_processable
detected_issues
decision
```

Os thresholds determinísticos ficam no código de pipeline e devem preencher esses campos, não criar outro contrato paralelo.
