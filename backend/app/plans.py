"""Plans and credit packs (section 9, step 4). Stored in the database so an admin can change prices,
credits and benefits without a code change. The constants below are only the first seed.

A plan row:  id, name, kind (subscription | topup), price_usd, credits, period_days, benefits (list of
lines shown to users), rules (what it unlocks), active, sort.
"""
import threading

from .db import DB, jdump, jload, now

PLAN_RULES = {
    "free": {"tiers": ["quick"], "max_rounds": 1, "max_tries": 1, "charts_per_day": 2, "retention_days": 7,
             "storage_mb": 20, "mcp": False, "images": False, "private_default": False},
    "student": {"tiers": ["quick", "smart"], "max_rounds": 3, "max_tries": 3, "charts_per_day": 50, "retention_days": 14,
                "storage_mb": 500, "mcp": False, "images": True, "private_default": False},
    "pro": {"tiers": ["quick", "smart", "genius"], "max_rounds": 5, "max_tries": 5, "charts_per_day": 500,
            "retention_days": 21, "storage_mb": 5000, "mcp": True, "images": True, "private_default": False},
    "school": {"tiers": ["quick", "smart", "genius"], "max_rounds": 3, "max_tries": 3, "charts_per_day": 200,
               "retention_days": 21, "storage_mb": 2000, "mcp": True, "images": True, "private_default": True},
}
SEED_EXTRA = {
    "free": {"max_effort": "low", "daily_credit_cap": 100},
    "student": {"max_effort": "high", "daily_credit_cap": 800},
    "pro": {"max_effort": "max", "daily_credit_cap": 2000},
    "school": {"max_effort": "high", "daily_credit_cap": 1000},
}
SEED_PLANS = [
    ("free", "Free", "subscription", 0, 100, 30,
     ["100 sign-up gift credits", "Fast, Normal and Think Again on Quick brains", "2 charts a day"]),
    ("student", "Student", "subscription", 8, 800, 30,
     ["800 credits every month", "All study modes on Quick and Smart brains", "Effort up to High", "Word and PPT files"]),
    ("pro", "Pro", "subscription", 20, 2000, 30,
     ["2,000 credits every month", "Every mode, including Overthink, Council and Think Team",
      "Genius brains and Max effort", "5 GB of file storage"]),
    ("school", "School", "subscription", 12, 1000, 30,
     ["1,000 credits per student every month", "Private route (ZDR) on by default", "Teacher-controlled brains"]),
    ("pack_starter", "Starter Pack (500)", "topup", 5, 500, 365, ["500 one-time credits ($0.01/credit)", "Valid for 12 months"]),
    ("pack_small", "Top-up 800", "topup", 10, 800, 365, ["800 extra credits", "Valid for 12 months"]),
    ("pack_standard", "Standard Pack (1,000)", "topup", 10, 1000, 365, ["1,000 one-time credits", "Valid for 12 months"]),
    ("pack_big", "Big Pack (2,100)", "topup", 20, 2100, 365, ["2,100 credits (5% bonus)", "Valid for 12 months"]),
    ("pack_large", "Top-up 2,500", "topup", 25, 2500, 365, ["2,500 extra credits", "Valid for 12 months"]),
    ("pack_large_50", "Large Pack (5,500)", "topup", 50, 5500, 365, ["5,500 credits (10% bonus)", "Valid for 12 months"]),
]
DEFAULT_RULES = PLAN_RULES["free"] | SEED_EXTRA["free"]
RULE_KEYS = {"tiers", "max_rounds", "max_tries", "charts_per_day", "retention_days", "storage_mb", "mcp", "images",
             "private_default", "max_effort", "daily_credit_cap", "modes"}

_db: DB | None = None
_cache: dict[str, dict] | None = None
_lock = threading.Lock()


def bind(db: DB, mode_rows: list[dict] | None = None) -> None:
    """Point the plan reader at this database and seed it the first time."""
    global _db, _cache
    _db, _cache = db, None
    if db.scalar("SELECT COUNT(*) FROM plans") == 0:
        for n, (pid, name, kind, price, credits, days, benefits) in enumerate(SEED_PLANS):
            rules = {}
            if kind == "subscription":
                rules = {**PLAN_RULES[pid], **SEED_EXTRA[pid]}
                if mode_rows:
                    rules["modes"] = [m["id"] for m in mode_rows if pid in m.get("plans", [])]
            db.run("INSERT INTO plans(id,name,kind,price_usd,credits,period_days,benefits,rules,active,sort,updated_at) "
                   "VALUES(?,?,?,?,?,?,?,?,1,?,?)", (pid, name, kind, price, credits, days, jdump(benefits), jdump(rules), n, now()))
    ensure_owner(db, mode_rows)


OWNER_ID = "owner"
OWNER_CREDITS = 100_000


def ensure_owner(db: DB, mode_rows: list[dict] | None = None) -> None:
    """The hidden Owner plan: everything unlocked. Used when UNLOCK_ALL=1 (one-person setups)."""
    rules = {"tiers": ["quick", "smart", "genius"], "max_rounds": 5, "max_tries": 5, "charts_per_day": 100000, "retention_days": 365,
             "storage_mb": 100000, "mcp": True, "images": True, "private_default": False, "max_effort": "max",
             "daily_credit_cap": 10_000_000}
    if mode_rows is not None:
        rules["modes"] = [m["id"] for m in mode_rows]
    row = db.one("SELECT id FROM plans WHERE id=?", (OWNER_ID,))
    if row:
        db.run("UPDATE plans SET rules=? WHERE id=?", (jdump(rules), OWNER_ID))
    else:
        db.run("INSERT INTO plans(id,name,kind,price_usd,credits,period_days,benefits,rules,active,sort,updated_at) "
               "VALUES(?,?,?,?,?,?,?,?,0,99,?)",
               (OWNER_ID, "Owner", "subscription", 0, OWNER_CREDITS, 3650, jdump(["Everything unlocked"]), jdump(rules), now()))
    invalidate()


def invalidate() -> None:
    global _cache
    _cache = None


def _load() -> dict[str, dict]:
    global _cache
    with _lock:
        if _cache is None:
            if _db is None:
                _cache = {}
            else:
                rows = _db.all("SELECT * FROM plans ORDER BY sort, price_usd")
                _cache = {r["id"]: {**r, "benefits": jload(r["benefits"], []), "rules": jload(r["rules"], {})} for r in rows}
        return _cache


def all_plans(include_inactive: bool = False) -> list[dict]:
    return [p for p in _load().values() if include_inactive or p["active"]]


def get(plan_id: str) -> dict | None:
    return _load().get(plan_id)


def rules(plan: str) -> dict:
    """What a plan unlocks. Falls back to the built-in seed when no database is bound (unit tests)."""
    row = get(plan)
    if row and row["kind"] == "subscription":
        return {**DEFAULT_RULES, **row["rules"]}
    return {**DEFAULT_RULES, **PLAN_RULES.get(plan, {}), **SEED_EXTRA.get(plan, {})}


def monthly_credits(plan: str) -> int:
    row = get(plan)
    if row:
        return int(row["credits"])
    return {"free": 100, "student": 800, "pro": 2000, "school": 1000}.get(plan, 100)


def clean_rules(data: dict) -> dict:
    """Keep only known rule keys with sane types (admin input)."""
    out = {}
    for k, v in (data or {}).items():
        if k not in RULE_KEYS:
            continue
        if k in ("tiers", "modes"):
            out[k] = [str(x) for x in v][:20] if isinstance(v, list) else []
        elif k in ("mcp", "images", "private_default"):
            out[k] = bool(v)
        elif k == "max_effort":
            out[k] = v if v in ("off", "low", "medium", "high", "max") else "low"
        else:
            out[k] = max(0, min(int(v), 10_000_000))
    return out
