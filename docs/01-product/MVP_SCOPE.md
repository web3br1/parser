# MVP_SCOPE.md — Escopo do MVP

## O que o MVP entrega

- Upload de PDF textual, DOCX, XLSX, CSV, TXT, texto colado
- Validação de qualidade de entrada com rejeição explícita e log de motivo
- Deduplicação por hash — documento idêntico não reprocessado
- Chunking semântico antes da classificação
- Normalização determinística antes do LLM (moeda, horário, data, percentual, dias)
- Classificação por chunk com score de confiança
- Extração com schema fixo e versão — output livre proibido
- Roteamento: fatos → extracted_facts, regras → business_rules
- Unknown queue para chunks não classificáveis ou com injection suspeita
- Validação humana por bloco com histórico em validation_events
- Detecção de contradições numéricas entre dados approved
- Resolução de conflito com hierarquia de autoridade (official > normal > informal)
- Camada de publicação: published_facts e published_rules como superfície de consulta
- Respostas com answer_state formal — nunca improvisação quando dado ausente
- Audit log versionado: schema_version, prompt_version_hash, model_version por resposta
- Permissões por ação além do isolamento de workspace
- RLS no Postgres desde o dia 1
- Log de tokens e custo por workspace com limite por plano
- Unsupported sources queue (PDFs escaneados) para análise de demanda

## Fora do escopo do MVP

- OCR para PDFs escaneados
- URL pública controlada (V1)
- Conectores oficiais: Google Sheets, Instagram, Google Business etc. (V2)
- Contradições semânticas via embedding
- Rule engine com avaliação em código (DSL)
- Integração com WhatsApp, CRM ou sistema externo
- RAG vetorial (pgvector — Fase 2)
- Dashboard analítico avançado
- Fine-tuning próprio
- App mobile
- Sistema de billing

## Critérios de aceite

Ver `/docs/07-qa/ACCEPTANCE_CRITERIA.md`.

## Prazo realista

3 a 5 semanas com um implementador focado, sem escopo adicional.

## Roadmap pós-MVP

| Versão | Conteúdo |
|--------|----------|
| V1 | URL pública controlada + importação assistida (CSV/JSON exportados) + contradições semânticas + rule engine em código |
| V2 | Conectores oficiais: Google Sheets, Drive, Business Profile, Instagram, YouTube, WhatsApp Business |
| V3 | Monitoramento contínuo de fontes externas + detecção de mudança |
| Fase 2 (produto) | Assistente operacional: FAQ automático, scripts comerciais, sugestões de resposta |
| Fase 3 (produto) | Automação com aprovação humana: follow-up, alertas, atualização de CRM |

