# Relatorio Tecnico - Ambiente Dev e Dataset Semi-Real

Data da consolidacao: 2026-05-13

## 1. Sumario Executivo

O ambiente `context-builder-dev` no Supabase, projeto `znvixbtquyscpduxiavk`, foi validado funcionalmente para uso em piloto controlado. A validacao tecnica cobriu contratos de banco, RLS, Storage privado, smoke minimo, smoke full E2E, suite artificial com gates adicionais e dataset semi-real expandido com 20 documentos sinteticos ricos.

Resultado consolidado:

| Area | Resultado |
|---|---|
| Supabase dev | Aprovado funcionalmente |
| Bucket privado | Aprovado |
| RLS outsider check | Aprovado |
| Smoke minimo | Aprovado |
| Smoke full E2E | Aprovado |
| Suite artificial de gates | Aprovada |
| Dataset semi-real | 20/20 documentos parseados localmente |
| Testes do dataset | Aprovados |
| Lint dos scripts alterados | Aprovado |

O sistema esta pronto para a proxima fase: execucao do piloto semi-real com upload dos 20 documentos, revisao humana completa e comparacao dos fatos extraidos contra o manifesto de expectativas.

## 2. Escopo Validado

### 2.1 Ambiente Supabase

Projeto validado:

- Project ref: `znvixbtquyscpduxiavk`
- Ambiente declarado: `APP_ENV=development`
- Storage bucket: `context-builder-private`
- API local usada nos testes: `http://localhost:8005`

Componentes validados:

- tabelas publicas principais;
- RPCs de ingest, classificacao, extracao e workspace;
- RLS nas tabelas expostas;
- indice critico `uq_sources_workspace_file_hash_active`;
- coluna `unknown_facts_queue.metadata`;
- bucket privado;
- visibilidade de tenant negada para usuario outsider;
- ciclo ingest -> classification -> review -> approve -> publish -> `published_facts`.

### 2.2 Observacao Sobre Migration History

O schema esta funcionalmente correto, mas `supabase_migrations.schema_migrations` nao representa integralmente as migrations `000-035`, pois a maior parte do schema foi aplicada via Supabase Management API HTTP, e nao via `supabase db push`.

Evidencia observada:

- `schema_migrations` registrou a migration timestampada `034`.
- Contratos funcionais confirmaram que os objetos esperados de `000-035` existem.
- A migration `035_unknown_queue_metadata.sql` foi criada localmente e a coluna correspondente foi aplicada/verificada no banco.

Impacto:

- Nao bloqueia o piloto dev.
- Pode afetar uso futuro de `supabase db push` sem reconciliacao.

Recomendacao:

- Para este dev project, continuar usando o caminho HTTP documentado ou reconciliar migration history antes de voltar ao fluxo CLI.

## 3. Correcoes Tecnicas Realizadas

### 3.1 Fallback Sem `psql`

Arquivo alterado:

- `scripts/smoke/check_supabase_contracts.py`

Motivo:

- `psql` nao estava disponivel no PATH local.
- `npx supabase --version` apresentou timeout.
- A validacao precisava continuar sem instalar dependencias globais no Windows.

Resultado:

- O script agora usa `psql` quando disponivel.
- Quando `psql` nao esta disponivel, usa Supabase Management API HTTP com:
  - `SUPABASE_ACCESS_TOKEN`
  - `SUPABASE_PROJECT_REF`

### 3.2 Migration 035

Arquivo criado:

- `supabase/migrations/035_unknown_queue_metadata.sql`

DDL:

```sql
alter table public.unknown_facts_queue
add column if not exists metadata jsonb not null default '{}'::jsonb;
```

Motivo:

- A suite artificial identificou falha real: o RPC `complete_classification_job` tentava inserir `metadata` em `unknown_facts_queue`, mas a coluna nao existia no schema remoto.
- Isso impedia que documento com prompt injection fosse roteado corretamente para a fila de unknown.

Resultado:

- Coluna aplicada e verificada como `jsonb`.
- Suite artificial passou depois da correcao.

## 4. Resultados de Validacao Supabase

### 4.1 Contratos Supabase

Comando executado:

```powershell
$env:UV_CACHE_DIR='.uv-cache'
$env:SUPABASE_ACCESS_TOKEN='<process-only>'
$env:SUPABASE_PROJECT_REF='znvixbtquyscpduxiavk'
uv run python scripts\smoke\check_supabase_contracts.py
```

Resultado:

| Check | Resultado |
|---|---|
| Extensions instaladas | OK |
| Tabelas esperadas existem | OK |
| RPCs esperados existem | OK |
| Indices esperados existem | OK |
| `unknown_facts_queue.metadata` existe | OK |
| RLS habilitado | OK |
| Bucket privado existe | OK |
| Contratos Supabase | OK |

### 4.2 Smoke Minimo

Relatorio:

- `.run/smoke-min-dev-validation.json`

Resultado:

| Etapa | Resultado |
|---|---|
| Health API | OK |
| Workspace criado | OK |
| Membership owner visivel | OK |
| Upload de fixture | OK |
| Contrato source/job | OK |
| Ingest | OK |
| Chunks criados | OK |
| RLS outsider | OK |

Workspace usado:

- `0a5540e2-092a-4c01-a0e8-12a85ce4fc6e`

Status:

- `passed`

### 4.3 Smoke Full E2E

Relatorio:

- `.run/smoke-full-dev-validation.json`

Periodo:

- Inicio: `2026-05-13T16:13:59Z`
- Fim: `2026-05-13T16:15:38Z`
- Duracao aproximada: 99 segundos

Resultado:

| Etapa | Resultado |
|---|---|
| Health API | OK |
| Workspace criado | OK |
| Membership owner visivel | OK |
| Upload | OK |
| Source/job contracts | OK |
| Ingest | OK |
| Chunks criados | OK |
| RLS outsider | OK |
| Review queue | OK |
| Approve + publish | OK |
| Leitura em `published_facts` | OK |

Workspace usado:

- `abed0583-97a0-4a0f-9d50-55dfa19737a9`

Source:

- `a96c2fc5-4d89-4fdd-ace1-56c0e9873bee`

Chunk:

- `6ee653ae-32be-4e17-9177-cfe05c01eeb9`

Fact publicado:

- `31d0a9d8-5f6c-4fda-ab2d-3fdc43ec5f12`
- Tipo: `service_price`

Status:

- `passed`

### 4.4 Limpeza Operacional

Comando executado:

```powershell
uv run python scripts\smoke\cleanup_smoke.py --slug-prefix smoke-
```

Resultado:

- `marked_deleted=2`

## 5. Suite Artificial de Gates

Relatorio:

- `.run/artificial-pilot-suite-8005.json`

Status:

- `passed`

Checks executados:

| Gate | Resultado |
|---|---|
| Matriz de formatos sinteticos | OK |
| Upload adversarial rejeitado | OK |
| Dataset baseline ingerido | OK |
| Permissoes de upload | OK |
| Permissoes de review | OK |
| Approve + publish humano | OK |
| Prompt injection para unknown queue | OK |
| Reenqueue contract | OK |
| Conflict contract | OK |
| Latencia single upload | OK |

Resultado de latencia registrado:

- CSV upload + ingest: `10.76s`

Observacoes:

- `human_review_reject` e `human_review_edit` ficaram marcados como skipped/OK porque a fixture gerou somente um fato editavel nessa rodada.
- Isso nao bloqueia o piloto semi-real, mas reforca a necessidade de executar revisao humana em volume maior.

## 6. Dataset Semi-Real Expandido

### 6.1 Artefatos

Arquivos principais:

- `examples/pilot_semireal/`
- `examples/pilot_semireal/manifest.json`
- `scripts/pilot/generate_semireal_documents.py`
- `tests/smoke/test_semireal_documents.py`
- `docs/07-qa/SEMI_REAL_SYNTHETIC_DATASET.md`

### 6.2 Composicao

Total:

- 20 documentos

Distribuicao por formato:

| Formato | Quantidade |
|---|---:|
| CSV | 4 |
| DOCX | 4 |
| PDF | 4 |
| TXT | 4 |
| XLSX | 4 |

Distribuicao por unidade ficticia:

| Unidade | Quantidade |
|---|---:|
| Centro | 5 |
| Jardins | 5 |
| Moema | 5 |
| Vila Madalena | 5 |

Distribuicao por tipo documental:

| Tipo | Quantidade |
|---|---:|
| pricing | 3 |
| pricing_table | 2 |
| adversarial | 1 |
| availability | 1 |
| business_rules | 1 |
| conflict | 1 |
| contact | 1 |
| discounts | 1 |
| events | 1 |
| exceptions | 1 |
| faq | 1 |
| finance_rules | 1 |
| hours | 1 |
| hours_contact | 1 |
| payments | 1 |
| policy | 1 |
| products | 1 |

### 6.3 Cobertura Semantica

O manifesto contem expectativas para 18 categorias semanticas:

| Categoria | Documentos com essa expectativa |
|---|---:|
| service_price | 6 |
| business_hours | 5 |
| cancellation_policy | 4 |
| faq_item | 4 |
| discount_rule | 3 |
| contact_info | 2 |
| expired_rule | 2 |
| payment_method | 2 |
| requires_manual_review | 2 |
| audit_note | 1 |
| business_rule | 1 |
| conflict_signal | 1 |
| deprecated_contact | 1 |
| deprecated_payment_method | 1 |
| product_price | 1 |
| service_availability | 1 |
| suspended_service | 1 |
| unknown_facts_queue | 1 |

Cobertura qualitativa:

- precos de servicos;
- horarios regulares e excecoes temporais;
- contatos ativos e contatos obsoletos;
- pagamentos ativos, descontinuados e em piloto;
- descontos ativos, expirados e conflitantes;
- politicas de cancelamento/no-show/remarcacao;
- FAQ operacional;
- disponibilidade por profissional;
- produtos, para testar over-generalization como `service_price`;
- servicos suspensos/parciais;
- conflitos documentais;
- prompt injection embutido;
- regras que exigem revisao manual.

### 6.4 Resultado de Parse Local

Validacao local dos parsers:

| Metrica | Resultado |
|---|---:|
| Documentos parseados | 20 |
| Falhas de parse | 0 |
| Caracteres extraidos | 11.660 |
| Paginas extraidas | 12 |
| Sheets extraidas | 8 |

Resultado:

- `20/20` documentos parseados sem erro.

### 6.5 Estatisticas Por Documento

| Arquivo | Formato | Chars | Pages | Sheets | Expectativas |
|---|---|---:|---:|---:|---|
| `01_centro_catalogo_servicos.txt` | txt | 889 | 1 | 0 | payment_method, service_price |
| `02_centro_politica_cancelamento.docx` | docx | 860 | 1 | 0 | cancellation_policy |
| `03_centro_horarios_e_contato.pdf` | pdf | 638 | 1 | 0 | business_hours, contact_info |
| `04_centro_tabela_precos.csv` | csv | 319 | 0 | 1 | service_price |
| `05_centro_promocoes.xlsx` | xlsx | 354 | 0 | 1 | discount_rule, expired_rule |
| `06_jardins_catalogo_quimica.txt` | txt | 783 | 1 | 0 | faq_item, service_price |
| `07_jardins_faq.docx` | docx | 888 | 1 | 0 | faq_item |
| `08_jardins_eventos.pdf` | pdf | 736 | 1 | 0 | cancellation_policy, service_price |
| `09_jardins_equipe.csv` | csv | 305 | 0 | 1 | business_hours, requires_manual_review |
| `10_jardins_produtos.xlsx` | xlsx | 317 | 0 | 1 | product_price |
| `11_moema_barbearia_precos.txt` | txt | 569 | 1 | 0 | faq_item, service_price |
| `12_moema_regras_pacotes.docx` | docx | 813 | 1 | 0 | cancellation_policy, discount_rule |
| `13_moema_contato.pdf` | pdf | 657 | 1 | 0 | business_hours, contact_info, deprecated_contact |
| `14_moema_agenda.csv` | csv | 347 | 0 | 1 | business_hours |
| `15_moema_caixa.xlsx` | xlsx | 310 | 0 | 1 | deprecated_payment_method, payment_method, requires_manual_review |
| `16_vila_madalena_excecoes.txt` | txt | 867 | 1 | 0 | business_hours, discount_rule, faq_item, service_availability |
| `17_vila_madalena_injection.docx` | docx | 639 | 1 | 0 | unknown_facts_queue |
| `18_vila_madalena_conflito.pdf` | pdf | 672 | 1 | 0 | audit_note, conflict_signal, expired_rule |
| `19_vila_madalena_servicos.csv` | csv | 346 | 0 | 1 | service_price, suspended_service |
| `20_vila_madalena_financeiro.xlsx` | xlsx | 351 | 0 | 1 | business_rule, cancellation_policy |

## 7. Testes Locais do Dataset

Comandos:

```powershell
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests\smoke\test_semireal_documents.py -q
uv run ruff check scripts\pilot\generate_semireal_documents.py tests\smoke\test_semireal_documents.py
```

Resultados:

| Verificacao | Resultado |
|---|---|
| `test_semireal_dataset_has_20_documents_across_supported_formats` | OK |
| `test_semireal_generator_writes_manifest_and_files` | OK |
| Ruff | OK |

Resumo:

- `2 passed`
- `All checks passed`

## 8. Interpretacao Tecnica

### 8.1 O Que Ja Esta Provado

O ambiente ja provou:

- que o schema remoto suporta o pipeline E2E;
- que o Storage privado esta operacional;
- que RLS impede vazamento entre tenants;
- que workers conseguem processar pelo menos um documento ate publicacao;
- que prompt injection pode ser roteado para unknown queue apos a correcao da coluna `metadata`;
- que os parsers locais aceitam os 20 documentos semi-reais.

### 8.2 O Que Ainda Nao Esta Provado

Ainda nao esta provado:

- qualidade semantica em volume;
- taxa real de aprovacao humana;
- taxa real de edicao humana;
- taxa de unknown em documentos semi-reais;
- comportamento de conflito documental em volume;
- se produtos sao corretamente separados de servicos;
- se regras expiradas/descontinuadas nao sao publicadas como ativas;
- se itens em piloto ou sob consulta sao mantidos para revisao humana;
- performance do pipeline processando os 20 documentos em uma mesma rodada.

## 9. Riscos Remanescentes

| Risco | Severidade | Observacao |
|---|---|---|
| Migration history incompleto | Media | Pode atrapalhar `supabase db push`; nao bloqueia piloto dev validado |
| Over-generalization de produtos como servicos | Media | Dataset inclui documento 10 para detectar isso |
| Regras expiradas publicadas como ativas | Alta | Dataset inclui docs 05, 16 e 18 |
| Conflito documental nao automatizado | Media | Existe contrato manual; precisa avaliacao no piloto semi-real |
| Approval rate artificial baixo | Media | Smokes aprovam pouco por desenho; piloto semi-real precisa revisao completa |
| Latencia com 20 docs | Media | Ainda nao medida em lote |
| Prompt injection em formatos diferentes | Media | Dataset inclui DOCX adversarial; suite artificial validou TXT adversarial |

## 10. Proximo Plano de Execucao

### 10.1 Rodada Semi-Real

Executar pipeline com os 20 documentos em workspace dedicado:

1. Criar workspace `pilot-semireal-v1`.
2. Fazer upload dos 20 arquivos de `examples/pilot_semireal`.
3. Aguardar ingest/classificacao/extracao de todos.
4. Revisar manualmente todos os fatos e unknowns.
5. Aprovar, rejeitar ou editar cada item.
6. Publicar somente fatos validados.
7. Comparar resultado contra `manifest.json`.
8. Gerar relatorio de metricas do workspace.

### 10.2 Metricas Alvo

Gates recomendados:

| Metrica | Gate |
|---|---|
| Critical errors | `0` |
| Parse failures | `0` |
| Approval rate | `>= 70%` apos revisao humana |
| Edit rate | `<= 30%` |
| Unknown rate | `<= 25%`, exceto casos adversariais/ambiguous esperados |
| Prompt injection | `100%` para unknown/review, nunca publish direto |
| Regras expiradas | `0` publicadas como ativas |
| Itens descontinuados | `0` publicados como ativos |
| RLS outsider | `0` vazamentos |

### 10.3 Artefatos Esperados da Proxima Rodada

Recomenda-se gerar:

- `.run/semireal-pilot-upload-report.json`
- `.run/semireal-pilot-review-report.json`
- `.run/semireal-pilot-quality-report.json`
- `.run/semireal-pilot-metrics.json`

## 11. Conclusao

O estado atual e tecnicamente solido para sair da validacao de infraestrutura e entrar em validacao semantica controlada.

A infraestrutura dev passou os gates tecnicos principais. O dataset semi-real agora possui diversidade suficiente para medir comportamento de extracao, classificacao, revisao e publicacao em cenarios mais proximos de uso real, mantendo controle total por meio do manifesto de expectativas.

Conclusao operacional:

- TASK-010 pode ser considerada concluida no eixo infraestrutura/dev.
- O proximo marco deve ser a rodada `pilot-semireal-v1` com os 20 documentos expandidos.
