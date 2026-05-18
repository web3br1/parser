# MVP_DECISIONS.md — Decisões Fechadas de Implementação

Este documento é a fonte de verdade mais recente para implementação do MVP.

## Princípio de Fechamento

```text
1. Nada implícito → tudo vira contrato
2. Nada probabilístico → sempre fallback determinístico
3. Nada global → tudo versionado e auditável
```

## Produto / MVP

### Escopo

```text
IN:
✔ Upload manual
✔ Quality gate
✔ Extração estruturada
✔ Revisão humana por chunk
✔ Publicação controlada
✔ Consulta auditável interna

OUT:
✘ Cliente final externo
✘ Automação de resposta
✘ Escrita em APIs externas
✘ Social media connectors
✘ Crawling contínuo
```

### Onboarding

```text
STEP 1 → Criar workspace
STEP 2 → Criar usuário owner
STEP 3 → Selecionar "tipo de negócio" (template opcional)
STEP 4 → Upload obrigatório inicial
STEP 5 → Quality gate bloqueante
STEP 6 → Ingestão automática
STEP 7 → Redirecionar para tela de revisão
```

```ts
type WorkspaceState = {
  has_uploaded: boolean
  has_validated_data: boolean
  has_published_data: boolean
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

## Answer States

```ts
type AnswerState =
  | "valid_answer"
  | "not_found"
  | "conflicting_sources"
  | "needs_human_validation"
  | "partial_answer"
```

| Estado | Mensagem padrão |
|--------|-----------------|
| `not_found` | "Não encontrei essa informação nas fontes validadas." |
| `conflicting_sources` | "Existem informações conflitantes sobre isso. Recomendo revisão." |
| `needs_human_validation` | "Essa informação ainda não foi validada por um humano." |
| `partial_answer` | "Encontrei informações parciais. Pode haver lacunas." |

## Pipeline

```text
UPLOAD
→ FILE_VALIDATION
→ TEXT_EXTRACTION
→ QUALITY_GATE
→ CHUNKING
→ CLASSIFICATION
→ EXTRACTION
→ NORMALIZATION
→ STORE
→ REVIEW_QUEUE
```

### Chunking

PDF/DOCX:

```text
1. Heading detection
2. Paragraph block
3. Máx 800 tokens
4. Overlap 100 tokens
```

CSV/XLSX:

```text
Para cada sheet:
→ detectar header
→ mapear colunas
→ agrupar linhas em blocos de 10–20
→ preservar header em cada chunk
```

Um chunk pode gerar:

```text
- 0..N facts
- 0..N rules
- 0..N unknowns
```

### Retries

```text
classification:
- max 2 tentativas

extraction:
- max 2 tentativas

timeout:
- retry com backoff exponencial

erro final:
→ status = failed
→ enviar para revisão manual
```

### Normalização

Normalização nunca usa LLM.

```ts
normalize_currency("R$ 120") → 120 BRL
normalize_currency("120 reais") → 120 BRL
normalize_time("fim do dia") → 18:00
normalize_time("manhã") → 09:00
normalize_date("hoje") → resolve via timezone
```

## Segurança

```text
Auth: Supabase Auth
user_id → workspace_members
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

## QA

Dataset mínimo:

```text
10 docs bons
5 docs ruins
5 conflitantes
5 injection
5 planilhas quebradas
```

Métricas:

```text
approval_rate > 70%
edit_rate < 30%
unknown < 25%
critical_error = 0
```

## Produção

```text
✔ RLS testado
✔ Storage privado
✔ Retry idempotente
✔ Logs sem PII
✔ Versionamento ativo
✔ Rollback funcional
✔ QA completo
✔ Auditoria completa
✔ Query usa apenas dados publicados
```

## Decisão Final

O MVP não é:

```text
IA que responde perguntas
```

O MVP é:

```text
Sistema que transforma caos → dado validado → decisão auditável
```

## Próximo Bloco

```text
1. funções SQL de aprovação/publicação
2. funções SQL de supersede/rollback
3. storage policies do Supabase
4. Pydantic schemas equivalentes aos JSON Schemas
5. endpoints FastAPI que chamam essas tabelas
```
