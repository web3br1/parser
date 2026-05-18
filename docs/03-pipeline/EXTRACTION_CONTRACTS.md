# EXTRACTION_CONTRACTS.md — Contratos de Entrada e Saída MVP

Este arquivo segue os contratos fechados em `MVP_DECISIONS.md`, `SCHEMA_REGISTRY.md` e `EXTRACTION_PROMPTS.md`.

## Contrato de classificação

Entrada:

```json
{
  "chunk_id": "chk_001",
  "text": "Atendemos de segunda a sexta das 9h às 18h. Aceitamos Pix."
}
```

Saída esperada:

```json
{
  "classifications": [
    {
      "classification": "business_hours",
      "confidence": 0.95,
      "reason": "Descreve horário de funcionamento com dias e horários explícitos."
    },
    {
      "classification": "payment_method",
      "confidence": 0.91,
      "reason": "Declara forma de pagamento aceita."
    }
  ]
}
```

Baixa confiança:

```json
{
  "classifications": [
    {
      "classification": "unknown",
      "confidence": 0.42,
      "reason": "Não foi possível identificar o tipo com confiança suficiente."
    }
  ]
}
```

## Contrato de extração

Entrada:

```json
{
  "chunk_id": "chk_001",
  "fact_type": "business_hours",
  "text": "Segunda: 9h às 18h."
}
```

Saída esperada:

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

Regra de desconto vaga:

```json
{
  "status": "failed",
  "fact_type": "discount_rule",
  "data": null,
  "evidence_span": {
    "quote": "Clientes antigos têm desconto especial no Pix.",
    "char_start": null,
    "char_end": null
  },
  "ambiguities": [
    "O que define cliente antigo?",
    "Qual é o percentual ou valor fixo do desconto?"
  ]
}
```

Falha de schema:

```json
{
  "status": "failed",
  "fact_type": "service_price",
  "reason": "schema_validation_failed",
  "raw_response": "..."
}
```

## Contrato de consulta

Entrada:

```json
{
  "workspace_id": "ws_001",
  "query": "Cliente pode ter desconto no Pix?"
}
```

Saída com resposta válida:

```json
{
  "audit_id": "aud_001",
  "answer": "Sim. Para esse caso, pode aplicar 5% de desconto no Pix.",
  "answer_state": "valid_answer",
  "rules_used": ["rule_123"],
  "facts_used": ["fact_456"],
  "sources_used": ["src_001"],
  "confidence": 0.92,
  "used_unvalidated_data": false
}
```

Saída sem dado publicado:

```json
{
  "audit_id": "aud_002",
  "answer": "Não encontrei essa informação nas fontes validadas.",
  "answer_state": "not_found",
  "rules_used": [],
  "facts_used": [],
  "sources_used": [],
  "confidence": 0.0,
  "used_unvalidated_data": false
}
```
