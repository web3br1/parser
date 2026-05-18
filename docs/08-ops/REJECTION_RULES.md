# REJECTION_RULES.md — O Que Nunca Pode Entrar no Produto

> Qualquer PR, proposta ou implementação que viole estas regras deve ser rejeitada imediatamente.

---

## Regras de rejeição absoluta

### Sobre dados e extração

- ❌ Output livre de LLM armazenado no banco estruturado sem validação de schema
- ❌ Preço, prazo ou estoque respondidos via RAG vetorial
- ❌ Dado não-aprovado em resposta ao cliente
- ❌ Chunk unknown processado como se tivesse tipo conhecido
- ❌ Schema genérico criado para acomodar múltiplos tipos diferentes

### Sobre validação

- ❌ Resposta crítica ao cliente sem fonte aprovada
- ❌ Consulta sem geração de `audit_log`
- ❌ Mudança de estado de validação sem registro em `validation_events`
- ❌ "Depois vemos auditoria" — auditoria é requisito, não feature

### Sobre pipeline

- ❌ Classificação por documento inteiro (deve ser por chunk)
- ❌ Extração sem chunking prévio
- ❌ OCR para PDFs escaneados no MVP (ver ADR-005)
- ❌ Processamento de arquivo que falhou no quality gate

### Sobre arquitetura

- ❌ Nome de modelo de IA hardcodado no código (usar variável de ambiente)
- ❌ Query de aplicação sem filtro por workspace_id
- ❌ RLS desabilitado para "simplificar"
- ❌ Tabela nova com workspace_id sem RLS configurado

### Sobre escopo

- ❌ Integração com WhatsApp, CRM ou sistema externo no MVP
- ❌ Contradição semântica via embedding no MVP
- ❌ Rule engine com avaliação em código (DSL) no MVP
- ❌ Dashboard analítico complexo no MVP

---

## Frases que indicam problema de arquitetura

Se um implementador usar qualquer uma destas frases, questionar antes de aprovar:

- "coloca tudo no vector database"
- "o LLM resolve as regras"
- "não precisa de validação humana aqui"
- "preço pode ir no RAG por enquanto"
- "depois vemos auditoria"
- "vamos simplificar e não versionar"
- "contradição é problema do usuário"
- "vamos fazer o chatbot primeiro e estruturar depois"
- "só hardcodei o modelo por enquanto"

