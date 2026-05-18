# OBSERVABILITY.md — Observabilidade e Avaliação Contínua

## Status no MVP

No MVP, a observabilidade executável vem das tabelas já migradas:

| Tabela | Uso |
|--------|-----|
| `processing_jobs` | status, retry, erro e idempotência de jobs |
| `source_quality_reports` | quality gate por fonte |
| `query_audits` | auditoria de consulta |
| `audit_logs` | auditoria operacional |
| `token_usage_log` | tokens, custo e latência |
| `validation_events` | histórico de aprovação, edição, publicação, supersede e conflito |

`pipeline_metrics`, `fact_type_metrics` e `unsupported_sources` são pós-MVP até existirem migrations dedicadas.

---

## 1. Métricas de qualidade do pipeline

Além de custo de tokens, registrar:

```sql
CREATE TABLE pipeline_metrics (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id            UUID NOT NULL,
    period_start            TIMESTAMP NOT NULL,
    period_end              TIMESTAMP NOT NULL,

    -- Ingestão
    docs_uploaded           INT DEFAULT 0,
    docs_rejected_quality   INT DEFAULT 0,
    rejection_rate          NUMERIC,        -- docs_rejected / docs_uploaded

    -- Classificação e extração
    chunks_total            INT DEFAULT 0,
    chunks_unknown          INT DEFAULT 0,
    unknown_rate            NUMERIC,        -- chunks_unknown / chunks_total
    schema_validation_fails INT DEFAULT 0,

    -- Validação humana
    facts_extracted         INT DEFAULT 0,
    facts_approved          INT DEFAULT 0,
    facts_rejected          INT DEFAULT 0,
    facts_edited            INT DEFAULT 0,
    approval_rate           NUMERIC,
    edit_rate               NUMERIC,        -- quanto humano edita o que LLM extraiu

    -- Contradições
    contradictions_detected INT DEFAULT 0,
    contradictions_resolved INT DEFAULT 0,

    -- Publicação
    avg_time_to_publish_hours NUMERIC,      -- upload até approved

    -- Custo
    total_cost_usd          NUMERIC(10, 4),
    cost_per_doc_usd        NUMERIC(10, 4),
    cost_per_approved_fact_usd NUMERIC(10, 6),

    created_at              TIMESTAMP DEFAULT NOW()
);
```

## 2. Métricas de qualidade por fact_type

```sql
CREATE TABLE fact_type_metrics (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id          UUID NOT NULL,
    fact_type             TEXT NOT NULL,
    schema_version        TEXT NOT NULL,
    period_start          TIMESTAMP NOT NULL,
    extractions_attempted INT DEFAULT 0,
    schema_valid_rate     NUMERIC,   -- passou na validação Pydantic
    approval_rate         NUMERIC,   -- aprovados / extraídos
    edit_rate             NUMERIC,   -- editados / aprovados
    ambiguity_rate        NUMERIC,   -- com ambiguidades / total
    created_at            TIMESTAMP DEFAULT NOW()
);
```

`edit_rate` alto em um fact_type específico indica que o prompt ou schema está gerando extração ruim.

## 3. Dataset de avaliação adversarial

Manter em `/examples/adversarial/` um dataset de casos que o pipeline **deve** tratar corretamente:

| Categoria | Exemplos |
|-----------|----------|
| Documento contraditório | PDF com preço A + planilha com preço B |
| Documento mal formatado | PDF com layout fragmentado que passa qualidade |
| Documento incompleto | Tabela de preços sem cabeçalho |
| Documento injetado | Texto com tentativa de prompt injection |
| Documento duplicado | Mesmo arquivo com nome diferente |
| Documento obsoleto | Versão antiga com data explícita |
| Tabela complexa | Células mescladas, abas múltiplas, fórmulas |
| Regra vaga | "Clientes especiais têm condições diferenciadas" |
| Ambiguidade de data | "Promoção válida até o fim do mês" sem data atual |

## 4. Regressão automática por mudança de schema ou prompt

Toda PR que modifica schema ou prompt deve:
1. Rodar extração contra o dataset de avaliação
2. Comparar saída com `expected_outputs/` correspondentes
3. Reportar: taxa de match exato, taxa de match semântico, novos campos, campos perdidos
4. Falhar se taxa de match exato cair mais de 10% em relação à versão anterior

```python
def run_regression(fact_type: str, new_schema_version: str) -> dict:
    test_cases = load_test_cases(fact_type)
    results = []
    for case in test_cases:
        output = extract(case["input"], fact_type, new_schema_version)
        results.append(compare(output, case["expected_output"]))
    return summarize(results)
```

## 5. Alerta de degradação

Monitorar semanalmente:
- `unknown_rate` subindo → prompt de classificação pode estar degradando
- `edit_rate` subindo → schema ou prompt de extração pode estar errado
- `approval_rate` caindo → qualidade de entrada pode estar piorando
- `cost_per_approved_fact` subindo → pipeline está ficando menos eficiente

Threshold de alerta: variação > 20% em relação à média das 4 semanas anteriores.

## 6. Unsupported sources (sem OCR)

Manter fila para fontes que o MVP não processa, para análise futura:

```sql
CREATE TABLE unsupported_sources (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    filename     TEXT,
    file_type    TEXT,
    reason       TEXT,   -- scanned_pdf | image | unknown_format
    file_url     TEXT,   -- arquivo original preservado no storage
    created_at   TIMESTAMP DEFAULT NOW()
);
```

Essa fila informa prioridade de desenvolvimento de OCR: se 40% das tentativas de upload são PDFs escaneados, OCR sobe de prioridade.

