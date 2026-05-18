# SCHEMA_REGISTRY.md — Registry MVP

Fonte de verdade executável: `supabase/migrations/021_seed_mvp_schemas.sql`.

Este documento descreve os Pydantic schemas equivalentes aos JSON Schemas semeados na migration `021`.

## Escopo MVP

Somente estes 5 tipos são válidos no MVP:

```text
service_price
business_hours
payment_method
discount_rule
cancellation_policy
```

Qualquer outro tipo deve ir para `unknown_facts_queue`.

## Pydantic Schemas

```python
from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Currency(StrEnum):
    BRL = "BRL"


class PriceType(StrEnum):
    fixed = "fixed"
    starting_from = "starting_from"
    range = "range"
    unknown = "unknown"


class ServicePrice(StrictModel):
    service_name: str
    price_amount: Optional[float] = None
    currency: Currency
    price_type: PriceType
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class DayOfWeek(StrEnum):
    mon = "mon"
    tue = "tue"
    wed = "wed"
    thu = "thu"
    fri = "fri"
    sat = "sat"
    sun = "sun"


class BusinessHours(StrictModel):
    day_of_week: DayOfWeek
    open_time: Optional[str] = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    close_time: Optional[str] = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    is_closed: bool
    special_case: Optional[str] = None


class PaymentMethodValue(StrEnum):
    pix = "pix"
    cash = "cash"
    credit = "credit"
    debit = "debit"
    bank_transfer = "bank_transfer"
    unknown = "unknown"


class PaymentMethod(StrictModel):
    method: PaymentMethodValue
    accepted: bool
    conditions: Optional[str] = None


class DiscountCondition(StrictModel):
    payment_method: Optional[str] = None
    day_of_week: Optional[str] = None
    min_value: Optional[float] = None


class DiscountAction(StrictModel):
    discount_percentage: Optional[float] = None
    discount_fixed: Optional[float] = None


class DiscountRule(StrictModel):
    condition: DiscountCondition
    action: DiscountAction


class CancellationPolicy(StrictModel):
    notice_required_hours: float
    penalty_percentage: Optional[float] = None
    penalty_fixed: Optional[float] = None
```

## Roteamento

| Tipo | Destino |
|------|---------|
| `service_price` | `extracted_facts` |
| `business_hours` | `extracted_facts` |
| `payment_method` | `extracted_facts` |
| `discount_rule` | `business_rules` |
| `cancellation_policy` | `business_rules` |

## Adicionando Novo Fact Type

Novo tipo só pode ser adicionado quando houver:

1. JSON Schema em migration.
2. Pydantic schema equivalente.
3. Prompt de classificação.
4. Prompt de extração.
5. Normalization policy.
6. Caso de teste.
7. Exemplo em `/examples/`.
