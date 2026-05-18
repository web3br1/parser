# EXTRACTION_PROMPTS.md — Prompts de Extração MVP

Cada extração deve responder somente JSON válido e deve incluir evidência textual.

## Template Base

```
Você é um extrator de informações estruturadas para sistemas empresariais.
Extraia apenas informações explicitamente presentes no trecho.

REGRAS OBRIGATÓRIAS:
- Responda APENAS com JSON válido.
- Nunca invente valores.
- Se um campo não estiver presente, use null quando o schema permitir.
- Não normalize por LLM. Preserve valores extraídos; a normalização determinística roda depois.
- Inclua evidence_span.quote com o menor trecho textual que sustenta a extração.
- Se não houver evidência textual clara, retorne status "failed".

Trecho:
---
{chunk_text}
---

Responda no formato:
{
  "status": "ok | failed",
  "fact_type": "<fact_type>",
  "data": {schema_data},
  "evidence_span": {
    "quote": "trecho literal usado como evidência",
    "char_start": null,
    "char_end": null
  },
  "ambiguities": []
}
```

## service_price

```json
{
  "service_name": "nome do serviço",
  "price_amount": 120,
  "currency": "BRL",
  "price_type": "fixed | starting_from | range | unknown",
  "min_price": null,
  "max_price": null,
  "valid_from": null,
  "valid_until": null
}
```

Regras:

- Use `fixed` quando houver valor único.
- Use `starting_from` para "a partir de".
- Use `range` quando houver mínimo e máximo.
- Nunca converter texto vago em preço.

## business_hours

```json
{
  "day_of_week": "mon | tue | wed | thu | fri | sat | sun",
  "open_time": "HH:mm ou null",
  "close_time": "HH:mm ou null",
  "is_closed": false,
  "special_case": null
}
```

Regras:

- Gere um item por dia quando o texto cobrir múltiplos dias.
- Use `is_closed: true` quando o texto declarar fechamento.
- Horários vagos devem ficar null e ir para ambiguities.

## payment_method

```json
{
  "method": "pix | cash | credit | debit | bank_transfer | unknown",
  "accepted": true,
  "conditions": null
}
```

Regras:

- Extraia apenas métodos explicitamente aceitos ou recusados.
- Condições como parcelamento ou taxa devem ir em `conditions`.

## discount_rule

```json
{
  "condition": {
    "payment_method": null,
    "day_of_week": null,
    "min_value": null
  },
  "action": {
    "discount_percentage": null,
    "discount_fixed": null
  }
}
```

Regras:

- Requer condição e ação.
- Desconto vago como "condição especial" deve retornar `failed` ou ambiguities, sem inventar valor.
- Percentual deve ser número, por exemplo `10` para 10%.

## cancellation_policy

```json
{
  "notice_required_hours": 24,
  "penalty_percentage": null,
  "penalty_fixed": null
}
```

Regras:

- Prazo deve ser explícito ou convertível deterministicamente.
- Penalidade pode ser percentual ou valor fixo.

## Sufixo de Retry

```
IMPORTANTE: Sua resposta anterior não foi JSON válido ou não seguiu o schema.
Responda EXCLUSIVAMENTE com JSON. Sem markdown, sem explicações.
Comece com { e termine com }.
```

## rule_evaluation

```
Com base nas regras publicadas abaixo, determine qual se aplica à situação descrita.
Use apenas regras fornecidas. Não use conhecimento externo.

Situação: {query_context}
Regras publicadas: {rules_json}

Responda:
{
  "matched_rule_ids": ["ids das regras que se aplicam"],
  "decision": "discount_allowed | discount_denied | policy_applies | insufficient_information",
  "explanation": "explicação curta baseada nas regras",
  "missing_information": [],
  "confidence": 0.0
}
```
