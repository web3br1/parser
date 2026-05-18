# TEST_CASES.md — Casos de Teste MVP

> Para cada caso: input → comportamento esperado → output esperado.
> Exemplos de arquivo real estão em `/examples/`.

## Quality Gate

### TC-001: PDF textual válido
- Input: PDF com texto selecionável, >800 chars, linhas normais
- Esperado: `source_quality_reports.is_processable = true`

### TC-002: PDF escaneado
- Input: PDF com <800 chars extraíveis
- Esperado: `is_processable = false`, `detected_issues` contém `low_text_volume`

### TC-003: PDF com layout fragmentado
- Input: PDF legado onde >60% das linhas têm menos de 3 tokens
- Esperado: `detected_issues` contém `fragmented_layout`

### TC-004: Documento duplicado
- Input: mesmo arquivo enviado duas vezes
- Esperado: segundo upload retorna `source_id` existente, não reprocessa

## Classificação

### TC-005: Horário explícito
- Input: "Atendemos segunda das 9h às 18h."
- Esperado: `classifications[0].classification = "business_hours"` e `confidence >= 0.75`

### TC-006: Texto ambíguo
- Input: "Conforme combinado, o atendimento será feito normalmente."
- Esperado: `unknown` ou confidence `< 0.75`
- Consequência: vai para `unknown_facts_queue`

### TC-007: Chunk misto
- Input: "Segunda das 9h às 18h. Aceitamos Pix. Limpeza custa R$120."
- Esperado: classificações para `business_hours`, `payment_method` e `service_price`

## Extração

### TC-008: business_hours simples
- Input chunk: "Segunda: 9h às 18h"
- Esperado:
```json
{
  "status": "ok",
  "fact_type": "business_hours",
  "data": {
    "day_of_week": "mon",
    "open_time": "09:00",
    "close_time": "18:00",
    "is_closed": false,
    "special_case": null
  },
  "evidence_span": {
    "quote": "Segunda: 9h às 18h",
    "char_start": null,
    "char_end": null
  },
  "ambiguities": []
}
```

### TC-009: discount_rule vaga
- Input chunk: "Clientes antigos têm desconto especial no Pix."
- Esperado: `status = "failed"` ou envio para revisão manual
- Esperado: ambiguities contém perguntas sobre definição de cliente antigo e valor do desconto
- Proibido: inventar `discount_percentage` ou `discount_fixed`

### TC-010: service_price fixo
- Input chunk: "Limpeza de pele custa R$120."
- Esperado: `service_price` com `price_type = "fixed"`, `price_amount = 120`, `currency = "BRL"`

### TC-011: Extração com falha de schema
- Input: resposta do LLM fora do schema esperado após retry
- Esperado: chunk vai para `unknown_facts_queue`, não para `extracted_facts`

## Validação e Publicação

### TC-012: Approve não publica
- Setup: fato com `status = "extracted"`
- Ação: `approve_fact(fact_id)`
- Esperado: `status = "approved"` e não aparece em `published_facts`

### TC-013: Publish torna consultável
- Setup: fato com `status = "approved"`
- Ação: `publish_fact(fact_id)`
- Esperado: `status = "published"` e aparece em `published_facts`

### TC-014: Aprovação gera validation_event
- Ação: usuário aprova fato
- Esperado: registro em `validation_events` com `action = "approved"`

## Contradições

### TC-015: Contradição numérica detectada
- Setup: dois facts `service_price` published com mesmo `service_name` e preços diferentes
- Ação: `mark_fact_contradiction(...)`
- Esperado: registro em `contradictions`; facts envolvidos ficam `status = "conflicted"`

### TC-016: Sem contradição em dados não aprovados/publicados
- Setup: dois fatos `extracted` com valores conflitantes
- Esperado: nenhuma contradição publicada para consulta

## Auditoria

### TC-017: Toda consulta gera query_audit
- Ação: consulta interna
- Esperado: registro em `query_audits` com `answer_state`, `facts_used`, `rules_used`, `sources_used`

### TC-018: used_unvalidated_data bloqueia resposta
- Setup: apenas dado `extracted` disponível
- Esperado: `answer_state = "needs_human_validation"` e `used_unvalidated_data = false` na resposta ao usuário

## Normalização

### TC-019: Moeda BR
- Input: `R$ 120`, `120 reais`
- Esperado: `120 BRL`

### TC-020: Percentual
- Input: `10%`
- Esperado: `10`, não `0.10`

### TC-021: Horário vago
- Input: `fim do dia`
- Esperado: `18:00`
