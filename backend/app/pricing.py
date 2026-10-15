"""Money math from section 9 of the plan.

credits = ceil(AI cost in dollars x 1.055 / 0.003)
Decimal is used so the rounding is exact (32.002 must become 33, never 32).
"""
from decimal import Decimal, ROUND_CEILING

from .config import settings

# Effort dial (section 3). Share of max_tokens that thinking may use.
EFFORT_SHARE = {"off": 0.0, "low": 0.20, "medium": 0.50, "high": 0.80, "max": 0.95}
# What we send to OpenRouter as reasoning.effort.
EFFORT_API = {"off": "none", "low": "low", "medium": "medium", "high": "high", "max": "xhigh"}
EFFORT_ORDER = ["off", "low", "medium", "high", "max"]
# Highest effort each plan may use.
PLAN_MAX_EFFORT = {"free": "low", "student": "high", "pro": "max", "school": "high"}


def _d(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    if isinstance(x, str):
        return Decimal(x)
    return Decimal(repr(float(x)))


def credits_for_cost(usd) -> int:
    """Round UP. 0 dollars is 0 credits; any real spend is at least 1."""
    usd = _d(usd)
    if usd <= 0:
        return 0
    raw = usd * Decimal(settings.fee_factor) / Decimal(settings.credit_cost_usd)
    return max(1, int(raw.to_integral_value(rounding=ROUND_CEILING)))


def call_cost(price_in: float, price_out: float, in_tokens: int, out_tokens: int,
              cached_tokens: int = 0, price_cached: float | None = None) -> Decimal:
    """Dollars for one call. Prices are dollars per 1 million tokens.

    in_tokens counts only NEW input tokens. cached_tokens are priced separately.
    """
    pin, pout = _d(price_in), _d(price_out)
    pc = _d(price_cached) if price_cached is not None else pin
    m = Decimal(1_000_000)
    return (Decimal(in_tokens) * pin + Decimal(cached_tokens) * pc + Decimal(out_tokens) * pout) / m


def thinking_ceiling(max_tokens: int, effort: str) -> int:
    return int(max_tokens * EFFORT_SHARE.get(effort, 0.0))


def clamp_effort(effort: str, plan: str) -> str:
    """Never let a plan use more effort than it paid for."""
    if effort == "auto":
        return effort
    from . import plans
    top = plans.rules(plan).get("max_effort") or PLAN_MAX_EFFORT.get(plan, "low")
    if effort not in EFFORT_ORDER:
        return "off"
    return effort if EFFORT_ORDER.index(effort) <= EFFORT_ORDER.index(top) else top
