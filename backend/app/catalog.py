"""Model catalog (section 3 and 8). Prices live in the database, never in code paths.

Seeded from the plan's model menu. `sync_live` then reads OpenRouter's model list,
updates prices, marks models that no longer exist as unavailable, and raises an alarm
when a price jumps by more than 20%.
Unknown live models are stored with approved=0, so they appear only after you approve them.
"""
from .config import settings
from .db import DB, now

# id, name, lab, region, tier, in $/M, out $/M, thinks, reasoning_style
SEED = [
    ("deepseek/deepseek-v4.1-flash", "DeepSeek V4.1 Flash", "DeepSeek", "china", "quick", 0.0438, 0.1752, 0, "effort"),
    ("qwen/qwen3.8-flash", "Qwen3.8 Flash", "Alibaba", "china", "quick", 0.15, 0.47, 1, "budget"),
    ("anthropic/claude-haiku-5.5", "Claude Haiku 5.5", "Anthropic", "west", "quick", 0.10, 0.50, 1, "budget"),
    ("deepseek/deepseek-v4-pro-0813", "DeepSeek V4 Pro 0813", "DeepSeek", "china", "smart", 0.2495, 0.7484, 0, "effort"),
    ("minimax/minimax-m3", "MiniMax M3", "MiniMax", "china", "smart", 0.23, 0.96, 0, "effort"),
    ("qwen/qwen3.8-max-0902", "Qwen3.8 Max (0902)", "Alibaba", "china", "smart", 2.0, 6.0, 1, "budget"),
    ("anthropic/claude-sonnet-5.5", "Claude Sonnet 5.5", "Anthropic", "west", "smart", 2.0, 10.0, 1, "budget"),
    ("google/gemini-4-argon", "Gemini 4 Argon", "Google", "west", "smart", 2.0, 10.0, 1, "budget"),
    ("openai/gpt-6.1-sol-pro", "GPT-6.1 Sol Pro", "OpenAI", "west", "smart", 2.0, 10.0, 1, "effort"),
    ("moonshotai/kimi-k3", "Kimi K3", "Moonshot AI", "china", "genius", 0.70, 15.0, 1, "effort"),
    ("z-ai/glm-5.3-prime", "GLM 5.3 Prime", "Z.ai", "china", "genius", 2.80, 8.80, 1, "effort"),
    ("qwen/qwen3.8-max-prime", "Qwen3.8 Max Prime", "Alibaba", "china", "genius", 4.0, 12.0, 1, "budget"),
    ("anthropic/claude-opus-5.5", "Claude Opus 5.5", "Anthropic", "west", "genius", 4.0, 20.0, 1, "budget"),
    ("anthropic/claude-fable-5.1", "Claude Fable 5.1", "Anthropic", "west", "genius", 10.0, 50.0, 0, "budget"),
]
# Cached input is about 5% of the input price on Claude (section 8). Others: same as input.
CACHED_FACTOR = {"anthropic": 0.05}
CODING_BRAINS = ["moonshotai/kimi-k2.7-code", "qwen/qwen3-coder-next"]

PRICE_ALARM = 0.20


def seed(db: DB) -> None:
    for (mid, name, lab, region, tier, pin, pout, thinks, style) in SEED:
        if db.one("SELECT id FROM model_catalog WHERE id=?", (mid,)):
            continue
        cached = pin * CACHED_FACTOR.get(mid.split("/")[0], 1.0)
        db.run(
            "INSERT INTO model_catalog(id,name,lab,region,tier,price_in,price_out,price_cached,thinks,"
            "reasoning_style,available,approved,private_route,source,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,1,1,1,'seed',?)",
            (mid, name, lab, region, tier, pin, pout, cached, thinks, style, now()),
        )
        db.run("INSERT INTO model_prices(model_id,price_in,price_out,started_at) VALUES(?,?,?,?)",
               (mid, pin, pout, now()))


def get(db: DB, model_id: str) -> dict | None:
    return db.one("SELECT * FROM model_catalog WHERE id=?", (model_id,))


def listing(db: DB, tiers_allowed: list[str] | None = None) -> list[dict]:
    rows = db.all("SELECT * FROM model_catalog WHERE approved=1 AND available=1 AND id NOT LIKE '%:free' "
                  "ORDER BY CASE tier WHEN 'quick' THEN 0 WHEN 'smart' THEN 1 ELSE 2 END, price_out")
    if tiers_allowed is not None:
        rows = [r for r in rows if r["tier"] in tiers_allowed]
    return rows


def _blend(r: dict) -> float:
    # Thinking is paid as output, so output price matters most.
    return 0.3 * (r["price_in"] or 0) + 0.7 * (r["price_out"] or 0)


def resolve(db: DB, tier: str, *, need_thinks: bool = False, exclude: tuple = (),
            policy: str | None = None, tiers_allowed: list[str] | None = None) -> dict:
    """Pick a model for a tier. Raises LookupError when nothing fits."""
    policy = policy or settings.brain_policy
    rows = [r for r in listing(db, tiers_allowed) if r["id"] not in exclude]
    if policy == "cheap":
        # Testing policy: genius work runs on the cheapest Smart model.
        pool = [r for r in rows if r["tier"] in ("quick", "smart")]
        if tier == "quick":
            pool = [r for r in pool if r["tier"] == "quick"] or pool
    else:
        pool = [r for r in rows if r["tier"] == tier] or rows
    if need_thinks:
        thinkers = [r for r in pool if r["thinks"]]
        pool = thinkers or pool
    if not pool:
        raise LookupError(f"no model available for tier {tier}")
    return sorted(pool, key=_blend)[0]


def fallbacks(db: DB, primary: str, n: int = 2, *, private_only: bool = False) -> list[str]:
    """Backup models for OpenRouter's `models` list: same tier first, cheapest first."""
    cur = get(db, primary)
    rows = listing(db)
    if private_only:
        rows = [r for r in rows if r["private_route"]]
    same = [r for r in rows if cur and r["tier"] == cur["tier"] and r["id"] != primary]
    same.sort(key=_blend)
    return [r["id"] for r in same[:n]]


def sync_live(db: DB, live_models: list[dict]) -> dict:
    """Update the catalog from GET /api/v1/models. Returns a report."""
    report = {"updated": 0, "missing": [], "new": 0, "alarms": []}
    live = {m["id"]: m for m in live_models}
    for row in db.all("SELECT * FROM model_catalog"):
        m = live.get(row["id"])
        if not m:
            db.run("UPDATE model_catalog SET available=0 WHERE id=?", (row["id"],))
            report["missing"].append(row["id"])
            continue
        _apply_live(db, row, m, report)
    for mid, m in live.items():
        if db.one("SELECT id FROM model_catalog WHERE id=?", (mid,)):
            continue
        pr = m.get("pricing") or {}
        pin, pout = _per_million(pr.get("prompt")), _per_million(pr.get("completion"))
        if pin is None or pout is None:
            continue
        params = m.get("supported_parameters") or []
        thinks = 1 if ("reasoning" in params or "include_reasoning" in params) else 0
        db.run(
            "INSERT INTO model_catalog(id,name,lab,region,tier,price_in,price_out,price_cached,thinks,"
            "reasoning_style,context,available,approved,private_route,source,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,1,0,1,'live',?)",
            (mid, m.get("name") or mid, mid.split("/")[0], "unknown", _guess_tier(pout), pin, pout,
             _per_million(pr.get("input_cache_read")) or pin, thinks, "effort", m.get("context_length"), now()),
        )
        report["new"] += 1
    return report


def _apply_live(db: DB, row: dict, m: dict, report: dict) -> None:
    pr = m.get("pricing") or {}
    pin, pout = _per_million(pr.get("prompt")), _per_million(pr.get("completion"))
    params = m.get("supported_parameters") or []
    thinks = 1 if ("reasoning" in params or "include_reasoning" in params) else row["thinks"]
    if pin is not None and pout is not None:
        old_out = row["price_out"] or 0
        if old_out and abs(pout - old_out) / old_out > PRICE_ALARM:
            report["alarms"].append({"model": row["id"], "old_out": old_out, "new_out": pout})
        if (pin, pout) != (row["price_in"], row["price_out"]):
            db.run("INSERT INTO model_prices(model_id,price_in,price_out,started_at) VALUES(?,?,?,?)",
                   (row["id"], pin, pout, now()))
        cached = _per_million(pr.get("input_cache_read"))
        if cached is None:
            cached = pin * CACHED_FACTOR.get(row["id"].split("/")[0], 1.0)
        db.run("UPDATE model_catalog SET price_in=?,price_out=?,price_cached=?,thinks=?,context=?,"
               "available=1,source='live',updated_at=? WHERE id=?",
               (pin, pout, cached, thinks, m.get("context_length"), now(), row["id"]))
    else:
        db.run("UPDATE model_catalog SET available=1, thinks=? WHERE id=?", (thinks, row["id"]))
    report["updated"] += 1


def _per_million(v) -> float | None:
    try:
        return float(v) * 1_000_000
    except (TypeError, ValueError):
        return None


def _guess_tier(price_out: float) -> str:
    return "quick" if price_out < 1 else "smart" if price_out < 12 else "genius"


def approve(db: DB, model_id: str, tier: str | None = None, on: bool = True) -> None:
    db.run("UPDATE model_catalog SET approved=? WHERE id=?", (1 if on else 0, model_id))
    if tier:
        db.run("UPDATE model_catalog SET tier=? WHERE id=?", (tier, model_id))
