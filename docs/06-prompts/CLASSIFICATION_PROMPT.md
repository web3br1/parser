# CLASSIFICATION_PROMPT.md — Prompt de Classificação MVP

## Prompt de classificação por chunk

```text
Você é um classificador de conhecimento empresarial.
Classifique o trecho abaixo em zero, uma ou mais classes do MVP.
Responda apenas com JSON válido. Sem texto antes ou depois do JSON.

Classes disponíveis:
- service_price: preço explícito de serviço ou produto
- business_hours: horário de funcionamento por dia ou exceção
- payment_method: forma de pagamento aceita ou recusada
- discount_rule: regra condicional de desconto
- cancellation_policy: política de cancelamento com prazo ou penalidade
- contact_info: telefone, e-mail, endereço ou qualquer dado de contato
- faq_item: pergunta e resposta frequente, instrução de uso ou política explicada em prosa
- unknown: não foi possível classificar com confiança

Trecho:
---
{chunk_text}
---

Responda APENAS com JSON no formato:
{
  "classifications": [
    {
      "classification": "<classe>",
      "confidence": <número entre 0.0 e 1.0>,
      "reason": "<uma frase explicando a classificação>"
    }
  ]
}
```

## Threshold de confiança

- `confidence >= 0.75` + classification em `ALLOWED_CLASSIFICATIONS` → prossegue para extração
- A lista canônica de classifications é definida em `worker_classification/classifier.py`
- `confidence < 0.75` → vai para `unknown_facts_queue`
- `classification == "unknown"` → vai para `unknown_facts_queue`

## Regra de múltiplos tipos

Um chunk pode gerar `0..N` facts, `0..N` rules e `0..N` unknowns. O classificador pode retornar múltiplas classificações quando o trecho contém dados diferentes no mesmo bloco.
