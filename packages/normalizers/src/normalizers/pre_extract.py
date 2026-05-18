from __future__ import annotations

from normalizers.currency import normalize_currency
from normalizers.percent import normalize_percent
from normalizers.time import normalize_time


def pre_normalize(fact_type: str, raw_data: dict) -> dict:  # type: ignore[type-arg]
    """
    Applies deterministic normalizers to string fields in raw_data before
    Pydantic validation. Fields that cannot be normalized are left unchanged.
    Never raises.
    """
    data: dict = dict(raw_data)  # type: ignore[type-arg]

    try:
        if fact_type == "service_price":
            data = _normalize_service_price(data)
        elif fact_type == "business_hours":
            data = _normalize_business_hours(data)
        elif fact_type == "discount_rule":
            data = _normalize_discount_rule(data)
        elif fact_type == "cancellation_policy":
            data = _normalize_cancellation_policy(data)
        # payment_method, contact_info, faq_item: no numeric normalization needed
    except Exception:
        pass  # preserve original data on unexpected error

    return data


# ---------------------------------------------------------------------------
# Per-type helpers
# ---------------------------------------------------------------------------


def _normalize_service_price(d: dict) -> dict:  # type: ignore[type-arg]
    for field in ("price_amount", "min_price", "max_price"):
        val = d.get(field)
        if isinstance(val, str):
            money = normalize_currency(val)
            if money is not None:
                d[field] = money.amount
    return d


def _normalize_business_hours(d: dict) -> dict:  # type: ignore[type-arg]
    for field in ("open_time", "close_time"):
        val = d.get(field)
        if isinstance(val, str) and val.strip():
            normalized = normalize_time(val)
            if normalized is not None:
                d[field] = normalized
    return d


def _normalize_discount_rule(d: dict) -> dict:  # type: ignore[type-arg]
    action = d.get("action")
    if not isinstance(action, dict):
        return d
    action = dict(action)

    pct = action.get("discount_percentage")
    if isinstance(pct, str):
        result = normalize_percent(pct)
        if result is not None:
            action["discount_percentage"] = result

    fixed = action.get("discount_fixed")
    if isinstance(fixed, str):
        money = normalize_currency(fixed)
        if money is not None:
            action["discount_fixed"] = money.amount

    d["action"] = action
    return d


def _normalize_cancellation_policy(d: dict) -> dict:  # type: ignore[type-arg]
    pct = d.get("penalty_percentage")
    if isinstance(pct, str):
        result = normalize_percent(pct)
        if result is not None:
            d["penalty_percentage"] = result

    fixed = d.get("penalty_fixed")
    if isinstance(fixed, str):
        money = normalize_currency(fixed)
        if money is not None:
            d["penalty_fixed"] = money.amount

    return d
