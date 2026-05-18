export const FACT_TYPES = [
  "service_price",
  "business_hours",
  "payment_method",
  "contact_info",
  "faq_item"
] as const;

export const MVP_KNOWLEDGE_TYPES = [
  ...FACT_TYPES,
  "discount_rule",
  "cancellation_policy"
] as const;

export const UNKNOWN_STATUS_OPTIONS = ["open", "mapped", "ignored", "schema_requested", "resolved"] as const;

const RULE_TYPES = new Set(["discount_rule", "cancellation_policy"]);

export function normalizeFactType(value: string) {
  return value.trim().toLowerCase();
}

export function selectableFactType(value: string | null | undefined) {
  const normalized = normalizeFactType(value ?? "");
  return (MVP_KNOWLEDGE_TYPES as readonly string[]).includes(normalized) ? normalized : MVP_KNOWLEDGE_TYPES[0];
}

export function destinationForFactType(value: string) {
  return RULE_TYPES.has(normalizeFactType(value)) ? "business_rules" : "extracted_facts";
}
