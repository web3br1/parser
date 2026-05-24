# MVP_SCOPE.md - Escopo do MVP

## O que o MVP entrega

- Upload de PDF textual, DOCX, XLSX, CSV, TXT e texto colado.
- Validacao de qualidade de entrada com rejeicao explicita e log de motivo.
- Deduplicacao por hash para evitar reprocessar documento identico.
- Chunking semantico antes da classificacao.
- Normalizacao deterministica antes do LLM para moeda, horario, data,
  percentual e dias.
- Classificacao por chunk com score de confianca.
- Extracao com schema fixo e versao; output livre e proibido.
- Roteamento: fatos para `extracted_facts`, regras para `business_rules`.
- Unknown queue para chunks nao classificaveis ou com injection suspeita.
- Validacao humana por bloco com historico em `validation_events`.
- Deteccao de contradicoes numericas entre dados aprovados.
- Resolucao de conflito com hierarquia de autoridade.
- Camada de publicacao: `published_facts` e `published_rules`.
- Export `context_bundle.v1` com fontes publicadas, fatos publicados, regras
  publicadas, evidencias referenciadas, readiness e hash de integridade.
- Audit log de exportacao com `audit_logs.action = 'context_bundle.export'`.
- Permissoes por acao alem do isolamento de workspace.
- RLS no Postgres desde o dia 1.
- Log de tokens e custo por workspace com limite por plano.
- Unsupported sources queue para PDFs escaneados e analise de demanda.
- Runtime local reproduzivel via Docker para piloto e desenvolvimento.
- Pilot Test console interno para validar fluxo, nao para conversar com usuario
  final.

## Fora do escopo do MVP

- Chatbot final ou tela de conversa para cliente externo.
- OCR para PDFs escaneados.
- URL publica controlada (V1).
- Conectores oficiais: Google Sheets, Instagram, Google Business etc. (V2).
- Contradicoes semanticas via embedding.
- Rule engine com avaliacao em codigo (DSL).
- Integracao com WhatsApp, CRM ou sistema externo.
- Hosted vector database.
- RAG vetorial como fonte primaria de verdade.
- Dashboard analitico avancado.
- Fine-tuning proprio.
- App mobile.
- Sistema de billing.

## Criterios de aceite

Ver `/docs/07-qa/ACCEPTANCE_CRITERIA.md`.

## Prazo realista

3 a 5 semanas com um implementador focado, sem escopo adicional.

## Roadmap pos-MVP

| Versao | Conteudo |
|--------|----------|
| V1 | URL publica controlada, importacao assistida CSV/JSON, contradicoes semanticas e rule engine em codigo |
| V2 | Conectores oficiais: Google Sheets, Drive, Business Profile, Instagram, YouTube, WhatsApp Business |
| V3 | Monitoramento continuo de fontes externas e deteccao de mudanca |
| Consumidor externo | Chatbot/assistente operacional que importa `context_bundle.v1` |
| Automacao externa | Follow-up, alertas e CRM em projeto separado, com aprovacao humana |
