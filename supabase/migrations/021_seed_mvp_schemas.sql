insert into public.fact_type_schemas (
  fact_type,
  schema_version,
  status,
  json_schema,
  extraction_prompt,
  normalization_policy,
  validation_policy
)
values
(
  'service_price',
  '1.0.0',
  'active',
  '{
    "type": "object",
    "additionalProperties": false,
    "required": ["service_name", "price_type", "currency"],
    "properties": {
      "service_name": { "type": "string" },
      "price_amount": { "type": ["number", "null"] },
      "currency": { "type": "string", "enum": ["BRL"] },
      "price_type": { "type": "string", "enum": ["fixed", "starting_from", "range", "unknown"] },
      "min_price": { "type": ["number", "null"] },
      "max_price": { "type": ["number", "null"] },
      "valid_from": { "type": ["string", "null"], "format": "date-time" },
      "valid_until": { "type": ["string", "null"], "format": "date-time" }
    }
  }'::jsonb,
  'Extract service pricing information only when explicitly present in the source text.',
  '{"currency_default":"BRL","price_parser":"br_money"}'::jsonb,
  '{"requires_evidence_span":true,"human_approval_required":true}'::jsonb
),
(
  'business_hours',
  '1.0.0',
  'active',
  '{
    "type": "object",
    "additionalProperties": false,
    "required": ["day_of_week", "is_closed"],
    "properties": {
      "day_of_week": { "type": "string", "enum": ["mon","tue","wed","thu","fri","sat","sun"] },
      "open_time": { "type": ["string", "null"], "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$" },
      "close_time": { "type": ["string", "null"], "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$" },
      "is_closed": { "type": "boolean" },
      "special_case": { "type": ["string", "null"] }
    }
  }'::jsonb,
  'Extract business opening hours only when explicitly present.',
  '{"time_format":"HH:mm","timezone":"America/Sao_Paulo"}'::jsonb,
  '{"requires_evidence_span":true,"human_approval_required":true}'::jsonb
),
(
  'payment_method',
  '1.0.0',
  'active',
  '{
    "type": "object",
    "additionalProperties": false,
    "required": ["method", "accepted"],
    "properties": {
      "method": { "type": "string", "enum": ["pix","cash","credit","debit","bank_transfer","unknown"] },
      "accepted": { "type": "boolean" },
      "conditions": { "type": ["string", "null"] }
    }
  }'::jsonb,
  'Extract accepted payment methods and explicit conditions.',
  '{}'::jsonb,
  '{"requires_evidence_span":true,"human_approval_required":true}'::jsonb
),
(
  'discount_rule',
  '1.0.0',
  'active',
  '{
    "type": "object",
    "additionalProperties": false,
    "required": ["condition", "action"],
    "properties": {
      "condition": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "payment_method": { "type": ["string", "null"] },
          "day_of_week": { "type": ["string", "null"] },
          "min_value": { "type": ["number", "null"] }
        }
      },
      "action": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "discount_percentage": { "type": ["number", "null"] },
          "discount_fixed": { "type": ["number", "null"] }
        }
      }
    }
  }'::jsonb,
  'Extract discount rules only when condition and action are explicit.',
  '{"currency_default":"BRL","percent_parser":"br_percent"}'::jsonb,
  '{"requires_evidence_span":true,"human_approval_required":true}'::jsonb
),
(
  'cancellation_policy',
  '1.0.0',
  'active',
  '{
    "type": "object",
    "additionalProperties": false,
    "required": ["notice_required_hours"],
    "properties": {
      "notice_required_hours": { "type": "number" },
      "penalty_percentage": { "type": ["number", "null"] },
      "penalty_fixed": { "type": ["number", "null"] }
    }
  }'::jsonb,
  'Extract cancellation policy only when explicitly stated.',
  '{"relative_time_parser":"pt_br"}'::jsonb,
  '{"requires_evidence_span":true,"human_approval_required":true}'::jsonb
),
(
  'contact_info',
  '1.0.0',
  'active',
  '{
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "phone": { "type": ["string", "null"] },
      "email": { "type": ["string", "null"] },
      "address": { "type": ["string", "null"] },
      "website": { "type": ["string", "null"] },
      "whatsapp": { "type": ["string", "null"] },
      "contact_name": { "type": ["string", "null"] }
    }
  }'::jsonb,
  'Extract explicit contact information such as phone, email, address, website, WhatsApp, or contact person.',
  '{}'::jsonb,
  '{"requires_evidence_span":true,"human_approval_required":true,"requires_non_empty_field":true}'::jsonb
),
(
  'faq_item',
  '1.0.0',
  'active',
  '{
    "type": "object",
    "additionalProperties": false,
    "required": ["question", "answer"],
    "properties": {
      "question": { "type": "string" },
      "answer": { "type": "string" },
      "category": { "type": ["string", "null"] }
    }
  }'::jsonb,
  'Extract FAQ items only when question and answer are explicitly present or clearly paired.',
  '{}'::jsonb,
  '{"requires_evidence_span":true,"human_approval_required":true}'::jsonb
);
