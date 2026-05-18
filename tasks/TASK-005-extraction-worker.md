# TASK-005 — Extraction Worker

**Projeto:** Context Builder Empresarial  
**Status:** `ready`  
**Versão:** 1.0  
**Agente:** Claude Code / Codex  
**Estimativa:** 1–2 sessões  
**Depende de:** TASK-001 ✅, TASK-002 ✅, TASK-004 ✅  
**Bloqueia:** TASK-006 (human review UI), TASK-007 (publication flow)

---

## Objetivo

Implementar o worker de extração que consome jobs de extração enfileirados pela TASK-004, chama o LLM com prompt por fact_type, valida com Pydantic, normaliza deterministicamente e persiste em `extracted_facts` ou `business_rules`.

Esta task cobre a etapa 7–10 do pipeline obrigatório:

```
[TASK-004] enqueue_extraction_job(fact_type, chunk_id)
  → [TASK-005] LLM extraction
  → Pydantic validation
  → deterministic normalization
  → evidence_span creation
  → store extracted_facts | business_rules
  → chunk.status = "extracted"
[TASK-006] human review →
```

**Não implementar revisão humana.** A task termina com o registro persistido com `status="extracted"` e pronto para a fila de revisão.

---

## Decisões fechadas

### Dois gaps herdados — fechados nesta task

**Gap 1 — Schema Registry incompleto:** `SCHEMA_REGISTRY.md` declara 5 fact types. `CLAUDE.md` especifica 7. `contact_info` e `faq_item` não têm schema Pydantic nem prompt de extração. Esta task adiciona ambos.

**Gap 2 — Outbox pattern:** `enqueue_extraction_job` na TASK-004 é `pass`. Esta task implementa o padrão correto:

```
TASK-004 (dentro da transação):
  → criar processing_job(type="extraction", status="queued") no DB  ← outbox

TASK-004 (APÓS commit da transação):
  → extract_fact.delay(job_id=job_id, ...)  ← enqueue real

TASK-005 worker:
  → processar o job pelo job_id
```

Se o sistema cair entre o commit e o `.delay()`, o job permanece `queued` e pode ser re-enfileirado por um scheduler periódico. O chunk **nunca fica em estado inconsistente**.

### Roteamento por fact_type e destino

| fact_type | Tabela destino | evidence_span_id |
|---|---|---|
| `service_price` | `extracted_facts` | opcional |
| `business_hours` | `extracted_facts` | opcional |
| `payment_method` | `extracted_facts` | opcional |
| `contact_info` | `extracted_facts` | opcional |
| `faq_item` | `extracted_facts` | opcional |
| `discount_rule` | `business_rules` | **obrigatório** |
| `cancellation_policy` | `business_rules` | **obrigatório** |

`business_rules.evidence_span_id` é `NOT NULL` na migration — se a extração não produzir um `quote`, o job falha com `extraction_parse_failed`.

### Multiplicity por fact_type

| fact_type | Records por job |
|---|---|
| `business_hours` | N (um por `day_of_week`) |
| Todos os demais | 1 |

Para `business_hours`, o LLM retorna `data` como `list[dict]`. O worker cria um `extracted_facts` por item da lista.

### Status do chunk após extração

```
"extracted"   → ao menos um fact/rule persistido com sucesso
"needs_review" → nenhum fact persistido (LLM retornou "failed", Pydantic falhou em todas as tentativas, ou quote ausente em rule)
```

### Contradiction detection

**Não implementar nesta task.** Contradiction detection ocorre no fluxo de publicação (TASK-007+), somente contra fatos `approved`. Extrair e armazenar como `extracted` é suficiente aqui.

### Normalização

Dois momentos distintos:

1. **Pré-Pydantic (pre-normalization):** aplicar normalizers a campos que o LLM pode retornar como string (`"R$ 120"`, `"9h"`, `"10%"`). Resultado alimenta a validação Pydantic.
2. **Pós-Pydantic (normalized_content):** após validação, persistir `normalized_content` como JSONB separado — versão canônica para queries. Se normalização falhar para um campo, esse campo fica `null` em `normalized_content` + warning.

---

## Arquivos a criar ou modificar

```
packages/
  schema_registry/
    src/schema_registry/
      types.py          ← adicionar ContactInfo, FAQItem
      validators.py     ← get_pydantic_model(fact_type) + validate_extraction()

  normalizers/
    src/normalizers/
      pre_extract.py    ← NOVO: pre-Pydantic normalization por fact_type

workers/
  extraction/
    pyproject.toml
    src/
      worker_extraction/
        __init__.py
        celery_app.py
        tasks.py          ← extract_fact task
        extractor.py      ← LLM call + parse + Pydantic
        prompt.py         ← prompts por fact_type + versioning
        normalizer.py     ← pré e pós normalização
        evidence.py       ← create_evidence_span()
        db.py             ← acesso ao banco
        logging.py        ← logger estruturado
    tests/
      test_extractor.py
      test_normalizer.py
      test_tasks.py

  classification/
    src/worker_classification/
      extraction_queue.py ← substituir `pass` pelo outbox real (TASK-004 companion)

docs/
  06-prompts/
    EXTRACTION_PROMPTS.md  ← adicionar contact_info e faq_item
  04-data/
    SCHEMA_REGISTRY.md     ← adicionar contact_info e faq_item
```

---

## `packages/schema_registry` — Tipos novos

Arquivo: `packages/schema_registry/src/schema_registry/types.py`

Adicionar ao final do arquivo existente (não remover os 5 tipos já declarados):

```python
class ContactInfo(StrictModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    whatsapp: Optional[str] = None
    contact_name: Optional[str] = None   # nome do atendente, departamento ou responsável


class FAQItem(StrictModel):
    question: str
    answer: str
    category: Optional[str] = None
```

Regras:

- `ContactInfo`: ao menos um campo não-null deve estar presente. Validar no nível do worker (não no schema — Pydantic não impõe isso diretamente).
- `FAQItem`: `question` e `answer` são obrigatórios; se o LLM retornar `null` em qualquer um → `status="failed"` no response.

---

## `packages/schema_registry` — Validator

Arquivo: `packages/schema_registry/src/schema_registry/validators.py`

```python
from dataclasses import dataclass
from pydantic import ValidationError
from .types import (
    StrictModel, ServicePrice, BusinessHours, PaymentMethod,
    DiscountRule, CancellationPolicy, ContactInfo, FAQItem,
)


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    data: dict              # dados validados (modelo.model_dump())
    errors: list[str]       # mensagens de erro Pydantic se valid=False


_FACT_TYPE_MAP: dict[str, type[StrictModel]] = {
    "service_price":      ServicePrice,
    "business_hours":     BusinessHours,
    "payment_method":     PaymentMethod,
    "discount_rule":      DiscountRule,
    "cancellation_policy": CancellationPolicy,
    "contact_info":       ContactInfo,
    "faq_item":           FAQItem,
}


def get_pydantic_model(fact_type: str) -> type[StrictModel]:
    if fact_type not in _FACT_TYPE_MAP:
        raise ValueError(f"Unknown fact_type: {fact_type!r}")
    return _FACT_TYPE_MAP[fact_type]


def validate_extraction(fact_type: str, raw_data: dict) -> ValidationResult:
    """
    Valida raw_data contra o schema Pydantic do fact_type.
    Nunca lança exceção — encapsula ValidationError em ValidationResult.
    """
    model_cls = get_pydantic_model(fact_type)
    try:
        instance = model_cls(**raw_data)
        return ValidationResult(valid=True, data=instance.model_dump(), errors=[])
    except ValidationError as exc:
        return ValidationResult(
            valid=False,
            data={},
            errors=[f"{e['loc']}: {e['msg']}" for e in exc.errors()],
        )
```

---

## `packages/normalizers` — Pre-extract Normalizer

Arquivo: `packages/normalizers/src/normalizers/pre_extract.py`

Aplicar normalizers a campos de string antes da validação Pydantic:

```python
from .currency import normalize_currency
from .time import normalize_time
from .date import normalize_date
from .percent import normalize_percent


def pre_normalize(fact_type: str, raw_data: dict) -> dict:
    """
    Aplica normalizadores deterministicos aos campos de raw_data
    antes da validação Pydantic.
    Campos que não forem normalizáveis ficam com valor original.
    Nunca lança exceção.
    """
    data = dict(raw_data)  # cópia defensiva

    if fact_type == "service_price":
        data = _normalize_service_price(data)

    elif fact_type == "business_hours":
        data = _normalize_business_hours(data)

    elif fact_type == "discount_rule":
        data = _normalize_discount_rule(data)

    elif fact_type == "cancellation_policy":
        data = _normalize_cancellation_policy(data)

    # payment_method, contact_info, faq_item: sem normalização numérica necessária

    return data


def _normalize_service_price(d: dict) -> dict:
    for field in ("price_amount", "min_price", "max_price"):
        val = d.get(field)
        if isinstance(val, str):
            money = normalize_currency(val)
            d[field] = money.amount if money else val
    return d


def _normalize_business_hours(d: dict) -> dict:
    for field in ("open_time", "close_time"):
        val = d.get(field)
        if isinstance(val, str) and val:
            normalized = normalize_time(val)
            d[field] = normalized if normalized else val
    return d


def _normalize_discount_rule(d: dict) -> dict:
    action = d.get("action", {})
    if isinstance(action, dict):
        pct = action.get("discount_percentage")
        if isinstance(pct, str):
            action["discount_percentage"] = normalize_percent(pct)
        fixed = action.get("discount_fixed")
        if isinstance(fixed, str):
            money = normalize_currency(fixed)
            action["discount_fixed"] = money.amount if money else fixed
        d["action"] = action
    return d


def _normalize_cancellation_policy(d: dict) -> dict:
    pct = d.get("penalty_percentage")
    if isinstance(pct, str):
        d["penalty_percentage"] = normalize_percent(pct)
    fixed = d.get("penalty_fixed")
    if isinstance(fixed, str):
        money = normalize_currency(fixed)
        d["penalty_fixed"] = money.amount if money else fixed
    return d
```

---

## `workers/extraction` — Prompt Manager

Arquivo: `workers/extraction/src/worker_extraction/prompt.py`

```python
from hashlib import sha256


# Prompts indexados por fact_type.
# Baseados em docs/06-prompts/EXTRACTION_PROMPTS.md.
# Esta é a fonte canônica — a doc é espelho.

_BASE_RULES = """Você é um extrator de informações estruturadas para sistemas empresariais.
Extraia apenas informações explicitamente presentes no trecho.

REGRAS OBRIGATÓRIAS:
- Responda APENAS com JSON válido.
- Nunca invente valores.
- Se um campo não estiver presente, use null quando o schema permitir.
- Não normalize. Preserve valores extraídos; a normalização determinística roda depois.
- Inclua evidence_span.quote com o menor trecho que sustenta a extração.
- Se não houver evidência textual clara, retorne status "failed".

Trecho:
---
{chunk_text}
---"""

_RESPONSE_FORMAT = """
Responda no formato:
{{
  "status": "ok | failed",
  "fact_type": "{fact_type}",
  "data": {schema_example},
  "evidence_span": {{
    "quote": "trecho literal que sustenta a extração",
    "char_start": null,
    "char_end": null
  }},
  "ambiguities": []
}}"""

_RETRY_SUFFIX = """

IMPORTANTE: Sua resposta anterior não era JSON válido ou não seguiu o schema.
Responda EXCLUSIVAMENTE com JSON. Sem markdown, sem explicações.
Comece com {{ e termine com }}."""


EXTRACTION_PROMPTS: dict[str, str] = {
    "service_price": _BASE_RULES + _RESPONSE_FORMAT.format(
        fact_type="service_price",
        schema_example='{"service_name": "string", "price_amount": 120, "currency": "BRL", "price_type": "fixed|starting_from|range|unknown", "min_price": null, "max_price": null, "valid_from": null, "valid_until": null}',
    ),
    "business_hours": _BASE_RULES + """

Regra especial: retorne um item por dia mencionado no trecho.
""" + _RESPONSE_FORMAT.format(
        fact_type="business_hours",
        schema_example='[{"day_of_week": "mon|tue|wed|thu|fri|sat|sun", "open_time": "HH:mm ou null", "close_time": "HH:mm ou null", "is_closed": false, "special_case": null}]',
    ),
    "payment_method": _BASE_RULES + _RESPONSE_FORMAT.format(
        fact_type="payment_method",
        schema_example='{"method": "pix|cash|credit|debit|bank_transfer|unknown", "accepted": true, "conditions": null}',
    ),
    "discount_rule": _BASE_RULES + _RESPONSE_FORMAT.format(
        fact_type="discount_rule",
        schema_example='{"condition": {"payment_method": null, "day_of_week": null, "min_value": null}, "action": {"discount_percentage": null, "discount_fixed": null}}',
    ),
    "cancellation_policy": _BASE_RULES + _RESPONSE_FORMAT.format(
        fact_type="cancellation_policy",
        schema_example='{"notice_required_hours": 24, "penalty_percentage": null, "penalty_fixed": null}',
    ),
    "contact_info": _BASE_RULES + _RESPONSE_FORMAT.format(
        fact_type="contact_info",
        schema_example='{"phone": null, "email": null, "address": null, "website": null, "whatsapp": null, "contact_name": null}',
    ),
    "faq_item": _BASE_RULES + _RESPONSE_FORMAT.format(
        fact_type="faq_item",
        schema_example='{"question": "pergunta literal do texto", "answer": "resposta literal do texto", "category": null}',
    ),
}


def get_extraction_prompt(fact_type: str, *, retry: bool = False) -> str:
    template = EXTRACTION_PROMPTS.get(fact_type)
    if template is None:
        raise ValueError(f"No extraction prompt for fact_type: {fact_type!r}")
    return template + (_RETRY_SUFFIX if retry else "")


def get_prompt_version(fact_type: str) -> str:
    template = get_extraction_prompt(fact_type, retry=False)
    return sha256(template.encode()).hexdigest()[:16]
```

---

## `workers/extraction` — Evidence Span

Arquivo: `workers/extraction/src/worker_extraction/evidence.py`

```python
from dataclasses import dataclass
from hashlib import sha256


@dataclass
class EvidenceSpanInput:
    workspace_id: str
    source_id: str
    chunk_id: str
    quote: str
    char_start: int | None
    char_end: int | None
    page_number: int | None
    sheet_name: str | None
    row_number: int | None


def build_evidence_span_input(
    *,
    workspace_id: str,
    source_id: str,
    chunk_id: str,
    llm_evidence: dict,       # {"quote": "...", "char_start": ..., "char_end": ...}
    chunk_metadata: dict,     # metadata do chunk (page, sheet, row)
) -> EvidenceSpanInput | None:
    """
    Constrói o input para criação do evidence_span.
    Retorna None se quote estiver ausente ou vazio.
    """
    quote = (llm_evidence.get("quote") or "").strip()
    if not quote:
        return None

    return EvidenceSpanInput(
        workspace_id=workspace_id,
        source_id=source_id,
        chunk_id=chunk_id,
        quote=quote,
        char_start=llm_evidence.get("char_start"),
        char_end=llm_evidence.get("char_end"),
        page_number=chunk_metadata.get("source_page"),
        sheet_name=chunk_metadata.get("sheet_name"),
        row_number=chunk_metadata.get("row_start"),
    )


def compute_quote_hash(quote: str) -> str:
    return sha256(quote.encode()).hexdigest()
```

Regra: se `build_evidence_span_input` retornar `None`:
- Para `extracted_facts` → continuar sem evidence_span (nullable).
- Para `business_rules` → falhar o job com `reason="missing_evidence_quote"` e enviar para `unknown_facts_queue`.

---

## `workers/extraction` — Extractor

Arquivo: `workers/extraction/src/worker_extraction/extractor.py`

```python
import json
import os
from dataclasses import dataclass, field
from hashlib import sha256
from model_gateway import get_model_gateway, ClassificationResponse
from schema_registry.validators import validate_extraction, ValidationResult
from normalizers.pre_extract import pre_normalize
from .prompt import get_extraction_prompt, get_prompt_version


@dataclass
class ExtractionOutput:
    fact_type: str
    status: str                   # "ok" | "failed" | "parse_failed" | "validation_failed"
    raw_data: dict                # payload bruto do LLM (pre-normalized)
    validated_data: dict          # após Pydantic (vazio se failed)
    normalized_content: dict      # após normalizadores pós-Pydantic (vazio se failed)
    evidence_quote: str
    evidence_char_start: int | None
    evidence_char_end: int | None
    ambiguities: list[str]
    model_name: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    raw_response_hash: str
    validation_errors: list[str]  # erros Pydantic se validation_failed
    is_multi: bool                # True para business_hours (lista de records)
    records: list[dict]           # populated only when is_multi=True


def extract(
    chunk_text: str,
    fact_type: str,
    *,
    retry: bool = False,
) -> ExtractionOutput:
    """
    Chama o LLM e processa a extração para um fact_type.
    Nunca lança exceção — erros encapsulados em ExtractionOutput.status.
    """
    prompt_version = get_prompt_version(fact_type)
    prompt = get_extraction_prompt(fact_type, retry=retry)
    model_name = os.getenv("EXTRACTION_MODEL", "gpt-4o")

    gateway = get_model_gateway()
    try:
        response = gateway.extract(
            chunk_text=chunk_text,
            prompt_template=prompt,
            prompt_version=prompt_version,
        )
    except Exception as exc:
        raise  # deixar o caller (tasks.py) decidir sobre retry técnico

    raw_str = response.raw_response
    raw_hash = sha256(raw_str.encode()).hexdigest()

    try:
        parsed = json.loads(raw_str)
    except json.JSONDecodeError:
        return ExtractionOutput(
            fact_type=fact_type, status="parse_failed",
            raw_data={}, validated_data={}, normalized_content={},
            evidence_quote="", evidence_char_start=None, evidence_char_end=None,
            ambiguities=[], model_name=model_name, prompt_version=prompt_version,
            input_tokens=response.input_tokens, output_tokens=response.output_tokens,
            raw_response_hash=raw_hash, validation_errors=[],
            is_multi=False, records=[],
        )

    if parsed.get("status") == "failed":
        return ExtractionOutput(
            fact_type=fact_type, status="failed",
            raw_data=parsed, validated_data={}, normalized_content={},
            evidence_quote=parsed.get("evidence_span", {}).get("quote", ""),
            evidence_char_start=None, evidence_char_end=None,
            ambiguities=parsed.get("ambiguities", []),
            model_name=model_name, prompt_version=prompt_version,
            input_tokens=response.input_tokens, output_tokens=response.output_tokens,
            raw_response_hash=raw_hash, validation_errors=[],
            is_multi=False, records=[],
        )

    evidence = parsed.get("evidence_span", {})
    raw_data = parsed.get("data", {})
    is_multi = fact_type == "business_hours" and isinstance(raw_data, list)

    if is_multi:
        records = _process_multi(fact_type, raw_data)
        return ExtractionOutput(
            fact_type=fact_type, status="ok",
            raw_data=parsed, validated_data={}, normalized_content={},
            evidence_quote=evidence.get("quote", ""),
            evidence_char_start=evidence.get("char_start"),
            evidence_char_end=evidence.get("char_end"),
            ambiguities=parsed.get("ambiguities", []),
            model_name=model_name, prompt_version=prompt_version,
            input_tokens=response.input_tokens, output_tokens=response.output_tokens,
            raw_response_hash=raw_hash, validation_errors=[],
            is_multi=True, records=records,
        )

    # single-record path
    pre_normalized = pre_normalize(fact_type, raw_data)
    vr = validate_extraction(fact_type, pre_normalized)
    if not vr.valid:
        return ExtractionOutput(
            fact_type=fact_type, status="validation_failed",
            raw_data=raw_data, validated_data={}, normalized_content={},
            evidence_quote=evidence.get("quote", ""),
            evidence_char_start=evidence.get("char_start"),
            evidence_char_end=evidence.get("char_end"),
            ambiguities=parsed.get("ambiguities", []),
            model_name=model_name, prompt_version=prompt_version,
            input_tokens=response.input_tokens, output_tokens=response.output_tokens,
            raw_response_hash=raw_hash, validation_errors=vr.errors,
            is_multi=False, records=[],
        )

    return ExtractionOutput(
        fact_type=fact_type, status="ok",
        raw_data=raw_data, validated_data=vr.data,
        normalized_content=vr.data,   # pós-Pydantic já é o dado normalizado
        evidence_quote=evidence.get("quote", ""),
        evidence_char_start=evidence.get("char_start"),
        evidence_char_end=evidence.get("char_end"),
        ambiguities=parsed.get("ambiguities", []),
        model_name=model_name, prompt_version=prompt_version,
        input_tokens=response.input_tokens, output_tokens=response.output_tokens,
        raw_response_hash=raw_hash, validation_errors=[],
        is_multi=False, records=[],
    )


def _process_multi(fact_type: str, items: list) -> list[dict]:
    """Para business_hours: pré-normaliza e valida cada item individualmente."""
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        pre = pre_normalize(fact_type, item)
        vr = validate_extraction(fact_type, pre)
        if vr.valid:
            results.append(vr.data)
    return results
```

---

## `packages/model_gateway` — Método `extract`

O `OpenAIModelGateway` precisa de um segundo método além de `classify`. Adicionar à interface base e ao cliente OpenAI:

### `base.py` — adicionar

```python
@dataclass(frozen=True)
class ExtractionResponse:
    model_name: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    raw_response: str    # JSON string completo — nunca persistir


class ModelGatewayBase(ABC):
    # ... classify existente ...

    @abstractmethod
    def extract(
        self,
        chunk_text: str,
        prompt_template: str,
        prompt_version: str,
    ) -> ExtractionResponse:
        ...
```

### `openai_client.py` — adicionar método

```python
def extract(
    self,
    chunk_text: str,
    prompt_template: str,
    prompt_version: str,
) -> ExtractionResponse:
    prompt = prompt_template.replace("{chunk_text}", chunk_text)
    model  = os.environ.get("EXTRACTION_MODEL", "gpt-4o")

    response = self._client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},   # extração: json_object (não json_schema — output variável por tipo)
        temperature=0,
    )
    raw = response.choices[0].message.content or "{}"
    return ExtractionResponse(
        model_name=model,
        prompt_version=prompt_version,
        input_tokens=response.usage.prompt_tokens    if response.usage else 0,
        output_tokens=response.usage.completion_tokens if response.usage else 0,
        raw_response=raw,
    )
```

Usar `response_format={"type": "json_object"}` (não `json_schema` estrito) pois o schema de `data` varia por fact_type e inclui campos opcionais. A validação estrutural é feita pelo Pydantic no worker, não pelo OpenAI.

---

## `workers/extraction` — Celery Task

Arquivo: `workers/extraction/src/worker_extraction/tasks.py`

```python
@app.task(
    bind=True,
    name="worker_extraction.tasks.extract_fact",
    max_retries=2,
    default_retry_delay=20,
    acks_late=True,
    soft_time_limit=60,
    time_limit=90,
)
def extract_fact(
    self: Task,
    *,
    job_id: str,
    chunk_id: str,
    workspace_id: str,
    source_id: str,
    fact_type: str,
    destination: str,         # "extracted_facts" | "business_rules"
    classification_confidence: float,
    classification_prompt_version: str,
) -> dict:
    ...
```

### Fluxo obrigatório

```
1. IDEMPOTÊNCIA
   prompt_version = get_prompt_version(fact_type)
   model_name = os.getenv("EXTRACTION_MODEL", "gpt-4o")
   idempotency_key = sha256(
       f"{chunk_id}:{fact_type}:{prompt_version}:{model_name}".encode()
   ).hexdigest()
   existing = db.get_job_by_idempotency_key(idempotency_key)
   Se existing e existing.status == "succeeded":
       return {"status": "succeeded", "cached": True}

2. INICIAR
   db.mark_job_running(job_id, idempotency_key=idempotency_key)
   chunk = db.get_chunk(chunk_id)
   Se chunk.workspace_id != workspace_id:
       db.mark_job_failed(job_id, reason="workspace_mismatch")
       return {"status": "failed", "reason": "workspace_mismatch"}

3. EXTRAIR (1ª tentativa)
   output = extract(chunk.content, fact_type, retry=False)

4. RETRY INTERNO (se parse_failed ou validation_failed na 1ª tentativa)
   Se output.status in ("parse_failed", "validation_failed") e self.request.retries == 0:
       logger.warning("extraction_retry", chunk_id=chunk_id, fact_type=fact_type,
                       reason=output.status)
       output = extract(chunk.content, fact_type, retry=True)  # sufixo de retry no prompt

5. LOG DE TOKENS
   db.log_token_usage(
       workspace_id=workspace_id, source_id=source_id, chunk_id=chunk_id,
       operation="extract",
       model=output.model_name,
       input_tokens=output.input_tokens,
       output_tokens=output.output_tokens,
   )

6. SE FALHA APÓS RETRY
   Se output.status in ("failed", "parse_failed", "validation_failed"):
       with db.transaction():
           db.insert_unknown_queue_item(
               workspace_id=workspace_id, source_id=source_id, chunk_id=chunk_id,
               raw_text=chunk.content[:2000],
               suggested_fact_type=fact_type, confidence=classification_confidence,
               metadata={
                   "reason": output.status,
                   "fact_type": fact_type,
                   "validation_errors": output.validation_errors[:5],
               },
           )
           db.update_chunk_status(chunk_id, "needs_review")
           db.mark_job_succeeded(job_id, idempotency_key=idempotency_key)
       return {"status": "succeeded", "chunk_status": "needs_review",
               "reason": output.status, "fact_type": fact_type}

7. VALIDAR DADOS ÚTEIS ESPECÍFICOS
   Se fact_type == "contact_info" e todos os campos de output.validated_data forem None ou "":
       with db.transaction():
           db.insert_unknown_queue_item(
               workspace_id=workspace_id, source_id=source_id, chunk_id=chunk_id,
               raw_text=chunk.content[:2000],
               suggested_fact_type=fact_type, confidence=classification_confidence,
               metadata={"reason": "empty_contact_info", "fact_type": fact_type},
           )
           db.update_chunk_status(chunk_id, "needs_review")
           db.mark_job_succeeded(job_id, idempotency_key=idempotency_key)
       return {"status": "succeeded", "chunk_status": "needs_review",
               "reason": "empty_contact_info", "fact_type": fact_type}

8. CRIAR EVIDENCE SPAN
   span_input = build_evidence_span_input(
       workspace_id=workspace_id, source_id=source_id, chunk_id=chunk_id,
       llm_evidence={"quote": output.evidence_quote,
                     "char_start": output.evidence_char_start,
                     "char_end": output.evidence_char_end},
       chunk_metadata=chunk.metadata,
   )
   Se destination == "business_rules" e span_input is None:
       # evidence_span obrigatório para rules — falha de domínio
       with db.transaction():
           db.insert_unknown_queue_item(..., metadata={"reason": "missing_evidence_quote"})
           db.update_chunk_status(chunk_id, "needs_review")
           db.mark_job_succeeded(job_id, idempotency_key=idempotency_key)
       return {"status": "succeeded", "chunk_status": "needs_review",
               "reason": "missing_evidence_quote"}

9. PERSISTIR (TRANSAÇÃO ÚNICA)
   with db.transaction():
       evidence_span_id = None
       Se span_input is not None:
           evidence_span_id = db.create_evidence_span(span_input)

       Se output.is_multi (business_hours):
           ids = []
           para cada record em output.records:
               id = db.insert_extracted_fact(
                   workspace_id=workspace_id, source_id=source_id, chunk_id=chunk_id,
                   evidence_span_id=evidence_span_id,
                   fact_type=fact_type, schema_version="1.0.0",
                   content=record, normalized_content=record,
                   confidence=classification_confidence,
                   model_name=output.model_name, prompt_version=output.prompt_version,
               )
               ids.append(id)
           records_created = len(ids)
       Senão se destination == "business_rules":
           db.insert_business_rule(
               workspace_id=workspace_id, source_id=source_id, chunk_id=chunk_id,
               evidence_span_id=evidence_span_id,   # NOT NULL garantido no passo 7
               rule_type=fact_type, schema_version="1.0.0",
               condition=output.validated_data.get("condition", {}),
               action=output.validated_data.get("action", {}),
               confidence=classification_confidence,
               model_name=output.model_name, prompt_version=output.prompt_version,
           )
           records_created = 1
       Senão:  # extracted_facts, single record
           db.insert_extracted_fact(
               workspace_id=workspace_id, source_id=source_id, chunk_id=chunk_id,
               evidence_span_id=evidence_span_id,
               fact_type=fact_type, schema_version="1.0.0",
               content=output.raw_data, normalized_content=output.normalized_content,
               confidence=classification_confidence,
               model_name=output.model_name, prompt_version=output.prompt_version,
           )
           records_created = 1

       Se records_created == 0:
           db.insert_unknown_queue_item(
               workspace_id=workspace_id, source_id=source_id, chunk_id=chunk_id,
               raw_text=chunk.content[:2000],
               suggested_fact_type=fact_type, confidence=classification_confidence,
               metadata={"reason": "no_records_created", "fact_type": fact_type},
           )
           db.update_chunk_status(chunk_id, "needs_review")
           db.mark_job_succeeded(job_id, idempotency_key=idempotency_key)
       Senão:
           db.update_chunk_status(chunk_id, "extracted")
           db.mark_job_succeeded(job_id, idempotency_key=idempotency_key)

10. RETORNAR
   Se records_created == 0:
       return {"status": "succeeded", "chunk_status": "needs_review",
               "reason": "no_records_created", "fact_type": fact_type,
               "records_created": 0}

   logger.info("extraction_succeeded", chunk_id=chunk_id, fact_type=fact_type,
               records_created=records_created)
   return {
       "status": "succeeded",
       "chunk_id": chunk_id,
       "fact_type": fact_type,
       "records_created": records_created,
       "input_tokens": output.input_tokens,
       "output_tokens": output.output_tokens,
   }
```

### Tratamento de exceções técnicas

```python
except openai.RateLimitError as exc:
    db.mark_job_retrying(job_id)
    raise self.retry(exc=exc, countdown=60)

except openai.APITimeoutError as exc:
    db.mark_job_retrying(job_id)
    raise self.retry(exc=exc, countdown=20)

except openai.APIConnectionError as exc:
    db.mark_job_retrying(job_id)
    raise self.retry(exc=exc, countdown=20)

except Exception as exc:
    if self.request.retries >= self.max_retries:
        db.mark_job_failed(job_id, reason=type(exc).__name__)
        logger.error("extraction_failed_final", chunk_id=chunk_id,
                     fact_type=fact_type, error_type=type(exc).__name__)
    else:
        db.mark_job_retrying(job_id)
    raise self.retry(exc=exc)
```

Nunca logar `chunk.content`. Apenas `chunk_id`, `fact_type`, `error_type`.

### Concorrência

```python
app.conf.update(
    worker_concurrency=2,            # extraction é mais custoso — modelo maior
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=60,
    task_time_limit=90,
)
```

---

## Outbox pattern — atualização da TASK-004

Arquivo: `workers/classification/src/worker_classification/extraction_queue.py`

Substituir o `pass` existente pela implementação real:

```python
import os
from supabase import create_client


def enqueue_extraction_job(
    *,
    chunk_id: str,
    workspace_id: str,
    source_id: str,
    fact_type: str,
    destination: str,
    confidence: float,
    prompt_version: str,
    model_name: str,
) -> str:
    """
    Passo 1 do outbox pattern: cria processing_job com status='queued' no DB.
    Deve ser chamado DENTRO da transação da TASK-004.

    Passo 2 (caller responsibility): após o commit da transação, chamar:
        from worker_extraction.tasks import extract_fact
        extract_fact.delay(job_id=job_id, chunk_id=chunk_id, ...)

    Retorna o job_id criado para que o caller possa enfileirar no Celery
    após o commit.
    """
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    result = supabase.table("processing_jobs").insert({
        "workspace_id": workspace_id,
        "source_id": source_id,
        "chunk_id": chunk_id,
        "job_type": "extraction",
        "status": "queued",
        "metadata": {
            "fact_type": fact_type,
            "destination": destination,
            "classification_confidence": confidence,
            "classification_prompt_version": prompt_version,
            "classification_model": model_name,
        },
    }).execute()
    return result.data[0]["id"]
```

### Atualização obrigatória na TASK-004 `tasks.py`

A chamada ao Celery deve acontecer **APÓS** o bloco `with db.transaction():`

```python
# Dentro da transação (passo 6 do TASK-004):
with db.transaction():
    ...
    extraction_job_ids = []
    for decision in result.decisions:
        if decision.destination != "unknown_facts_queue":
            job_id = enqueue_extraction_job(
                chunk_id=chunk_id, workspace_id=workspace_id, source_id=source_id,
                fact_type=decision.fact_type, destination=decision.destination,
                confidence=decision.confidence, prompt_version=result.prompt_version,
                model_name=result.model_name,
            )
            extraction_job_ids.append((job_id, decision))
    ...
    db.mark_job_succeeded(job_id, ...)

# FORA da transação (após commit):
from worker_extraction.tasks import extract_fact
for ext_job_id, decision in extraction_job_ids:
    extract_fact.delay(
        job_id=ext_job_id,
        chunk_id=chunk_id,
        workspace_id=workspace_id,
        source_id=source_id,
        fact_type=decision.fact_type,
        destination=decision.destination,
        classification_confidence=decision.confidence,
        classification_prompt_version=result.prompt_version,
    )
```

---

## Atualização de documentação

### `docs/06-prompts/EXTRACTION_PROMPTS.md` — adicionar ao final

```markdown
## contact_info

```json
{
  "phone": "número literal ou null",
  "email": "email literal ou null",
  "address": "endereço literal ou null",
  "website": "URL literal ou null",
  "whatsapp": "número whatsapp ou null",
  "contact_name": "nome ou departamento ou null"
}
```

Regras:
- Ao menos um campo deve estar preenchido. Se nenhum, retornar `status: "failed"`.
- Preservar formato original (ex: "(11) 99999-9999", não converter).

## faq_item

```json
{
  "question": "pergunta literal do texto",
  "answer": "resposta literal do texto",
  "category": null
}
```

Regras:
- `question` e `answer` são obrigatórios. Se ausentes, retornar `status: "failed"`.
- Não inferir pergunta — só extrair o que estiver explícito.
```

### `docs/04-data/SCHEMA_REGISTRY.md` — corrigir escopo

Alterar:

```diff
-## Escopo MVP
-Somente estes 5 tipos são válidos no MVP:
+## Escopo MVP
+Somente estes 7 tipos são válidos no MVP:

 service_price
 business_hours
 payment_method
 discount_rule
 cancellation_policy
+contact_info
+faq_item
```

E adicionar os Pydantic schemas de `ContactInfo` e `FAQItem` à seção de schemas.

---

## Dependências novas

### `workers/extraction/pyproject.toml`

```toml
[project]
name = "worker-extraction"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "celery[redis]>=5.3",
  "supabase>=2.4",
  "context-builder-model-gateway",
  "context-builder-schema-registry",
  "context-builder-normalizers",
  "context-builder-domain",
]
```

### `.env.example` — confirmar presença

```dotenv
EXTRACTION_MODEL=gpt-4o
```

---

## Testes obrigatórios

### `packages/schema_registry/tests/test_validators.py`

```
✓ validate_extraction("service_price", valid_dict) → valid=True
✓ validate_extraction("service_price", missing_required) → valid=False, errors preenchidos
✓ validate_extraction("contact_info", {"phone": "11 99999"}) → valid=True
✓ validate_extraction("faq_item", {"question": "Q", "answer": "A"}) → valid=True
✓ validate_extraction("faq_item", {"question": "Q"}) → valid=False (answer ausente)
✓ get_pydantic_model("unknown_type") → ValueError
✓ validate_extraction nunca lança exceção
```

### `packages/normalizers/tests/test_pre_extract.py`

```
✓ service_price com "R$ 150" → price_amount=150.0
✓ business_hours com "9h" → open_time="09:00"
✓ discount_rule com "10%" → discount_percentage=10.0
✓ campo não-normalizável → valor original preservado
✓ nenhum fact_type → dict retornado sem modificação
```

### `workers/extraction/tests/test_extractor.py`

Mockar `get_model_gateway()`:

```
✓ status="ok", fact_type="service_price" → ExtractionOutput.status="ok", validated_data preenchido
✓ LLM retorna status="failed" → ExtractionOutput.status="failed"
✓ JSON malformado → ExtractionOutput.status="parse_failed"
✓ data falha Pydantic → ExtractionOutput.status="validation_failed", validation_errors preenchido
✓ business_hours com 3 dias → is_multi=True, records com 3 itens
✓ business_hours com item inválido numa lista → item ignorado, records com N-1 itens
✓ contact_info com quote presente → evidence_quote preenchido
✓ extract nunca lança exceção para JSON inválido
```

### `workers/extraction/tests/test_tasks.py`

Mockar `extract`, `db.*`, `build_evidence_span_input`:

```
✓ job já succeeded → cached=True sem LLM
✓ workspace_mismatch → failed sem LLM
✓ output.status="ok" → extracted_fact inserido, chunk.status="extracted"
✓ output.status="failed" → unknown_queue inserido, chunk.status="needs_review", job.status="succeeded"
✓ output.status="parse_failed" → retry interno com retry=True chamado antes de unknown_queue
✓ output.status="validation_failed" → retry interno com retry=True
✓ contact_info com todos os campos null → unknown_queue, reason="empty_contact_info"
✓ destination="business_rules" + quote ausente → unknown_queue, reason="missing_evidence_quote"
✓ business_hours com 3 records → 3 extracted_facts inseridos, records_created=3
✓ business_hours com 0 records válidos → unknown_queue, chunk.status="needs_review"
✓ RateLimitError → mark_job_retrying + self.retry(countdown=60)
✓ domain failure (parse_failed após retry) → self.retry NÃO chamado
✓ mark_job_succeeded dentro da transação (mesmo contexto que inserts)
✓ token_usage logado sempre (mesmo em falha)
✓ idempotency_key inclui fact_type, prompt_version, model_name
✓ raw_response nunca presente no insert (apenas raw_response_hash)
```

---

## O que NÃO fazer

- Não implementar contradiction detection (TASK-007+).
- Não implementar revisão humana (TASK-006).
- Não implementar publication flow (TASK-007).
- Não chamar LLM mais de 2 vezes por job (1 normal + 1 retry interno com sufixo).
- Não logar `chunk.content` nem `raw_response` completo.
- Não salvar `raw_response` no banco — apenas `raw_response_hash`.
- Não criar extraction job dentro da transação E chamar `.delay()` no mesmo bloco — usar outbox.
- Não alterar `supabase/migrations/`.
- Não usar `completed` — usar `succeeded`.
- Não expandir fact_types além dos 7 definidos.

---

## Critérios de aceite

```
[ ] pytest packages/schema_registry/tests/test_validators.py -v → todos passam
[ ] pytest packages/normalizers/tests/test_pre_extract.py -v → todos passam
[ ] pytest workers/extraction/tests/test_extractor.py -v → todos passam
[ ] pytest workers/extraction/tests/test_tasks.py -v → todos passam
[ ] python -c "from schema_registry.validators import validate_extraction, get_pydantic_model" → sem erro
[ ] python -c "from normalizers.pre_extract import pre_normalize" → sem erro
[ ] python -c "from worker_extraction.extractor import extract" → sem erro
[ ] python -c "from worker_extraction.tasks import extract_fact" → sem erro
[ ] validate_extraction("contact_info", ...) funciona (sem KeyError)
[ ] validate_extraction("faq_item", ...) funciona (sem KeyError)
[ ] business_hours com 2 dias → records_created=2 (teste unitário)
[ ] business_hours com 0 records válidos → chunk.status="needs_review" e reason="no_records_created"
[ ] contact_info com todos os campos null/vazios → chunk.status="needs_review" e reason="empty_contact_info"
[ ] destination="business_rules" + quote vazio → chunk.status="needs_review" (mock)
[ ] output.status="parse_failed" → retry interno com retry=True antes de ir para unknown
[ ] extract_fact.delay() chamado APÓS commit da transação (verificar via mock de transaction)
[ ] idempotency_key inclui fact_type + prompt_version + model_name (teste unitário)
[ ] token_usage logado mesmo quando output.status="failed" (mock)
[ ] celery -A worker_extraction.celery_app worker --dry-run → sem erro
[ ] workers/extraction listado no root `pyproject.toml` (uv workspace)
[ ] `.github/workflows/ci.yml` executa testes de `workers/extraction`
[ ] ruff check . → zero erros
[ ] mypy packages/schema_registry workers/extraction → zero erros
[ ] SCHEMA_REGISTRY.md declara 7 fact types
[ ] EXTRACTION_PROMPTS.md contém prompts para contact_info e faq_item
```

---

## Referências

- `CLAUDE.md` — pipeline, regras de retry, fact types MVP
- `docs/06-prompts/EXTRACTION_PROMPTS.md` — atualizar nesta task
- `docs/04-data/SCHEMA_REGISTRY.md` — atualizar nesta task
- `docs/03-pipeline/PIPELINE.md` — fluxo de extração, normalização, roteamento
- `docs/03-pipeline/EXTRACTION_CONTRACTS.md` — contratos de entrada/saída
- `supabase/migrations/007_evidence_spans.sql` — schema do evidence_span
- `supabase/migrations/009_extracted_facts.sql` — schema do extracted_facts
- `supabase/migrations/010_business_rules.sql` — schema do business_rules (evidence_span_id NOT NULL)
- `supabase/migrations/011_unknown_queue.sql` — schema do unknown_facts_queue
- `supabase/migrations/016_jobs.sql` — processing_jobs, job_status enum
- `supabase/migrations/017_token_usage.sql` — token_usage_log
