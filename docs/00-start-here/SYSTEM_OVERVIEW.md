# SYSTEM_OVERVIEW.md — Visão Geral do Sistema

## O que este sistema faz

Transforma informações brutas de empresas em fontes de verdade estruturadas, validadas por humanos e consultáveis por IA.

**Problema resolvido:** empresas pequenas têm conhecimento espalhado em PDFs, planilhas, WhatsApp e na cabeça do dono. Isso gera atendimento inconsistente, retrabalho e automações frágeis.

**Solução:** camada de organização, validação e recuperação de verdades empresariais. O chatbot ou automação vem depois, como interface sobre esta camada.

---

## O que este sistema NÃO é

- Não é chatbot. Chatbot é interface futura sobre esta camada.
- Não é RAG genérico. Cada tipo de dado tem storage adequada.
- Não é substituto de validação humana em dados críticos.
- Não é ERP, CRM ou sistema de automação.

---

## Fluxo canônico

```
Input messy
  ↓
Input quality gate       ← rejeita antes de gastar tokens (ADR-001)
  ↓
Normalização determinística ← antes de qualquer schema (ADR-008)
  ↓
Chunking semântico       ← segmenta antes de classificar (ADR-002)
  ↓
Classificação por chunk  ← tipo por bloco, não por documento
  ↓
Extração com schema fixo ← nunca output livre (ADR-002)
  ↓
Roteamento               ← facts vs regras (ver PIPELINE.md)
  ↓
Unknown queue            ← tipos desconhecidos não entram no banco (ADR-003)
  ↓
Validação humana         ← nada crítico sem aprovação (ADR-004)
  ↓
published_facts / published_rules ← única superfície de consulta (ADR-011)
  ↓
LLM como interface       ← interpreta, não cria verdade
  ↓
Resposta com answer_state formal (ADR-010) + audit log versionado (ADR-006)
```

---

## Separação de camadas

| Camada | Conteúdo | Storage |
|--------|----------|---------|
| Dados brutos | Arquivos originais imutáveis | File storage (R2/Supabase) |
| Dados estruturados | Fatos extraídos e validados | PostgreSQL `extracted_facts` |
| Regras | Políticas e condições validadas | PostgreSQL `business_rules` |
| Publicados | Superfície de consulta — published + sem supersede + dentro da validade | Views `published_facts` / `published_rules` |
| Conhecimento vetorial | Políticas textuais longas | pgvector (Fase 2) |
| Dados dinâmicos | Preço, estoque, prazo | PostgreSQL — consulta direta, nunca RAG |
| Decisão | LLM interpreta com base nas camadas acima | Sem persistência própria |

---

## Camadas de ingestão por versão

| Versão | Fontes aceitas |
|--------|----------------|
| MVP | Upload manual: PDF textual, DOCX, XLSX, CSV, TXT, texto colado |
| V1 | + URL pública controlada (depth=1, sem JS, robots.txt respeitado) + importação assistida (CSV/JSON exportados) |
| V2 | + Conectores oficiais: Google Sheets, Google Drive, Google Business Profile, Instagram/Facebook Graph API, YouTube, WhatsApp Business |
| V3 | + Monitoramento contínuo de mudança em fontes externas |

Toda fonte externa passa por quality gate, classificação de confiabilidade e validação humana antes de virar verdade operacional. Nunca scraping irrestrito.

---

## Confiabilidade de fonte

Cada fonte recebe `source_reliability` que impacta resolução de conflitos e disclaimer nas respostas:

| Tipo | Exemplos | Confiabilidade |
|------|----------|----------------|
| `official_document` | Contrato assinado, política aprovada | Alta |
| `official_website` | Site institucional | Média-alta |
| `official_api` | Google Business, WhatsApp Business | Média-alta |
| `internal_spreadsheet` | Planilha de preços interna | Média |
| `marketing_content` | Post patrocinado | Média-baixa |
| `social_post` | Instagram orgânico | Baixa |
| `review` | Google Reviews | Muito baixa |
| `conversation` | DM, WhatsApp | Baixa |

Conflito entre tipos com diferença de 2+ níveis → fonte superior vence automaticamente.
Mesmo nível → revisão humana obrigatória.

---

## Versionamento por camada

Toda resposta deve ser reproduzível. Cada fato armazena:

| Campo | O que versiona |
|-------|----------------|
| `schema_version` | Versão do Pydantic schema usado na extração |
| `prompt_version` | Versão/hash do prompt usado |
| `model_provider` / `model_name` | Provedor e modelo de IA |
| `supersedes` / `superseded_by` | Cadeia de substituição de facts/rules |
| `source_version` | Inteiro incrementado a cada re-upload |

Audit logs registram todas as versões usadas em cada resposta.

---

## Estados formais de resposta

O sistema nunca improvisa quando a fonte não cobre a pergunta:

| Estado | Resposta ao usuário |
|--------|---------------------|
| `valid_answer` | Resposta normal com fonte publicada |
| `partial_answer` | Resposta parcial com indicação do que falta |
| `not_found` | "Ainda não temos essa informação validada." |
| `conflicting_sources` | "Há um conflito não resolvido. Consulte o responsável." |
| `needs_human_validation` | "Essa informação ainda não foi validada por um humano." |

---

## Nicho inicial

**Genérico:** sistema agnóstico de nicho por padrão.
**Prioritário no MVP:** estúdios de estética (SP e RJ).

Extensão para outros nichos: criar arquivos em `/docs/04-data/schemas/{nicho}/`.
Nunca modificar código core para adaptação de nicho — extensão via configuração.

---

## Princípios não-negociáveis

1. Sem schema fixo → não extrai
2. Sem validação humana → não responde ao cliente
3. Sem audit log versionado → não executa
4. Dado dinâmico → nunca via RAG
5. Unknown → fila de revisão, nunca banco estruturado
6. Fonte externa → quality gate + confiabilidade + validação antes de publicar
7. LLM classifica, extrai e interpreta — nunca cria verdade sozinho
8. Todo input é tratado como hostil (ver SECURITY.md)

