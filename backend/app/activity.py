"""The user's blueprint: an append-only log of everything a user did, plus a summary built from all tables.

Each row: who (user_id), what (kind), details (JSON), who did it (actor: the user, or an admin id), when.
"""
from .db import DB, jdump, jload, now


def log(db: DB, user_id: str, kind: str, actor: str | None = None, **detail) -> None:
    db.run("INSERT INTO activity(user_id,kind,detail,actor,created_at) VALUES(?,?,?,?,?)",
           (user_id, kind, jdump(detail), actor or user_id, now()))


def timeline(db: DB, user_id: str, limit: int = 100, before: int | None = None) -> list[dict]:
    rows = db.all("SELECT id,kind,detail,actor,created_at FROM activity WHERE user_id=? AND (? IS NULL OR id<?) "
                  "ORDER BY id DESC LIMIT ?", (user_id, before, before, min(limit, 500)))
    return [{**r, "detail": jload(r["detail"], {})} for r in rows]


def blueprint(db: DB, user_id: str) -> dict:
    """Everything known about a user, in one place (for the user's own view and for admins)."""
    from . import memory, plans, wallet
    u = db.one("SELECT * FROM users WHERE id=?", (user_id,)) or {}
    day = now() - (now() % 86400)
    by_mode = db.all("SELECT mode, COUNT(*) runs, SUM(credits_used) credits, SUM(usd_used) usd FROM tasks "
                     "WHERE user_id=? GROUP BY mode ORDER BY runs DESC", (user_id,))
    by_model = db.all("SELECT model, COUNT(*) calls, SUM(input_tokens+cached_tokens) tokens_in, SUM(output_tokens) tokens_out, "
                      "SUM(cost_usd) usd FROM usage_events WHERE user_id=? GROUP BY model ORDER BY calls DESC LIMIT 15", (user_id,))
    convs = db.all("SELECT c.id, c.title, c.summary, c.updated_at, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id) messages "
                   "FROM conversations c WHERE c.user_id=? ORDER BY c.updated_at DESC LIMIT 50", (user_id,))
    rules = plans.rules(u.get("plan") or "free")
    return {
        "user": public_user(u),
        "wallet": {"balance": wallet.balance(db, user_id), "held": wallet.held(db, user_id), "available": wallet.available(db, user_id),
                   "spent_today": wallet.spent_today(db, user_id), "spent_month": wallet.spent_month(db, user_id)},
        "limits": {"daily": u.get("daily_limit") or rules.get("daily_credit_cap"), "monthly": u.get("monthly_limit"),
                   "daily_custom": u.get("daily_limit") is not None, "monthly_custom": u.get("monthly_limit") is not None},
        "totals": {
            "conversations": db.scalar("SELECT COUNT(*) FROM conversations WHERE user_id=?", (user_id,)),
            "messages": db.scalar("SELECT COUNT(*) FROM messages m JOIN conversations c ON c.id=m.conversation_id "
                                  "WHERE c.user_id=? AND m.role='user'", (user_id,)),
            "runs": db.scalar("SELECT COUNT(*) FROM tasks WHERE user_id=?", (user_id,)),
            "runs_today": db.scalar("SELECT COUNT(*) FROM tasks WHERE user_id=? AND created_at>=?", (user_id, day)),
            "files": db.scalar("SELECT COUNT(*) FROM workspace_files WHERE user_id=? AND path LIKE 'out/%'", (user_id,)),
            "credits_used": int(db.scalar("SELECT -SUM(delta) FROM credit_ledger WHERE user_id=? AND delta<0", (user_id,))),
            "ai_cost_usd": round(float(db.scalar("SELECT SUM(cost_usd) FROM usage_events WHERE user_id=?", (user_id,), 0.0)), 6),
            "purchases_usd": round(float(db.scalar("SELECT SUM(amount_usd) FROM purchases WHERE user_id=? AND status='paid'",
                                                   (user_id,), 0.0)), 2),
            "memories": db.scalar("SELECT COUNT(*) FROM memories WHERE user_id=? AND deleted=0", (user_id,)),
            "thumbs_up": db.scalar("SELECT COUNT(*) FROM messages m JOIN conversations c ON c.id=m.conversation_id "
                                   "WHERE c.user_id=? AND m.rating=1", (user_id,)),
            "thumbs_down": db.scalar("SELECT COUNT(*) FROM messages m JOIN conversations c ON c.id=m.conversation_id "
                                     "WHERE c.user_id=? AND m.rating=-1", (user_id,)),
        },
        "by_mode": by_mode, "by_model": by_model, "conversations": convs,
        "profile": jload((db.one("SELECT data FROM profiles WHERE user_id=?", (user_id,)) or {}).get("data"), {}),
        "memories": memory.listing(db, user_id),
        "purchases": db.all("SELECT * FROM purchases WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (user_id,)),
        "ledger": db.all("SELECT delta,reason,task_id,created_at FROM credit_ledger WHERE user_id=? ORDER BY id DESC LIMIT 50", (user_id,)),
        "timeline": timeline(db, user_id, 60),
    }


def public_user(u: dict) -> dict:
    keys = ("id", "name", "email", "plan", "role", "status", "auto_spend", "private_route", "daily_limit", "monthly_limit",
            "memory_enabled", "created_at", "last_seen_at", "plan_renews_at", "note")
    out = {k: u.get(k) for k in keys}
    out["registered"] = bool(u.get("email"))
    return out
