# Documentacao

Este diretorio esta organizado pela ordem em que a documentacao costuma ser usada durante implementacao.

## Ordem recomendada

1. `00-start-here`: decisões fechadas, contexto obrigatorio, visao geral e regra de ouro.
2. `01-product`: limites do produto, usuario-alvo e fluxos.
3. `03-pipeline`: comportamento tecnico do processamento.
4. `04-data`: tabelas, schemas, estados e permissoes.
5. `05-security`: isolamento, upload abuse, prompt injection e RLS.
6. `06-prompts`: prompts versionados e contratos esperados.
7. `07-qa`: aceite, testes e outputs esperados.
8. `08-ops`: observabilidade, regressao e rejeicoes.
9. `operations`: runtime local, Docker e smoke/readiness real.

## Mapa rapido

| Preciso entender... | Leia |
|---------------------|------|
| Quais decisões finais guiam o MVP | `00-start-here/MVP_DECISIONS.md` |
| O que o sistema e | `00-start-here/SYSTEM_OVERVIEW.md` |
| O que entra no MVP | `01-product/MVP_SCOPE.md` |
| O fluxo tecnico completo | `03-pipeline/PIPELINE.md` |
| Como exportar contexto para outro chatbot | `03-pipeline/CONTEXT_BUNDLE.md` |
| Como consultar conhecimento internamente para diagnostico | `03-pipeline/QUERY.md` |
| Como rodar runtime local | `operations/LOCAL_RUNTIME.md` |
| Como rodar Docker local | `operations/DOCKER_LOCAL_RUNTIME.md` |
| Como rodar smoke/readiness real | `operations/smoke-runbook.md` |
| Quais dados existem no banco | `04-data/DATA_MODEL.md` |
| Quais fact types existem | `04-data/SCHEMA_REGISTRY.md` |
| Como validar seguranca multi-tenant | `05-security/SECURITY_RLS.md` |
| Como lidar com documentos maliciosos | `05-security/SECURITY.md` |
| Quais prompts usar | `06-prompts/CLASSIFICATION_PROMPT.md` e `06-prompts/EXTRACTION_PROMPTS.md` |
| Como saber se o MVP esta pronto | `07-qa/ACCEPTANCE_CRITERIA.md` |
| Quais problemas dos patches recentes bloqueiam producao | `07-qa/PRODUCTION_BLOCKERS_PATCH_REVIEW.md` |
| O que testar antes do Supabase real | `07-qa/PRE_SUPABASE_TEST_GUIDE.md` |
| Qual matriz de testes roda sem infraestrutura real | `07-qa/TEST_MATRIX_PRE_SUPABASE.md` |
| Como simular E2E com mocks | `07-qa/MOCK_E2E_RUNBOOK.md` |
| Quais gates rodam antes de tasks grandes | `07-qa/REGRESSION_GATES.md` |
| Qual plano cobre Context Bundle e cleanup | `../tasks/TASK-011-context-bundle-integration.md` ate `../tasks/TASK-016-docs-canonicalization.md` |
| O que nunca implementar | `08-ops/REJECTION_RULES.md` |
| Quais migrations são executáveis | `../supabase/README.md` |
| Onde fica o dataset adversarial | `../examples/adversarial/README.md` |

## Decisoes pendentes

Antes de teste real com usuarios, leia `00-start-here/PENDING_DECISIONS.md`.

## Piloto local

Para rodar o piloto local, leia `operations/LOCAL_RUNTIME.md` e
`operations/DOCKER_LOCAL_RUNTIME.md`.

Para smoke/readiness real, leia `operations/smoke-runbook.md`.

