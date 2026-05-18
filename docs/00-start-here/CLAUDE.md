# CLAUDE.md — Context Builder: Índice Operacional

> Ponto de entrada para Claude Code.
> Não contém implementação. Contém navegação e regra de ouro.
> Leia os documentos referenciados antes de qualquer tarefa.

---

## Leitura obrigatória antes de implementar qualquer coisa

| Ordem | Arquivo | O que cobre |
|-------|---------|-------------|
| 1 | `/docs/00-start-here/MVP_DECISIONS.md` | Decisões finais do MVP: escopo, fact types, answer states, pipeline, QA e produção |
| 2 | `/docs/00-start-here/SYSTEM_OVERVIEW.md` | O que o sistema faz, camadas, confiabilidade de fonte, versionamento, answer states |
| 3 | `/docs/03-pipeline/PIPELINE.md` | Fluxo técnico completo: ingestão, consulta, contradição, rollback, idempotência |
| 4 | `/docs/04-data/DATA_MODEL.md` | Schema SQL completo com RLS, views de publicação, permissões por ação |
| 5 | `/docs/01-product/MVP_SCOPE.md` | O que entra, o que não entra, critérios de aceite, roadmap |
| 6 | `/docs/04-data/SCHEMA_REGISTRY.md` | Schemas Pydantic fixos por fact_type |
| 7 | `/docs/08-ops/REJECTION_RULES.md` | O que nunca pode ser implementado |

## Referência durante implementação

| Arquivo | Uso |
|---------|-----|
| `/docs/06-prompts/CLASSIFICATION_PROMPT.md` | Prompt de classificação por chunk |
| `/docs/06-prompts/EXTRACTION_PROMPTS.md` | Prompts de extração por fact_type + rule_evaluation |
| `/docs/03-pipeline/EXTRACTION_CONTRACTS.md` | Contratos de I/O por operação |
| `/docs/05-security/SECURITY_RLS.md` | RLS, isolamento, configuração de sessão |
| `/docs/05-security/SECURITY.md` | Prompt injection, upload abuse, segredos, idempotência, retenção |
| `/docs/02-architecture/MCP_GATEWAY.md` | Geração de MCP, gateway de conectores, OAuth, auditoria (V2) |
| `/docs/01-product/VALIDATION_UX.md` | UX de validação humana |
| `/docs/01-product/USER_FLOWS.md` | Fluxos principais do usuário |
| `/docs/08-ops/OBSERVABILITY.md` | Métricas de qualidade, regressão automática, alertas |
| `/docs/07-qa/ACCEPTANCE_CRITERIA.md` | Checklist completo de aceite do MVP |
| `/docs/07-qa/TEST_CASES.md` | Casos de teste com input e output esperado |
| `/examples/` | Outputs reais esperados por fact_type |

---

## Variáveis de ambiente obrigatórias

```
CLASSIFICATION_MODEL=   # modelo barato (ex: claude-haiku-4-5, gpt-4o-mini)
EXTRACTION_MODEL=       # modelo médio (ex: claude-sonnet-4-6, gpt-4o)
QUERY_MODEL=            # modelo médio/alto para consultas
DATABASE_URL=
STORAGE_BUCKET_URL=
```

Nunca hardcodar nome de modelo no código.

---

## Regra de ouro

> O LLM pode interpretar. Nunca pode criar verdade sem validação, schema e audit log estruturado.


