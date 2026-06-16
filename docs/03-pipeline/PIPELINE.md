# PIPELINE.md — Fluxo Técnico Completo

## Variáveis de ambiente obrigatórias (nunca hardcodar modelo)

```python
CLASSIFICATION_MODEL = os.getenv("CLASSIFICATION_MODEL")  # modelo barato
EXTRACTION_MODEL     = os.getenv("EXTRACTION_MODEL")       # modelo medio
```

`QUERY_MODEL` nao e obrigatorio para o Context Compiler. Consultas internas sao
diagnosticas; o artefato de integracao com chatbot externo e
`context_bundle.v1`.

---

## Fluxo 1 — Ingestão

```
upload(file)
  ↓
validate_upload_abuse(file)         ← MIME real, tamanho, macros, zip bomb (SECURITY.md §3)
  ↓
validate_input_quality(text)        ← rejeitar antes de gastar tokens
  │  if len(text) < 800            → reject: low_text_volume
  │  if short_lines_ratio > 0.6    → reject: fragmented_layout
  │  if avg_line_length < 12       → reject: broken_extraction
  │  → salvar em source_quality_reports
  ↓
check_file_hash(sha256)             ← deduplicação: hash já existe? retornar source_id existente
  ↓
save_source(file, metadata)         → sources: status='raw', source_type, source_reliability, authority_level
  ↓
extract_text(file)
  │  PDF textual   → pdfminer/pymupdf
  │  DOCX          → python-docx
  │  XLSX          → openpyxl (avaliar fórmulas, expandir células mescladas)
  │  CSV/TXT       → leitura direta
  │  [todos rodam em worker isolado: CPU 0.5, MEM 512MB, timeout 60s, sem rede]
  ↓
split_by_layout(text)               ← chunking semântico: títulos → parágrafos → tabelas → 800 tokens max + overlap 100
  │  cada chunk registra: chunk_index, page_start/page_end, row_start/row_end, content_hash
  ↓
save_chunks()                       → chunks table
  ↓
for each chunk:
  ↓
  detect_injection_attempt(chunk)   ← "ignore instruções anteriores" → flag injection_suspected → unknown_facts_queue
  ↓
  normalize(chunk)                  ← normalização determinística ANTES do LLM
  │  moeda → {"amount": float, "currency": "BRL"}
  │  horário → "HH:MM" 24h
  │  data → ISO 8601
  │  percentual → float em pontos percentuais (10% → 10)
  │  dias → ["monday", ...]
  │  falha de normalização → null + registrar em ambiguities
  ↓
  classify(chunk)                   → fact_type + confidence
  │  prompt: ver /docs/06-prompts/CLASSIFICATION_PROMPT.md
  │  modelo: CLASSIFICATION_MODEL
  ↓
  if confidence < 0.75 or fact_type == 'unknown' or injection_suspected:
    → unknown_facts_queue (status='pending')
  else:
    route(fact_type)
    ↓
    if fact_type in RULE_TYPES:
      extract_rule(chunk, schema)   → business_rules: status='needs_review', schema_version, prompt_version, model_name
    else:
      extract_fact(chunk, schema)   → extracted_facts: status='extracted', schema_version, prompt_version, model_name
    ↓
    if schema_validation_fails after retry:
      → unknown_facts_queue
    ↓
    grounding(chunk, claim, evidence) ← Truth Contract: parse_artifact_created → truth_evaluated (flag GROUNDING_ENABLED)
    │  Check A determinístico  → prova que evidence_quote é texto literal do chunk (NFC, aspas, NBSP, whitespace)
    │  Check B entailment      → verificador independente julga suporte semântico contra o chunk inteiro
    │  required type + falha/abstenção → unknown_facts_queue (needs_review), NÃO vira registro confiável
    │  warn-only type          → mantém o registro + grava grounding_results (sinal visível à revisão)
    │  ver /docs/03-pipeline/GROUNDING_WORKER.md e /docs/07-qa/GROUNDING_GOLD_SLICE.md
  ↓
  log_token_usage()                 → token_usage_log: workspace_id, operation, model, tokens, cost
  ↓
  check_contradictions()            ← apenas entre dados 'approved' (MVP: conflitos numéricos/exatos via SQL)
    → contradictions table se detectado
```

---

## Fluxo 2 — Export Context Bundle

Contrato completo: ver `CONTEXT_BUNDLE.md`.

```text
context_bundle_export(workspace_id)
  -> check workspace membership
  -> load published_sources
  -> load published_facts / published_rules
  -> load only referenced evidence spans
  -> compute readiness from unknown queue and contradictions
  -> sanitize records and evidence
  -> compute deterministic context_version and bundle_hash
  -> write audit_logs.action = 'context_bundle.export'
  -> return context_bundle.v1
```

Este e o fluxo principal para entregar contexto mastigado ao chatbot externo.

---

## Fluxo 2b — Consulta diagnostica interna

Consulta interna nao e o produto principal e nao substitui o chatbot externo.

Contrato completo de producao: ver `QUERY.md`.

```
user_query(text, user_id, workspace_id)
  ↓
check_permission(user, 'query_published')  ← ADR-012: role matrix
  ↓
filter_context_by_role(user)               ← campos sensitive=true removidos antes do LLM (staff não vê custo/margem)
  ↓
classify_intent(query)
  ↓
route_to_source:
  ├── fato estruturado  → SELECT FROM published_facts    ← view: published + válido + superseded_by is null
  ├── regra condicional → SELECT FROM published_rules    ← view: published + válido + superseded_by is null
  ├── política textual  → vector search (Fase 2)
  └── dado dinâmico     → tabela específica (NUNCA RAG)
  ↓
determine_answer_state:
  ├── published + sem conflito          → valid_answer
  ├── cobertura parcial                 → partial_answer
  ├── nenhum dado                       → not_found
  ├── conflito pendente                 → conflicting_sources  ← bloqueia resposta ao cliente
  ├── extracted mas não approved        → needs_human_validation
  ↓
if answer_state != 'valid_answer':
  → retornar mensagem padrão do estado (sem improvisação de LLM)
  → registrar audit_log com answer_state
  → return
  ↓
build_context(facts, rules)           ← apenas published, filtrado por role
  ↓
llm_query(context, query)
  │  prompt: ver /docs/06-prompts/EXTRACTION_PROMPTS.md § rule_evaluation
  │  saída obrigatória: matched_rule_ids, decision, explanation, confidence
  │  NÃO armazenar chain-of-thought interno
  ↓
build_audit_log()
  │  query_audits: question, answer, answer_state, facts_used, rules_used, sources_used
  │  audit_logs: action/resource/input_hash/output_hash
  │  used_unvalidated_data: false (garantido pelo route acima)
  ↓
return(answer, audit_id, sources, confidence, answer_state)
```

---

## Fluxo 3 — Detecção de contradições (MVP: numérico/exato)

```
novo fato → status mudou para 'approved'
  ↓
query: fatos approved com mesmo fact_type + mesmo serviço/entidade
  ↓
comparar valores exatos (price_exact, deadline_days, horário, etc.)
  ↓
if conflito:
  aplicar hierarquia de autoridade (ADR-007):
    official vs normal/informal → official vence automaticamente → fonte inferior deprecated
    mesmo nível                 → mark_fact_contradiction(...), status='open'
  ↓
  se pendente: fatos conflitantes recebem status='conflicted' e saem de published_facts
  ↓
  usuário resolve:
    A) source_a prevalece → fact_b: deprecated
    B) source_b prevalece → fact_a: deprecated
    C) exceção contextual → ambos mantidos com nota obrigatória
    D) ambos inválidos    → ambos: rejected
```

---

## Fluxo 4 — Rollback de publicação

```
owner marca source como deprecated
  ↓
SELECT rollback_source_publication(source_id, reason)
  ↓
published_facts view exclui automaticamente (filtra status != 'published')
  ↓
efeito imediato: próxima consulta já não enxerga os dados
```

Rollback deve ser atômico. Se qualquer UPDATE falhar: ROLLBACK completo.

---

## Roteamento: fact_type → destino

| fact_type | Destino | Tabela |
|-----------|---------|--------|
| service_price | Fato | extracted_facts |
| business_hours | Fato | extracted_facts |
| payment_method | Fato | extracted_facts |
| discount_rule | Regra | business_rules |
| cancellation_policy | Regra | business_rules |
| unknown | Fila | unknown_facts_queue |

---

## Idempotência de tasks

Toda task da fila usa chave idempotente antes de processar:

```python
idempotency_key = sha256(f"{source_id}:{chunk_hash}:{schema_version}:{prompt_version_hash}")
# Se já processado com essa chave: retornar resultado existente, não reprocessar
```

Celery retry nunca duplica fatos, logs ou cobranças.

