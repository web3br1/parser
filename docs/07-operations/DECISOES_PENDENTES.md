# Decisões Pendentes — Context Builder

Documento de registro de decisões operacionais, de produto e de segurança.
Todas as decisões abaixo foram fechadas em sessão de entrevista em 2026-05-12.

---

## Estado atual

| Item | Valor |
|------|-------|
| Última validação | 2026-05-12 |
| Ambiente | Supabase dev real |
| Smoke full | passed |
| Prontidão técnica | 95% |

---

## P0 — Bloqueavam teste real com dados reais

### D-001 — Rotação de secrets expostos

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisor** | owner técnico |
| **Decisão** | Todos os secrets (Supabase access token, service role key, anon key, OpenAI API key) já foram rotacionados. |
| **Política** | `.env` no gitignore. `.env.example` contém apenas nomes sem valores. Sem gerenciador externo por ora. |
| **Alternativas recusadas** | Gerenciador de secrets (Doppler, Infisical) — adiado para pós-piloto. |
| **Impacto em código** | Nenhum — `.env.example` já correto. |
| **Impacto em docs** | Confirmar que nenhum runbook contém secrets reais. |
| **Validação necessária** | Smoke full passando com secrets novos. |

---

### D-002 — Ambiente oficial do teste real

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisor** | owner técnico |
| **Decisão** | Piloto roda no Supabase dev atual (mesmo ambiente do smoke full). |
| **Alternativas recusadas** | Staging dedicado — overhead sem necessidade no volume do piloto. Produção limitada — prematuro. |
| **Impacto em código** | Nenhum. |
| **Impacto em docs** | Workspaces de smoke e workspaces reais devem ser identificados com prefixo diferente para evitar mistura. |
| **Validação necessária** | Workspaces separados confirmados antes do primeiro usuário. |

---

### D-003 — Broker oficial para teste real

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisor** | owner técnico |
| **Decisão** | Redis local na mesma máquina da API e workers. |
| **Alternativas recusadas** | Redis gerenciado — overhead para piloto local. Filesystem broker — proibido para ambiente compartilhado. |
| **Impacto em código** | `REDIS_URL` deve apontar para `redis://localhost:6379` no `.env` do piloto. |
| **Impacto em docs** | Filesystem broker explicitamente documentado como dev-only fallback. |
| **Validação necessária** | `check_local_stack` e `start_local_stack` passando sem `-FilesystemBroker`. |

---

### D-004 — Política de dados reais

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisor** | owner técnico |
| **Decisão** | Qualquer documento de negócio é permitido — app sem acesso externo, dados não saem do ambiente. |
| **Tipos permitidos** | PDF, DOCX, CSV, XLSX, TXT, EPUB e outros formatos comuns em empresas. |
| **Retenção** | Arquivos originais apagados ao fim do piloto. Chunks e fatos podem ser mantidos. |
| **Consentimento** | Não necessário — piloto interno controlado sem usuário final externo. |
| **Alternativas recusadas** | Restringir a documentos de baixo risco — desnecessário dado isolamento completo da rede. |
| **Impacto em código** | Configurar deleção em lote de arquivos originais ao encerrar piloto. |
| **Impacto em docs** | Registrar data de encerramento do piloto e procedimento de deleção. |
| **Validação necessária** | Script de deleção de arquivos por workspace testado antes de encerrar. |

---

### D-005 — Fronteira de responsabilidade do MVP

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisor** | produto |
| **Decisão** | "Transformar documentos de negócio em fatos revisados, publicados e com trilha de auditoria." |
| **Fora do escopo** | Resposta automática a cliente final, chatbot, conectores externos, publicação automática. |
| **Alternativas recusadas** | Base de conhecimento consultável / Validador de documentos — framing menos preciso. |
| **Impacto em docs** | Telas e documentação não devem prometer resposta automática ou atendimento. |
| **Validação necessária** | UI revisada para não sugerir automação de resposta. |

---

## P1 — Necessárias para piloto controlado

### D-006 — Critério de sucesso do piloto

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisor** | produto + owner técnico |
| **Métricas** | `approval_rate > 70%` / `edit_rate < 30%` / `unknown_rate < 25%` / `critical_error = 0` / `RLS violations = 0` |
| **Gate** | Todas as métricas devem passar para continuar o piloto. |
| **Alternativas recusadas** | Critical error como único hard stop — insuficiente. Medir sem gate — não gera decisão. |
| **Impacto em código** | Queries para calcular as métricas por workspace e por período. |
| **Impacto em docs** | Template de relatório de piloto a criar. |
| **Validação necessária** | Queries de métricas testadas com dados do smoke. |

---

### D-007 — Dataset mínimo do piloto

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisor** | produto |
| **Decisão** | Documentos reais disponíveis sem classificação prévia. Piloto serve como coleta de baseline. |
| **Privacidade** | Documentos anonimizados ou fictícios. Sem dados de cliente final. |
| **Alternativas recusadas** | Mix controlado (bons/ruins/adversariais) — overhead desnecessário para piloto baseline. |
| **Impacto em docs** | Dataset não deve entrar no repositório se contiver dados reais. |
| **Validação necessária** | Lista de documentos usados arquivada externamente. |

---

### D-008 — Modelo LLM e custo por ambiente

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisor** | owner técnico |
| **Classificação** | Modelos locais — Gemma 4 (seleção de variantes para documentos técnicos e gerais). |
| **Extração** | Modelo local equivalente em qualidade ao Claude Sonnet (ex: Llama 3.3 70B, Mistral Large local). |
| **Inferência** | Ollama ou servidor de inferência local. |
| **Budget** | Zero custo de API — infraestrutura local. |
| **Alternativas recusadas** | GPT-4o / Claude Sonnet via API — custo e dependência externa desnecessários. |
| **Impacto em código** | Workers devem apontar para `OLLAMA_BASE_URL` ou endpoint local configurável via env. API OpenAI/Anthropic vira fallback opcional. |
| **Impacto em docs** | Requisitos de hardware documentados (GPU/RAM mínimos para os modelos escolhidos). |
| **Validação necessária** | Smoke full passando com modelos locais antes do piloto. |

---

### D-009 — Deploy alvo da API e workers

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisor** | owner técnico |
| **Decisão** | Localhost — API FastAPI + workers Celery + modelos locais na mesma máquina. |
| **Acesso** | Rede local apenas. Sem exposição externa no piloto. |
| **Alternativas recusadas** | Servidor dedicado / VPS com GPU — overhead para piloto inicial. Ngrok — piloto é rede local. |
| **Impacto em código** | `start_local_stack` deve iniciar API, workers e Redis sem depender de infra externa. |
| **Impacto em docs** | Runbook de start documentado por processo (API, workers, Redis, modelos). |
| **Validação necessária** | Smoke full passa com stack completa no mesmo hardware do piloto. |

---

### D-010 — Estratégia de observabilidade mínima

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisor** | owner técnico |
| **Decisão** | Logs estruturados com `job_id`, `source_id`, `workspace_id` em todo erro. Script `diagnose_source` como primeira resposta. |
| **Alertas** | Notificação quando job vai para `failed` ou `needs_manual_review`. |
| **Alternativas recusadas** | Sentry — overhead de setup para piloto local. Logs simples — insuficiente para diagnóstico. |
| **Impacto em código** | Todo log de erro deve incluir os 4 campos de correlação. Alerta pode ser log destacado ou notificação local. |
| **Impacto em docs** | Runbook de incidente criado com primeira resposta: `diagnose_source <source_id>`. |
| **Validação necessária** | Falha simulada gera log com todos os campos de correlação. |

---

### D-011 — UX do review humano

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisor** | produto |
| **Público** | Time interno / admin técnico. UX funcional sem polimento visual necessário. |
| **Ações obrigatórias** | Aprovar / Editar+Aprovar / Rejeitar / Enviar para unknown queue. |
| **Alternativas recusadas** | UX para usuário de negócio não técnico — complexidade desnecessária no piloto. |
| **Impacto em código** | Tela de review com as 4 ações + visualização de evidência textual + histórico de `validation_events`. |
| **Validação necessária** | Fluxo completo aprovar → publicar testado por usuário interno. |

---

### D-012 — Reprocessamento e reenqueue operacional

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisor** | owner técnico |
| **Decisão** | Reenqueue manual sob demanda via `diagnose_source` + script de reenqueue. |
| **Retries** | 3 tentativas (1 original + 2 retries). Após terceira falha → `needs_manual_review`. |
| **Alternativas recusadas** | Reenqueue automático por idade — risco de duplicidade sem validação prévia. |
| **Impacto em código** | `max_retries = 3` configurável por tipo de job em env. |
| **Impacto em docs** | Runbook: "job stuck → `diagnose_source` → `reenqueue_job <job_id>`". |
| **Validação necessária** | Idempotência de reenqueue validada (mesmo job_id não cria duplicata). |

---

## P2 — Antes de produção

### D-013 — Rollback e supersede para dados publicados

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Permissão** | Owner e Manager podem despublicar e supersede. Reviewer e Staff: só leitura. |
| **UX** | Published view mostra só versão ativa. Histórico completo em `validation_events`. |
| **Alternativas recusadas** | Todas as versões visíveis inline — confuso para usuário. |
| **Impacto em código** | Endpoint de despublicação com verificação de role. `published view` filtra por status ativo. |
| **Validação necessária** | Fluxo supersede testado: fato antigo vai para `superseded`, novo é ativo. |

---

### D-014 — Política de conflitos

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisão** | Conflito nunca é resolvido automaticamente. Marca `conflicting_sources` e exige revisão humana. |
| **Consulta** | Fatos conflitantes excluídos do published view. Consulta retorna `conflicting_sources` com aviso. |
| **Alternativas recusadas** | Fonte mais recente vence / Autoridade vence — automação prematura sem regra de negócio validada. |
| **Impacto em código** | Detector de conflito por `(workspace_id, fact_type, normalized_key)`. Published view exclui `conflicting_sources` não resolvidos. |
| **Validação necessária** | Teste com dois documentos contraditórios → ambos marcados conflicting → consulta retorna estado correto. |

---

### D-015 — Multi-tenant e roles finais

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Roles** | Owner (tudo) / Manager (upload+review+admin) / Reviewer (review sem admin) / Staff (leitura). |
| **Convite** | Só Owner pode convidar novos membros. |
| **Alternativas recusadas** | Só Owner no piloto — impede teste de colaboração. |
| **Impacto em código** | RBAC implementado na API. UI não mostra ação proibida por role. RLS por workspace_id + role. |
| **Validação necessária** | Teste por role: Manager não acessa admin. Reviewer não faz upload. Staff não edita. |

---

### D-016 — Storage definitivo

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Decisão** | Supabase Storage privado com URLs assinadas para MVP e piloto. |
| **Limite** | 100 MB por arquivo. |
| **Reavaliar** | S3/R2 somente se custo, compliance ou performance exigirem. |
| **Alternativas recusadas** | S3/R2 agora — overhead desnecessário. Storage local — sem redundância. |
| **Impacto em código** | `MAX_UPLOAD_SIZE = 100 * 1024 * 1024` configurável via env. |
| **Validação necessária** | Upload de 99 MB aceito. Upload de 101 MB rejeitado com mensagem clara. |

---

### D-017 — Limites de upload e abuso

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Formatos aceitos** | PDF, DOCX, CSV, XLSX, TXT, EPUB e outros formatos comuns em empresas. |
| **Rate limit** | Sem limite formal no piloto (volume controlado internamente). |
| **Nota** | EPUB requer parser adicional — registrar como item de implementação separado. |
| **Impacto em código** | Magic bytes check + MIME check obrigatórios para todos os tipos. Parser EPUB a implementar. |
| **Validação necessária** | MIME falso rejeitado. Arquivo com extensão incorreta rejeitado. |

---

### D-018 — Versionamento de schemas e prompts

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Schema** | Nova versão cria `fact_type@2.0.0`. Fatos publicados com schema antigo permanecem válidos. Reprocessamento é opcional. |
| **Auditoria** | `schema_version` + `prompt_version` obrigatórios em todo output de extração. |
| **Alternativas recusadas** | Reprocessar tudo ao mudar schema — custo e risco desnecessários. Bloquear mudança — impede evolução. |
| **Impacto em código** | `extracted_facts` e `business_rules` devem ter colunas `schema_version` e `prompt_version`. |
| **Validação necessária** | `diagnose_source` mostra `schema_version` e `prompt_version` por fato. |

---

### D-019 — Interface de consulta

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Interface** | Tabela com filtros sobre `published_facts` + campo de pergunta em linguagem natural. |
| **Answer states** | `valid_answer` / `not_found` / `conflicting_sources` / `needs_human_validation` — todos implementados. |
| **Consulta** | Nunca usa fatos não publicados. |
| **Alternativas recusadas** | Só tabela — limita descoberta. Só linguagem natural — complexidade sem estrutura. |
| **Impacto em código** | Endpoint `/query` classifica intenção, busca apenas `published_facts`, retorna `answer_state` + `audit_id`. |
| **Validação necessária** | Consulta sem dados publicados retorna `not_found`. Consulta com conflito retorna `conflicting_sources`. |

---

### D-020 — Backup, restore e disaster recovery

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Data** | 2026-05-12 |
| **Backup** | Automático do Supabase. Dependência documentada. |
| **RPO** | 24 horas (piloto interno). |
| **RTO** | Indefinido para piloto. Formalizar antes de produção. |
| **Alternativas recusadas** | RPO 4h/RTO 2h — não necessário para piloto. Script custom — overhead sem benefício no piloto. |
| **Impacto em docs** | Runbook de restore deve ser testado em projeto Supabase separado antes de produção. |
| **Validação necessária** | Restore testado antes de qualquer deploy em produção. |

---

## P3 — Decisões de evolução

### D-021 — Conectores externos

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Decisão** | Pós-piloto, somente se necessidade real for comprovada pelos usuários do piloto. |

---

### D-022 — Automação de resposta ao cliente final

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Decisão** | Fora do escopo do produto. O produto compila conhecimento, não responde clientes. |

---

### D-023 — Troca de arquitetura de filas

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Decisão** | Celery/Redis mantidos. Reavaliar somente se virarem limitante real de volume, custo ou operação. |

---

## Confirmadas

### C-001 — Supabase como DB/Auth/Storage do MVP

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Decisão** | Sim. Supabase real passou smoke full. Definitivo para MVP e piloto. |

---

### C-002 — Filesystem broker como fallback local

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Decisão** | Permitido apenas para smoke local sem Redis. Explicitamente proibido para ambiente compartilhado. |

---

### C-003 — Smoke full como gate obrigatório

| Campo | Valor |
|-------|-------|
| **Status** | decided |
| **Decisão** | Smoke full deve passar antes de qualquer piloto ou deploy. Relatórios JSON arquivados por rodada. |

---

## Itens de implementação identificados nesta sessão

| Item | Origem | Prioridade |
|------|--------|-----------|
| Workers apontam para endpoint local (Ollama) via env | D-008 | P0 antes do piloto |
| Parser EPUB a implementar | D-017 | P1 |
| Queries de métricas do piloto (approval_rate, edit_rate, etc.) | D-006 | P1 |
| Colunas `schema_version` e `prompt_version` em `extracted_facts` | D-018 | P1 |
| Script de deleção de arquivos originais por workspace | D-004 | P2 |
| Runbook de restore testado em projeto Supabase separado | D-020 | P2 (antes de produção) |
