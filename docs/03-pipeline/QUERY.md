# QUERY.md - Consulta auditavel interna

> Diagnostic/internal reference. The product boundary for the current repo is
> `context_bundle.v1`; the end-user chatbot lives in the external consumer
> project. Use `CONTEXT_BUNDLE.md` as the integration contract.

Este documento define o contrato completo do endpoint `/query` do Context Compiler.
A consulta nao e um chat livre. Ela e a ultima etapa do compilador de conhecimento:

```text
upload -> parse -> classify -> extract -> review -> publish -> query
```

O `/query` so pode responder a partir de dados publicados, validos, nao
superseded e pertencentes ao workspace atual.

Estado implementado no MVP atual: a resposta e montada por fallback
deterministico, sem chamada de LLM. Campos de modelo ficam `null`, custo fica
`0.0`, e `audit_logs.metadata.usage_is_estimated=true`.

---

## Objetivo

Entregar uma consulta operacional, auditavel e controlada por budget, capaz de:

- responder perguntas usando apenas `published_facts` e `published_rules`;
- gerar `answer_state` formal em toda resposta;
- gerar `query_audits` e `audit_logs` para toda consulta;
- limitar contexto por tokens antes de chamar modelo;
- contabilizar tokens reais de entrada e saida apos a chamada;
- condensar contexto quando necessario sem criar informacao nova;
- retornar evidencias e IDs rastreaveis;
- impedir vazamento entre tenants;
- impedir uso de dados nao publicados, sensiveis ou pendentes.

Definicao curta de pronto:

```text
Uma pergunta enviada ao /query retorna uma resposta auditavel baseada somente
em conteudo publicado, com audit_id rastreavel ate facts, rules e sources usados.
```

---

## Endpoint

### Rota

```http
POST /workspaces/{workspace_id}/query
```

### Permissao

Qualquer membro ativo do workspace pode consultar dados publicados:

- `owner`
- `manager`
- `reviewer`
- `staff`

A role afeta o contexto visivel. `staff` nunca recebe campos sensiveis no
contexto nem na resposta.

### Request

```json
{
  "question": "Cliente pode ter desconto no Pix?",
  "mode": "answer",
  "max_output_tokens": 700,
  "include_evidence": true
}
```

Campos:

| Campo | Tipo | Obrigatorio | Regra |
|-------|------|-------------|-------|
| `question` | string | sim | 1..2000 caracteres |
| `mode` | string | nao | MVP: apenas `answer` |
| `max_output_tokens` | integer | nao | teto por request, limitado por config |
| `include_evidence` | boolean | nao | default `true` |

Requests vazios, gigantes ou com payload invalido retornam `422`.

### Response

```json
{
  "audit_id": "5f7c6e4d-0000-4000-9000-000000000001",
  "answer_state": "valid_answer",
  "answer": "Sim. Para pagamento via Pix, pode aplicar 5% de desconto.",
  "confidence": 0.92,
  "used_unvalidated_data": false,
  "facts_used": [
    "5f7c6e4d-0000-4000-9000-000000000010"
  ],
  "rules_used": [
    "5f7c6e4d-0000-4000-9000-000000000011"
  ],
  "sources_used": [
    "5f7c6e4d-0000-4000-9000-000000000020"
  ],
  "evidence": [
    {
      "source_id": "5f7c6e4d-0000-4000-9000-000000000020",
      "source_name": "politica_comercial.pdf",
      "evidence_span_id": "5f7c6e4d-0000-4000-9000-000000000030",
      "quote": "Pagamentos via Pix recebem 5% de desconto.",
      "page_number": 2,
      "sheet_name": null,
      "row_number": null
    }
  ],
  "missing_data": [],
  "warnings": [],
  "usage": {
    "model_provider": "openai",
    "model_name": "configured-query-model",
    "model_context_limit_tokens": 128000,
    "context_budget_tokens": 6000,
    "context_pack_tokens_estimated": 4210,
    "input_tokens": 5120,
    "output_tokens": 380,
    "estimated_cost": 0.001234
  }
}
```

Resposta sem dado publicado:

```json
{
  "audit_id": "5f7c6e4d-0000-4000-9000-000000000002",
  "answer_state": "not_found",
  "answer": "Nao encontrei essa informacao nas fontes validadas.",
  "confidence": 0.0,
  "used_unvalidated_data": false,
  "facts_used": [],
  "rules_used": [],
  "sources_used": [],
  "evidence": [],
  "missing_data": ["published_data"],
  "warnings": [],
  "usage": {
    "model_provider": null,
    "model_name": null,
    "model_context_limit_tokens": null,
    "context_budget_tokens": 6000,
    "context_pack_tokens_estimated": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "estimated_cost": 0.0
  }
}
```

---

## Answer states

Toda resposta deve retornar exatamente um `answer_state`.

| Estado | Quando usar | Usa LLM para responder? |
|--------|-------------|-------------------------|
| `valid_answer` | Ha dados publicados suficientes e sem conflito | sim, opcional |
| `not_found` | Nao ha dado publicado relevante | nao |
| `conflicting_sources` | Ha conflito aberto ou candidatos incompativeis | nao |
| `needs_human_validation` | Existem candidatos nao publicados relevantes, mas nada publicado suficiente | nao |
| `partial_answer` | Ha dados publicados relevantes, mas cobertura incompleta | no MVP: nao; V1: pode sintetizar com aviso |

Regra obrigatoria:

```text
Se answer_state != valid_answer, o modelo nao pode improvisar resposta.
```

Mensagens padrao:

| Estado | `answer` |
|--------|----------|
| `not_found` | `Nao encontrei essa informacao nas fontes validadas.` |
| `conflicting_sources` | `Encontrei fontes publicadas conflitantes. E necessario resolver o conflito antes de responder.` |
| `needs_human_validation` | `Existe informacao relacionada, mas ela ainda nao foi validada por revisao humana.` |
| `partial_answer` | `Encontrei apenas parte da informacao nas fontes validadas.` |

---

## Fluxo tecnico

```text
POST /workspaces/{workspace_id}/query
  -> autenticar usuario
  -> validar membership e role
  -> validar question
  -> classificar intencao
  -> buscar candidatos publicados
  -> buscar candidatos pendentes apenas para estado, nunca para resposta
  -> detectar conflito
  -> ranquear candidatos publicados
  -> calcular token budget
  -> montar context_pack
  -> condensar contexto se necessario
  -> decidir answer_state
  -> se valid_answer: gerar resposta
  -> persistir query_audits
  -> persistir audit_logs
  -> persistir token_usage_log quando houver uso de modelo
  -> retornar resposta auditavel
```

---

## Fontes permitidas

A camada de consulta so pode ler conteudo operacional de:

- `published_facts`
- `published_rules`
- `published_sources`
- `evidence_spans`, apenas para evidencias dos itens usados

E proibido usar para resposta:

- `extracted_facts` diretamente;
- `business_rules` diretamente;
- chunks nao publicados;
- unknown queue;
- documentos originais;
- storage files;
- logs;
- dados de outro workspace;
- dados pendentes de revisao.

Excecao controlada:

- `extracted_facts` e `business_rules` podem ser consultados separadamente para
  decidir `needs_human_validation`, mas seus dados nao podem entrar no
  `context_pack`, na resposta ou em evidencias retornadas ao usuario.

---

## Classificacao de intencao

O MVP deve classificar a pergunta em uma intencao simples:

| Intencao | Exemplos | Superficie primaria |
|----------|----------|---------------------|
| `fact_lookup` | "Qual o preco do corte?" | `published_facts` |
| `rule_evaluation` | "Cliente tem desconto no Pix?" | `published_rules` + facts auxiliares |
| `business_hours` | "Abre no sabado?" | `published_facts` |
| `contact_lookup` | "Qual o telefone?" | `published_facts` |
| `faq_lookup` | "Como remarcar?" | `published_facts` |
| `unknown` | pergunta fora do dominio publicado | nenhuma |

No MVP, a classificacao pode ser heuristica e deterministica. LLM para
classificacao de intencao e permitido apenas se:

- houver budget configurado;
- tokens forem registrados;
- a saida for schema estruturado;
- falha cair para `unknown` ou busca ampla conservadora.

---

## Ranking de candidatos

O ranking existe para construir um contexto pequeno e util. Ele nao altera a
verdade publicada.

Estrategia atual:

```text
ranking_strategy = deterministic_v1
```

Sinais usados, nesta ordem:

1. match exato de entidade/servico explicito (`service`, `service_name`,
   `name`, `entity` ou `topic`);
2. match por tipo de fato/regra inferido pela intencao;
3. quantidade de matches lexicais entre pergunta e conteudo normalizado;
4. confidence do item;
5. recencia (`published_at`, depois `updated_at`, depois `created_at`);
6. `id` como desempate estavel.

Guardrails:

- nunca promover item de outro workspace;
- nunca promover item nao publicado;
- nunca usar source sem `status=published`;
- nunca promover item superseded;
- nunca promover item fora de validade;
- nunca esconder conflito por ranking.

---

## Token budget

O `/query` deve limitar contexto por tokens antes de chamar qualquer modelo.

Formula:

```text
model_context_limit_tokens
- system_prompt_tokens
- developer_prompt_tokens
- question_tokens
- answer_schema_tokens
- reserved_output_tokens
- safety_margin_tokens
= context_budget_tokens
```

Config recomendada:

```text
QUERY_MODEL=
QUERY_MODEL_PROVIDER=
QUERY_MODEL_CONTEXT_LIMIT_TOKENS=128000
QUERY_CONTEXT_BUDGET_TOKENS=6000
QUERY_MAX_OUTPUT_TOKENS=700
QUERY_SAFETY_MARGIN_TOKENS=1000
QUERY_MAX_CANDIDATE_FACTS=80
QUERY_MAX_CANDIDATE_RULES=40
QUERY_ENABLE_LLM_CONDENSATION=false
QUERY_ENABLE_LLM_ANSWER=true
```

Regras:

- o limite real e por tokens, nao por numero de rows;
- numero maximo de facts/rules e apenas guarda secundaria;
- o estimador de tokens deve ser especifico do provider/modelo quando possivel;
- fallback por caracteres deve ser conservador;
- `max_output_tokens` da chamada ao modelo e obrigatorio;
- se o contexto nao couber e a condensacao estiver desativada, retornar
  `partial_answer` ou reduzir candidatos deterministicamente.

Valores que devem entrar na resposta e na auditoria:

```json
{
  "model_context_limit_tokens": 128000,
  "context_budget_tokens": 6000,
  "context_pack_tokens_estimated": 4210,
  "input_tokens": 5120,
  "output_tokens": 380
}
```

---

## Context pack

O `context_pack` e o unico conteudo enviado ao modelo para resposta.

Formato canonico:

```json
{
  "workspace_id": "5f7c6e4d-0000-4000-9000-000000000100",
  "question": "Cliente pode ter desconto no Pix?",
  "facts": [
    {
      "id": "5f7c6e4d-0000-4000-9000-000000000010",
      "fact_type": "payment_method",
      "schema_version": "1.0.0",
      "content": {
        "payment_method": "pix",
        "accepted": true
      },
      "normalized_content": {
        "payment_method": "pix",
        "accepted": true
      },
      "source_id": "5f7c6e4d-0000-4000-9000-000000000020",
      "evidence_span_id": "5f7c6e4d-0000-4000-9000-000000000030",
      "confidence": 0.94
    }
  ],
  "rules": [
    {
      "id": "5f7c6e4d-0000-4000-9000-000000000011",
      "rule_type": "discount_rule",
      "schema_version": "1.0.0",
      "condition": {
        "payment_method": "pix"
      },
      "action": {
        "discount_percentage": 5.0
      },
      "source_id": "5f7c6e4d-0000-4000-9000-000000000020",
      "evidence_span_id": "5f7c6e4d-0000-4000-9000-000000000031",
      "confidence": 0.91
    }
  ],
  "sources": [
    {
      "id": "5f7c6e4d-0000-4000-9000-000000000020",
      "name": "politica_comercial.pdf",
      "source_type": "upload",
      "authority_level": "official"
    }
  ]
}
```

Regras:

- deve ser serializado de forma deterministica para hash;
- deve excluir campos sensiveis por role antes do calculo de tokens;
- deve conter IDs originais;
- deve conter apenas campos necessarios para responder;
- nao deve conter documentos integrais;
- nao deve conter chunks completos, exceto trechos de evidencia curtos quando
  `include_evidence=true`.

### Hash do context pack

O backend deve calcular:

```text
context_pack_hash = sha256(canonical_json(context_pack))
```

Esse hash entra em `audit_logs.metadata` e, se a tabela permitir no futuro, em
coluna propria de `query_audits`.

---

## Condensacao de contexto

Condensacao e parte do escopo de producao do `/query`. Ela existe para caber no
budget, reduzir custo e manter respostas auditaveis.

### Camada 1: condensacao deterministica

Sempre roda antes de qualquer chamada ao modelo.

Responsabilidades:

- deduplicar facts equivalentes;
- agrupar por `fact_type`, entidade, servico ou topico;
- remover campos irrelevantes para a intencao;
- preservar IDs, source IDs e evidence span IDs;
- ordenar por ranking;
- cortar pelo budget de tokens;
- registrar motivos de descarte.

Exemplo de `dropped_reasons`:

```json
[
  {
    "resource_type": "fact",
    "resource_id": "5f7c6e4d-0000-4000-9000-000000000040",
    "reason": "duplicate_normalized_content"
  },
  {
    "resource_type": "rule",
    "resource_id": "5f7c6e4d-0000-4000-9000-000000000041",
    "reason": "token_budget_exceeded"
  }
]
```

### Camada 2: condensacao por LLM

Permitida somente quando:

- o contexto publicado relevante excede o budget;
- `QUERY_ENABLE_LLM_CONDENSATION=true`;
- a chamada tem `max_output_tokens`;
- tokens sao registrados;
- a saida e validada por schema.

O modelo de condensacao nao responde a pergunta. Ele apenas reduz contexto.

Saida obrigatoria:

```json
{
  "kept_fact_ids": [
    "5f7c6e4d-0000-4000-9000-000000000010"
  ],
  "kept_rule_ids": [
    "5f7c6e4d-0000-4000-9000-000000000011"
  ],
  "summary_by_topic": [
    {
      "topic": "Desconto Pix",
      "summary": "Ha uma regra publicada que aplica 5% de desconto quando o pagamento e Pix.",
      "fact_ids": [
        "5f7c6e4d-0000-4000-9000-000000000010"
      ],
      "rule_ids": [
        "5f7c6e4d-0000-4000-9000-000000000011"
      ]
    }
  ],
  "dropped_reasons": []
}
```

Guardrails:

- a condensacao nao pode criar IDs;
- a condensacao nao pode alterar valores;
- a resposta final deve citar IDs originais, nao apenas o resumo;
- se a saida da condensacao for invalida, descartar e usar fallback
  deterministico.

---

## Geracao de resposta

Quando `answer_state = valid_answer`, o backend pode:

1. montar resposta deterministica; ou
2. chamar LLM para redigir resposta em linguagem natural.

Mesmo quando usa LLM, a resposta deve obedecer:

- nao usar conhecimento externo;
- nao responder fora do `context_pack`;
- nao expor campos sensiveis removidos;
- nao citar dados sem ID original;
- retornar confidence;
- retornar IDs usados;
- retornar aviso se houver cobertura parcial.

Prompt de resposta deve exigir JSON estruturado:

```json
{
  "answer": "string",
  "confidence": 0.0,
  "facts_used": ["uuid"],
  "rules_used": ["uuid"],
  "sources_used": ["uuid"],
  "missing_data": ["string"],
  "warnings": ["string"]
}
```

Validacao pos-modelo:

- todos os IDs retornados devem existir no `context_pack`;
- `confidence` deve estar entre 0 e 1;
- `answer` nao pode estar vazia para `valid_answer`;
- se o modelo citar ID inexistente, descartar resposta e usar fallback
  deterministico ou retornar erro tecnico seguro;
- nunca persistir chain-of-thought.

---

## Auditoria

Toda consulta relevante gera:

1. registro em `query_audits`;
2. registro em `audit_logs`;
3. registro em `token_usage_log` quando houver chamada de modelo.

### `query_audits`

Campos existentes:

| Campo | Valor |
|-------|-------|
| `workspace_id` | workspace da rota |
| `user_id` | usuario autenticado |
| `question` | pergunta original |
| `answer` | resposta final ou mensagem padrao |
| `answer_state` | estado formal |
| `facts_used` | UUIDs usados na resposta |
| `rules_used` | UUIDs usados na resposta |
| `sources_used` | UUIDs usados na resposta |
| `used_unvalidated_data` | sempre `false` no MVP |
| `confidence` | 0..1 |
| `model_provider` | provider usado, se houver |
| `model_name` | modelo usado, se houver |
| `prompt_version` | versao do prompt |
| `latency_ms` | latencia total |
| `token_input` | tokens reais de entrada |
| `token_output` | tokens reais de saida |
| `estimated_cost` | custo estimado |

### `audit_logs`

Registro recomendado:

```json
{
  "action": "query.answer",
  "resource_type": "query_audit",
  "resource_id": "query_audit_id",
  "input_hash": "sha256(question + context_pack_hash)",
  "output_hash": "sha256(answer_payload)",
  "metadata": {
    "answer_state": "valid_answer",
    "context_pack_hash": "sha256...",
    "context_budget_tokens": 6000,
    "context_pack_tokens_estimated": 4210,
    "retrieval_count": 37,
    "candidate_count": 37,
    "selected_count": 9,
    "ranking_strategy": "deterministic_v1",
    "facts_considered": ["fact-id-1"],
    "rules_considered": ["rule-id-1"],
    "facts_used": ["fact-id-1"],
    "rules_used": [],
    "condensation_used": false,
    "usage_is_estimated": true
  }
}
```

### Campos de auditoria que podem exigir migracao futura

A tabela `query_audits` atual cobre o minimo. Para producao completa, considerar
uma migracao futura com:

- `context_pack_hash text`;
- `retrieval_count integer`;
- `facts_considered uuid[]`;
- `rules_considered uuid[]`;
- `context_budget_tokens integer`;
- `context_pack_tokens_estimated integer`;
- `condensation_used boolean`;
- `condensation_model_provider text`;
- `condensation_model_name text`;
- `condensation_prompt_version text`;
- `condensation_input_tokens integer`;
- `condensation_output_tokens integer`;
- `dropped_reasons jsonb`.

Enquanto essa migracao nao existir, esses dados devem ir em `audit_logs.metadata`.

No MVP atual, `retrieval_count` e alias historico de `candidate_count`.
`candidate_count` conta facts e rules publicados relevantes apos filtro e
ranking. `selected_count` conta facts e rules efetivamente usados na resposta
ou context pack apos corte por budget. Em `conflicting_sources`, `selected_count`
e `0`, pois dados conflitantes nao entram no prompt/resposta.

---

## Token accounting

O sistema usa duas medicoes:

1. estimativa pre-chamada;
2. usage real retornado pelo provider.

### Pre-chamada

Usada para budget:

```text
estimated_input_tokens =
  prompt_tokens
  + question_tokens
  + context_pack_tokens_estimated
  + schema_tokens
```

Se `estimated_input_tokens + reserved_output_tokens` exceder o limite do modelo:

- reduzir candidatos deterministicamente;
- se habilitado, condensar contexto;
- se ainda exceder, retornar `partial_answer` ou erro seguro configurado.

### Pos-chamada

Fonte oficial para auditoria e custo:

- `query_audits.token_input`;
- `query_audits.token_output`;
- `token_usage_log.input_tokens`;
- `token_usage_log.output_tokens`;
- `estimated_cost`.

Se o provider nao retornar usage:

- usar estimativa conservadora;
- marcar `metadata.usage_is_estimated = true` em `audit_logs`;
- nao usar o valor estimado para billing definitivo sem revisao.

---

## Tratamento de conflitos

O `/query` deve bloquear resposta quando houver conflito relevante.

Conflito pode vir de:

- rows em `contradictions` com status aberto;
- facts publicados incompativeis para a mesma entidade/campo;
- regras publicadas incompativeis para a mesma condicao.

Resposta:

```json
{
  "answer_state": "conflicting_sources",
  "answer": "Encontrei fontes publicadas conflitantes. E necessario resolver o conflito antes de responder.",
  "confidence": 0.0,
  "facts_used": [],
  "rules_used": [],
  "sources_used": ["source_a", "source_b"],
  "warnings": ["conflict_requires_review"]
}
```

Dados conflitantes nao devem entrar no prompt de resposta.

---

## Dados pendentes de validacao

O endpoint pode verificar se existem dados nao publicados relacionados para
retornar `needs_human_validation`.

Regras:

- dados pendentes nunca entram no `context_pack`;
- dados pendentes nunca entram em `facts_used`, `rules_used` ou `evidence`;
- a resposta nao deve revelar conteudo pendente para `staff`;
- `used_unvalidated_data` deve permanecer `false`.

---

## Seguranca e privacidade

Regras obrigatorias:

- autenticar via JWT;
- validar membership por `workspace_id`;
- aplicar permissao por role;
- usar service role apenas no backend;
- nunca expor service role ao frontend;
- nunca depender apenas de filtro manual se RLS estiver disponivel;
- preservar `security_invoker = true` nas views publicadas;
- remover campos sensiveis antes do contexto;
- nao logar documentos integrais;
- nao logar prompt completo com dados sensiveis;
- nao retornar stack trace;
- nao retornar dados de outro tenant;
- nao permitir pergunta alterar regras de seguranca.

Campos sensiveis minimos:

```text
cost
margin
supplier_price
internal_notes
secret
token
credential
api_key
```

Para `staff`, esses campos devem ser removidos recursivamente de `content`,
`normalized_content`, `condition` e `action`.

---

## Observabilidade

Eventos de log recomendados:

| Evento | Nivel | Campos |
|--------|-------|--------|
| `query_received` | info | request_id, workspace_id, user_id |
| `query_retrieval_completed` | info | candidates, published_facts, published_rules |
| `query_context_budgeted` | info | budget, estimated_tokens, dropped_count |
| `query_condensation_completed` | info | used, input_tokens, output_tokens |
| `query_answer_completed` | info | answer_state, audit_id, latency_ms |
| `query_failed` | error | request_id, safe_error_code |

Nunca logar:

- pergunta junto com contexto completo;
- documento integral;
- prompt completo;
- secrets;
- tokens;
- resposta bruta do modelo antes de validacao.

---

## Erros HTTP

| Status | Quando |
|--------|--------|
| `401` | token ausente ou invalido |
| `403` | usuario nao e membro do workspace |
| `404` | workspace nao encontrado ou inacessivel |
| `422` | payload invalido |
| `429` | rate limit ou budget do plano excedido |
| `500` | falha tecnica segura |
| `503` | provider indisponivel quando LLM e necessario |

Erros tecnicos devem incluir `request_id`, nunca stack trace.

---

## Testes obrigatorios

### API

- sem bearer retorna `401`;
- usuario fora do workspace retorna `403`;
- payload invalido retorna `422`;
- membro `staff` consegue consultar;
- `staff` nao recebe campos sensiveis;
- `owner` e `manager` recebem auditoria completa.

### Publicacao

- consulta nao le `extracted_facts` para resposta;
- consulta nao le `business_rules` para resposta;
- facts `approved` nao aparecem;
- facts `published` aparecem;
- facts superseded nao aparecem;
- facts fora de validade nao aparecem;
- source deleted nao aparece.

### Answer state

- sem dado publicado retorna `not_found`;
- dado pendente relacionado retorna `needs_human_validation`;
- conflito relevante retorna `conflicting_sources`;
- dado parcial retorna `partial_answer`;
- dado suficiente retorna `valid_answer`.

### Context budget

- contexto abaixo do limite nao condensa;
- contexto acima do limite corta deterministicamente;
- contexto acima do limite com condensacao habilitada chama condensador;
- `context_pack_tokens_estimated <= context_budget_tokens`;
- `max_output_tokens` sempre e enviado ao provider;
- falha do estimador usa fallback conservador.

### Auditoria

- toda consulta cria `query_audits`;
- toda consulta cria `audit_logs`;
- `used_unvalidated_data=false` sempre;
- `facts_used`, `rules_used`, `sources_used` batem com resposta;
- `context_pack_hash` e reproduzivel;
- usage real do provider vai para `query_audits`;
- token usage vai para `token_usage_log` quando houver chamada de modelo.

### Tenant isolation

- pergunta em workspace A nunca retorna dado de workspace B;
- IDs retornados pertencem ao workspace da rota;
- tentativa de usar source/fact ID de outro workspace nao altera resultado.

### Modelo

- resposta com ID inventado e rejeitada;
- resposta com confidence fora de 0..1 e rejeitada;
- resposta vazia em `valid_answer` e rejeitada;
- provider sem usage marca usage estimado;
- timeout retorna erro seguro ou fallback configurado.

---

## Criterios de pronto

O `/query` esta pronto para MVP de producao quando:

- endpoint `POST /workspaces/{workspace_id}/query` existe;
- request e response usam schemas Pydantic;
- endpoint exige auth e workspace membership;
- busca operacional usa apenas `published_facts` e `published_rules`;
- estados `not_found`, `needs_human_validation`, `conflicting_sources`,
  `partial_answer` e `valid_answer` sao cobertos por testes;
- contexto e limitado por tokens antes de qualquer LLM;
- context pack e hashavel e auditavel;
- condensacao deterministica existe;
- condensacao por LLM e opcional, controlada por env e auditada;
- resposta por LLM, quando usada, e validada por schema;
- `query_audits` e criado em toda consulta;
- `audit_logs` e criado em toda consulta;
- token usage real e persistido quando provider retornar usage;
- `used_unvalidated_data=false` e garantido;
- campos sensiveis sao filtrados para `staff`;
- testes de tenant leak passam;
- logs nao contem documento integral nem prompt completo.

---

## Fora do MVP

Nao incluir no primeiro `/query` de producao:

- RAG vetorial com pgvector;
- busca em documentos originais;
- consulta publica externa;
- resposta automatica para cliente final;
- escrita em sistemas externos;
- tool calling;
- memoria conversacional;
- personalizacao por usuario final;
- streaming de resposta;
- explicacoes longas de raciocinio interno.

Esses itens podem entrar em V1/V2, mas nao sao necessarios para fechar o ciclo
tecnico do MVP.
