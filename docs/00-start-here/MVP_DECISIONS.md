# MVP_DECISIONS.md - Decisoes Fechadas de Implementacao

Este documento e a fonte de verdade mais recente para implementacao do MVP.

## Principio de fechamento

```text
1. Nada implicito -> tudo vira contrato
2. Nada probabilistico -> sempre fallback deterministico
3. Nada global -> tudo versionado e auditavel
```

## Direcao de produto

O MVP nao e um chatbot. O MVP e um Context Compiler local que transforma caos em
conhecimento validado e exporta esse contexto para outro runtime.

```text
IN:
- Upload manual
- Quality gate
- Extracao estruturada
- Revisao humana por chunk
- Publicacao controlada
- Export auditavel de context_bundle.v1
- Readiness, gaps e bloqueios de importacao

OUT:
- Cliente final externo
- Runtime final de conversa
- Automacao de resposta
- Escrita em APIs externas
- Social media connectors
- Crawling continuo
- Hosted vector database
```

Consultas internas podem existir para diagnostico e QA, mas nao sao o produto
principal. O contrato de integracao com o outro projeto e `context_bundle.v1`.

## Onboarding

```text
STEP 1 -> Criar workspace
STEP 2 -> Criar usuario owner
STEP 3 -> Selecionar tipo de negocio/template opcional
STEP 4 -> Upload inicial obrigatorio
STEP 5 -> Quality gate bloqueante
STEP 6 -> Ingestao automatica
STEP 7 -> Redirecionar para revisao
STEP 8 -> Publicar conhecimento validado
STEP 9 -> Exportar context_bundle.v1
```

```ts
type WorkspaceState = {
  has_uploaded: boolean
  has_validated_data: boolean
  has_published_data: boolean
  has_exportable_context: boolean
}
```

## Fact Types MVP

### service_price@1.0.0

```ts
{
  service_name: string
  price_amount: number
  currency: "BRL"
  price_type: "fixed" | "starting_from" | "range"
  min_price?: number
  max_price?: number
  valid_from?: date
  valid_until?: date
}
```

### business_hours@1.0.0

```ts
{
  day_of_week: "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun"
  open_time: "HH:mm"
  close_time: "HH:mm"
  is_closed: boolean
  special_case?: string
}
```

### discount_rule@1.0.0

```ts
{
  condition: {
    payment_method?: string
    day_of_week?: string
    min_value?: number
  }
  action: {
    discount_percentage?: number
    discount_fixed?: number
  }
}
```

### cancellation_policy@1.0.0

```ts
{
  notice_required_hours: number
  penalty_percentage?: number
  penalty_fixed?: number
}
```

### payment_method@1.0.0

```ts
{
  method: "pix" | "cash" | "credit" | "debit"
  accepted: boolean
  conditions?: string
}
```

## Readiness do Context Bundle

```ts
type ContextBundleReadiness = {
  status: "ready" | "warning" | "blocked"
  score: number
  blocking_reasons: string[]
  warnings: string[]
}
```

Blocking reasons iniciais:

- `no_published_sources`
- `no_published_records`
- `open_unknown_items`
- `blocking_contradictions`
- `published_record_missing_source`
- `published_record_missing_provenance`

Warnings iniciais:

- `published_record_missing_evidence`
- `low_confidence_record`

Estados de resposta conversacional pertencem ao projeto consumidor. Este repo
entrega readiness, evidencias e contexto compilado.

## Pipeline

```text
UPLOAD
-> FILE_VALIDATION
-> TEXT_EXTRACTION
-> QUALITY_GATE
-> CHUNKING
-> CLASSIFICATION
-> EXTRACTION
-> NORMALIZATION
-> STORE
-> REVIEW_QUEUE
-> PUBLISH
-> CONTEXT_BUNDLE_EXPORT
```

## Chunking

PDF/DOCX:

```text
1. Heading detection
2. Paragraph block
3. Max 800 tokens
4. Overlap 100 tokens
```

CSV/XLSX:

```text
Para cada sheet:
-> detectar header
-> mapear colunas
-> agrupar linhas em blocos de 10-20
-> preservar header em cada chunk
```

Um chunk pode gerar:

```text
- 0..N facts
- 0..N rules
- 0..N unknowns
```

## Retries

```text
classification:
- max 2 tentativas

extraction:
- max 2 tentativas

timeout:
- retry com backoff exponencial

erro final:
-> status = failed
-> enviar para revisao manual
```

## Normalizacao

Normalizacao nunca usa LLM.

```ts
normalize_currency("R$ 120") -> 120 BRL
normalize_currency("120 reais") -> 120 BRL
normalize_time("fim do dia") -> 18:00
normalize_time("manha") -> 09:00
normalize_date("hoje") -> resolve via timezone
```

## Seguranca

```text
Auth: Supabase Auth
user_id -> workspace_members
Bucket: private
Storage path: /workspace/{id}/source/{id}/file
```

RLS deve sempre usar membership:

```sql
public.is_workspace_member(workspace_id)
```

Nunca usar:

```sql
workspace_id = auth.uid()
```

O Context Bundle nunca inclui secrets, bearer tokens, signed URLs, paths locais,
prompts crus, provider responses, stack traces, unpublished facts/rules ou raw
unknown queue content.

## QA

Dataset minimo:

```text
10 docs bons
5 docs ruins
5 conflitantes
5 injection
5 planilhas quebradas
```

Metricas:

```text
approval_rate > 70%
edit_rate < 30%
unknown < 25%
critical_error = 0
context_bundle_secret_leaks = 0
```

## Producao

```text
- RLS testado
- Storage privado
- Retry idempotente
- Logs sem PII/secrets
- Versionamento ativo
- Rollback funcional
- QA completo
- Auditoria completa
- Context bundle usa apenas dados publicados
- Secret scan e redaction gates passam
```

## Decisao final

O MVP nao e:

```text
IA que responde perguntas
```

O MVP e:

```text
Sistema local que transforma caos -> dado validado -> contexto exportavel
```

## Proximo bloco

```text
1. consolidar funcoes SQL de aprovacao/publicacao
2. consolidar supersede/rollback
3. validar storage policies do Supabase
4. manter schemas Pydantic alinhados aos JSON Schemas
5. expor endpoints FastAPI para ingestao, revisao, publicacao e bundle
6. preparar importacao pelo chatbot externo
```
