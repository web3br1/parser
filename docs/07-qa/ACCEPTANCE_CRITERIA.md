# ACCEPTANCE_CRITERIA.md — Critérios de Aceite do MVP

O MVP só está completo quando todos os itens abaixo passam end-to-end.

## Estado de verificacao

Os checkboxes abaixo representam aceite end-to-end do MVP. Eles devem permanecer
abertos ate haver evidencia de ambiente real/piloto, nao apenas testes locais.

Evidencia local verificada em 2026-05-25:

| Area | Evidencia | Resultado |
|---|---|---|
| Suite local completa | `uv run --cache-dir .uv-cache pytest -q` | 515 passed |
| Lint | `uv run --cache-dir .uv-cache ruff check .` | passed |
| Typecheck Python parcial | `npm run typecheck:python` | 36 source files, no issues |
| Typecheck Python strict-full | `npm run typecheck:python:strict-full` | 105 source files, no issues |
| Typecheck frontend | `corepack pnpm --filter @context-builder/web typecheck` | passed |
| Build frontend | `corepack pnpm --filter @context-builder/web build` | passed |
| Context Bundle fixtures | export schema/golden/manifest `--check` | current |
| Secret scan | `uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py` | exit 0 |
| P1 1, publicacao/source publicada | `uv run --cache-dir .uv-cache pytest tests\api\test_query.py tests\api\test_knowledge.py tests\integrity -q` | 72 passed |
| P1 2, source state machine | `uv run --cache-dir .uv-cache pytest tests\integrity workers\classification\tests workers\extraction\tests workers\ingest\tests -q` | 109 passed |
| P1 3 e 4, query contradictions/unknowns | `uv run --cache-dir .uv-cache pytest tests\api\test_query.py -q` | 31 passed |

Evidencia ainda pendente para aceite do MVP:

- smoke real Supabase/Docker pelo orquestrador;
- smoke headless do console contra runtime real;
- gate semantico com predictions reais;
- metricas mecanicas de piloto em ambiente atual;
- auditorias de dependencia (`pnpm audit --prod`, `pip-audit` ou equivalente);
- aceitacao formal de riscos P2 restantes em `PRODUCTION_BLOCKERS_PATCH_REVIEW.md`.

---

## Ingestão e quality gate

- [ ] PDF textual aceito e processado
- [ ] DOCX aceito e processado
- [ ] XLSX/CSV aceito e processado — fórmulas avaliadas, células mescladas expandidas
- [ ] Texto colado aceito e processado
- [ ] PDF escaneado rejeitado antes de gastar tokens
- [ ] PDF com layout fragmentado rejeitado com razão registrada
- [ ] Arquivo com MIME falso rejeitado (validação por conteúdo, não extensão)
- [ ] Arquivo acima do limite de tamanho rejeitado
- [ ] Mensagem clara ao usuário em qualquer rejeição
- [ ] `source_quality_reports` criado para todo arquivo processado
- [ ] Documento duplicado (mesmo hash) não reprocessado — retorna source_id existente
- [ ] PDF escaneado fica registrado em `source_quality_reports.detected_issues` (não descartado silenciosamente)

## Processamento

- [ ] Workers de parsing rodam como processos isolados, com timeout e limites operacionais definidos pelo runtime
- [ ] Chunking segmenta documento antes de classificar
- [ ] Chunks preservam: page_start/page_end, row_start/row_end quando aplicável, content imutável e content_hash
- [ ] Normalização determinística roda antes do LLM (moeda → float, horário → HH:MM, etc.)
- [ ] Chunk com tentativa de injection vai para unknown_facts_queue com flag
- [ ] Classificação ocorre por chunk — nunca por documento inteiro
- [ ] Chunk com confidence < 0.75 vai para unknown_facts_queue
- [ ] Extração usa schema fixo — output livre não entra no banco
- [ ] schema_version, prompt_version, model_provider/model_name registrados em cada fato ou regra
- [ ] Falha de validação de schema (após retry) vai para unknown_facts_queue
- [ ] fact_types de regra vão para business_rules
- [ ] fact_types de fato vão para extracted_facts
- [ ] Evidence span criado para cada fato/regra extraído quando houver evidência literal

## Validação humana

- [ ] Publicacao de facts/rules exige role `owner` ou `manager`; `reviewer` nao publica

- [ ] Interface mostra original_text ao lado do fato extraído
- [ ] Localização evidenciada: página, parágrafo (ou linha/aba para XLSX)
- [ ] Usuário pode aprovar, editar ou rejeitar cada bloco
- [ ] Aprovação/publicação usa funções SQL com `FOR UPDATE`, não duplica evento nem altera workspace errado
- [ ] Todo evento de validação gera registro em validation_events com conteúdo anterior e novo
- [ ] Contagem de itens pendentes na unknown_facts_queue visível
- [ ] Dado não-approved nunca aparece em published_facts

## Camada de publicação e export

- [ ] published_facts view: apenas `status='published'` + dentro da validade + `superseded_by is null`
- [ ] Context Bundle usa apenas published_sources, published_facts e published_rules; nunca extracted_facts direto
- [ ] Readiness retorna ready, warning ou blocked com blocking_reasons e warnings
- [ ] Export blocked nao deve ser ativado pelo consumidor externo como contexto de producao
- [ ] Audit log gerado para todo export com `audit_logs.action = 'context_bundle.export'`
- [ ] Bundle garante `used_unvalidated_data: false` por construcao: apenas dados publicados entram
- [ ] Campos sensitive=true e segredos operacionais nao aparecem no bundle

## Contradições e conflitos

- [ ] Contradições numéricas entre dados approved detectadas via SQL
- [ ] Hierarquia de autoridade aplicada: official vs normal/informal → automático
- [ ] Fatos marcados como `conflicted` saem de published_facts automaticamente
- [ ] Resolução pelo usuário: A prevalece, B prevalece, exceção, ambos rejeitados
- [ ] Fonte perdedora marca fatos derivados como deprecated
- [ ] Rollback de publicação atômico: todos os fatos derivados saem juntos ou nenhum

## Segurança e governança

- [ ] RLS configurado e ativo em todas as tabelas com workspace_id
- [ ] RPCs `SECURITY DEFINER` privilegiadas revogadas de `public`, `anon` e `authenticated`, com smoke `has_function_privilege` passando
- [ ] Storage privado nao possui policies diretas de leitura ou escrita para browser/client roles; upload/delete passam pela API/service role
- [ ] Testes negativos cross-tenant passam para rotas protegidas da API
- [ ] Workers usam claim atomico de job e nao processam o mesmo job em duplicidade
- [ ] Fontes processadas nao permanecem presas em `processing` apos sucesso/falha terminal
- [ ] Gate semantico do piloto passa com predictions exportadas: precision >= 0.85, recall >= 0.75, falsos positivos criticos = 0. Sem predictions, o resultado esperado e `not_evaluated`, nao aprovado.
- [ ] Headers de seguranca, TrustedHost e limite de corpo da API passam em teste
- [ ] Upload rejeita arquivos grandes, MIME falso, macro Office e suspeita de zip bomb
- [ ] Fluxos LGPD de exportacao/delete request existem como comportamento auditavel
- [ ] Chamadas de modelo registram provider/model, prompt_version, tokens, latencia, custo estimado e hash da resposta
- [ ] Frontend interno compila e cobre login, workspace dashboard, fontes/upload, source detail/job, revisao, unknown queue, consulta, knowledge browser e settings/LGPD; smoke headless de browser passa via `node scripts/smoke/frontend_console_smoke.mjs`
- [ ] CI roda testes, lint, frontend build, smoke tests, scan simples de secrets e audits de dependencias
- [ ] workspace_members com roles funcionando
- [ ] Verificação de permissão por ação na API (não só RLS)
- [ ] Token de acesso nunca aparece em resposta de API ou em logs
- [ ] Secrets carregados de variável de ambiente, nunca hardcodados
- [ ] Modelo de IA configurado via env var, nunca hardcodado
- [ ] Log de tokens e custo por operação em token_usage_log
- [ ] Limite de documentos por plano funcionando
- [ ] Idempotência de tasks: retry não duplica fatos ou cobranças

## Readiness gates para release/piloto

- [ ] Nenhum P1 aberto em `docs/07-qa/PRODUCTION_BLOCKERS_PATCH_REVIEW.md`
- [ ] Todo P2 aberto em `docs/07-qa/PRODUCTION_BLOCKERS_PATCH_REVIEW.md` possui mitigacao documentada, owner e aceite explicito de risco
- [ ] Views publicadas e endpoints de knowledge/query provam que uma fact/rule publicada nao aparece se a source nao estiver publicada, ativa e nao deletada
- [ ] Source state machine esta alinhada entre migrations, dominio Python e frontend; `extracted`, `needs_review`, `published` e estados terminais sao representaveis em todos os contratos
- [ ] Query trata `open` e `needs_review` como contradicoes bloqueantes quando relevantes
- [ ] Query retorna `needs_human_validation` quando ha unknown aberto/relevante mesmo sem fact/rule pendente
- [ ] Ingest, classification e extraction possuem comportamento consistente para retry, failed terminal e idempotencia
- [ ] Typecheck Python e frontend executam verificacoes reais e nao podem passar por ausencia de script/pacote selecionado; o gate Python obrigatorio inclui `npm run typecheck:python` e `npm run typecheck:python:strict-full`
- [ ] CI verde em pull request: `uv run ruff check .`, `uv run pytest -q`, `uvx pip-audit`, `pnpm audit --prod`, typecheck e build do frontend
- [ ] Smoke tests incluidos no gate padrao de pytest via `tests/smoke`
- [ ] Secret scan bloqueia valores vazados (`sk-*`, Bearer JWT/key e assignments longos de secrets), sem falhar por nomes de variaveis documentados
- [ ] Smoke full real passa pelo orquestrador canonico: `uv run --cache-dir .uv-cache python scripts\smoke\run_real_smoke.py --target local --full --json-report .run\smoke-local-full.json`
- [ ] `scripts/smoke/supabase_smoke.py --full` continua disponivel apenas como subfase/debug do smoke real
- [ ] Metricas mecanicas do piloto passam via `scripts/pilot/pilot_metrics.py`: approval_rate >= 0.70, edit_rate <= 0.30, unknown_rate <= 0.25, critical_error = 0
- [ ] Gate RLS outsider passa no smoke full: RLS violations = 0
- [ ] Gate semantico passa com `--predictions` ou `--pilot-report` contendo `semantic_predictions`: precision >= 0.85, recall >= 0.75, critical_false_positives = 0, negative_test_false_positives = 0. Sem predictions, registrar `not_evaluated`.

## Context Bundle v1

- [ ] Context Bundle v1 usa apenas published_sources, published_facts, published_rules e evidencias referenciadas
- [ ] Context Bundle v1 retorna `schema_version`, `context_version`, `readiness` e `integrity.bundle_hash`
- [ ] Context Bundle v1 bloqueia readiness quando ha unknown aberto ou contradicao `open`/`needs_review`
- [ ] Context Bundle v1 nunca inclui secrets, bearer tokens, paths locais, prompts crus, stack traces ou conteudo nao publicado
- [ ] Export bem-sucedido de Context Bundle gera `audit_logs.action = 'context_bundle.export'`
- [ ] Gate do Context Bundle passa: `uv run --cache-dir .uv-cache pytest tests\api\test_context_bundle.py tests\api\test_knowledge.py tests\integrity -q`
- [ ] Gate do Context Bundle faz parte do release/piloto padrao, nao apenas de mudancas no export

## Source Pack Compiler

- [ ] Upload de pasta/zip com `00_source_manifest.md` e arquivos numerados e identificado como source pack antes de processar arquivo por arquivo
- [ ] API de preflight retorna `compile_as_source_pack`, `normal_ingest` ou `reject` antes de iniciar ingestao/compilacao
- [ ] Source pack incompleto falha no preflight com lista de arquivos/roles faltantes
- [ ] `compounding-pharmacy-gold` compila para `context_bundle.v1` sem edicao manual
- [ ] Bundle compilado preserva evidence por arquivo/linha CSV e secao Markdown
- [ ] Bundle compilado contem facts, rules, gaps, tests, memory_policy e tool_recommendations uteis
- [ ] Gaps sinteticos aceitos entram como `readiness.status = warning`, nao como `blocked`
- [ ] Bundle compilado nao inclui secrets, bearer tokens, paths locais privados, raw prompts, provider responses ou stack traces
- [ ] Hash do bundle compilado e verificavel pelo consumidor externo
- [ ] Runtime externo importa o bundle compilado e responde com citacao respeitando bloqueios

