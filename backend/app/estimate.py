"""Live credit estimates (section 9, step 2b). Never typed in by hand: every number comes
from the catalog prices and a token plan per mode.

Token plans come straight from the plan's worked examples, so the tests can check them:
  Normal 3,000 in / 700 out. Think Again: draft 3,000/1,500, each round critic 4,500/400 +
  rewrite 5,000/1,500. Overthink: each try 3,000/8,000, judge reads 3,000 per try, writes 800.
"""
from decimal import Decimal

from .pricing import EFFORT_SHARE, call_cost, credits_for_cost

WEB_SEARCH_USD = Decimal("0.007")
IMAGE_OUT_TOKENS = 1200  # what one generated picture costs in output tokens (tools/image.py sends this cap)


def _price(m: dict) -> tuple[float, float, float]:
    return m["price_in"] or 0.0, m["price_out"] or 0.0, m.get("price_cached") or m["price_in"] or 0.0


def _cost(m: dict, tin: int, tout: int, cached: int = 0) -> Decimal:
    pin, pout, pc = _price(m)
    return call_cost(pin, pout, tin, tout, cached, pc)


def _think_out(base_think: int, answer: int, effort: str, default_effort: str, cap: int) -> int:
    """Scale the thinking part of a try by the effort dial. Never above max_tokens."""
    d = EFFORT_SHARE.get(default_effort, 0.8) or 0.8
    think = int(base_think * EFFORT_SHARE.get(effort, d) / d)
    return min(think + answer, cap)


def estimate(mode: dict, brains: dict[str, list[dict]], *, rounds: int | None = None, tries: int | None = None,
             effort: str = "auto", chart: bool = False, searches: int | None = None,
             image_model: dict | None = None) -> dict:
    """brains: role -> list of model rows. Returns {usd, credits, parts}."""
    r = mode["runner"]
    p = mode.get("params", {})
    one = lambda role: brains[role][0]
    parts: list[tuple[str, Decimal]] = []
    eff = lambda role, default: mode["reasoning"].get(role, default) if effort == "auto" else effort

    if r == "single":
        out = 700 + (1500 if chart else 0)
        parts.append(("answer", _cost(one("answer"), 3000, out)))
    elif r == "think_again":
        n = rounds if rounds is not None else p.get("default_rounds", 2)
        w, c = one("write"), one("critic")
        parts.append(("draft", _cost(w, 3000, 1500)))
        for k in range(n):
            parts.append((f"critic {k+1}", _cost(c, 4500, 400)))
            parts.append((f"rewrite {k+1}", _cost(w, 5000, 1500)))
    elif r == "overthink":
        n = tries if tries is not None else p.get("default_tries", 3)
        t, j = one("think"), one("judge")
        tout = _think_out(6000, 2000, eff("think", "high"), "high", mode["max_tokens"]["think"])
        for k in range(n):
            parts.append((f"try {k+1}", _cost(t, 3000, tout)))
        parts.append(("judge", _cost(j, 3000 * n, 800)))
    elif r == "council":
        members = brains["members"]
        for k, m in enumerate(members):
            parts.append((f"member {k+1}", _cost(m, 3000, 1500)))
        parts.append(("judge", _cost(one("judge"), int(2500 * len(members)), 1200)))
    elif r == "two_brains":
        tout = _think_out(6000, 1000, eff("think", "high"), "high", mode["max_tokens"]["think"])
        parts.append(("think", _cost(one("think"), 3000, tout)))
        parts.append(("answer", _cost(one("answer"), 4000, 700)))
    elif r == "think_team":
        for k, m in enumerate(brains["think"]):
            parts.append((f"thinker {k+1}", _cost(m, 3000, 3000)))
        parts.append(("answer", _cost(one("answer"), 3000 + 500 * len(brains["think"]), 700)))
    elif r == "research":
        n = searches if searches is not None else p.get("max_searches", 4)
        parts.append(("plan", _cost(one("planner"), 800, 200)))
        parts.append(("searches", WEB_SEARCH_USD * n))
        parts.append(("write", _cost(one("writer"), 12000, 1500)))
    elif r == "deep":
        steps = min(int(p.get("max_steps", 8)), 6)  # plan: a typical Deep task is 6 steps
        w = one("worker")
        parts.append(("plan", _cost(one("planner"), 3000, 600)))
        for k in range(steps):
            parts.append((f"step {k+1}", _cost(w, 4000, 2000, cached=8000)))
        parts.append(("check", _cost(one("checker"), 3000, 300)))
    elif r == "create":
        # outline + 10 slides/sections + check. Plan: PPT 10 slides ~ 80 credits on Sonnet.
        w = one("worker")
        parts.append(("outline", _cost(w, 2000, 800)))
        for k in range(10):
            parts.append((f"item {k+1}", _cost(w, 3000, 700)))
        parts.append(("check", _cost(one("checker"), 3000, 300)))
    if image_model is not None:
        # One generated picture. Image models bill the picture as output tokens, so this is the costly part.
        parts.append(("picture", _cost(image_model, 300, IMAGE_OUT_TOKENS)))
    total = sum((c for _, c in parts), Decimal(0))
    media = sum((c for n, c in parts if n == "picture"), Decimal(0))
    return {"usd": float(total), "credits": max(1, credits_for_cost(total)),
            # A drawn picture is paid media, not thinking, so the caller may allow it above the mode's cap.
            "media_credits": credits_for_cost(media) if media else 0,
            "parts": [{"name": n, "usd": float(c)} for n, c in parts]}
