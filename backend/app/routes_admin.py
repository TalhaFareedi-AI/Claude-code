"""Admin routes. Every route needs an admin login (role=admin) or the ADMIN_TOKEN header, and every change is
written to the user's activity log with the admin as the actor, so nothing happens silently."""
from fastapi import Body, HTTPException, Query, Request
from pydantic import BaseModel, Field

from . import activity, billing, memory, plans, wallet, workspace
from .db import jdump, jload, now
from .routes_account import wipe_user

SORTS = {"recent": "COALESCE(u.last_seen_at,u.created_at) DESC", "credits": "credits_used DESC", "runs": "runs DESC",
         "balance": "balance DESC", "newest": "u.created_at DESC", "name": "u.name COLLATE NOCASE"}


class UserPatch(BaseModel):
    name: str | None = Field(None, max_length=40)
    plan: str | None = None
    status: str | None = None
    role: str | None = None
    daily_limit: int | None = Field(None, ge=0, le=10_000_000)
    monthly_limit: int | None = Field(None, ge=0, le=10_000_000)
    clear_daily_limit: bool = False
    clear_monthly_limit: bool = False
    memory_enabled: bool | None = None
    auto_spend: int | None = Field(None, ge=1, le=2000)
    note: str | None = Field(None, max_length=1000)
    extend_plan_days: int | None = Field(None, ge=1, le=3650)


class PlanBody(BaseModel):
    id: str | None = Field(None, pattern=r"^[a-z][a-z0-9_]{1,30}$")
    name: str = Field(..., min_length=1, max_length=40)
    kind: str = "subscription"
    price_usd: float = Field(0, ge=0, le=100000)
    credits: int = Field(0, ge=0, le=100_000_000)
    period_days: int = Field(30, ge=1, le=3650)
    benefits: list[str] = Field(default_factory=list, max_length=12)
    rules: dict = Field(default_factory=dict)
    active: bool = True
    sort: int = 0


def install(app, db, harness, need_admin) -> None:
    def user_rows(where: str = "", params: tuple = (), sort: str = "recent", limit: int = 50, offset: int = 0) -> list[dict]:
        order = SORTS.get(sort, SORTS["recent"])
        rows = db.all(
            "SELECT u.id,u.name,u.email,u.plan,u.role,u.status,u.created_at,u.last_seen_at,u.daily_limit,u.monthly_limit,u.note,"
            " COALESCE((SELECT SUM(delta) FROM credit_ledger l WHERE l.user_id=u.id),0) balance,"
            " COALESCE((SELECT -SUM(delta) FROM credit_ledger l WHERE l.user_id=u.id AND delta<0 AND reason NOT LIKE 'admin%'),0) credits_used,"
            " (SELECT COUNT(*) FROM tasks t WHERE t.user_id=u.id) runs,"
            " (SELECT COUNT(*) FROM conversations c WHERE c.user_id=u.id) chats,"
            " (SELECT COUNT(*) FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE c.user_id=u.id AND m.role='user') queries "
            f"FROM users u {where} ORDER BY {order} LIMIT ? OFFSET ?", (*params, limit, offset))
        for r in rows:
            r["spent_today"] = wallet.spent_today(db, r["id"])
            r["limits"] = {"daily": r["daily_limit"] if r["daily_limit"] is not None else plans.rules(r["plan"]).get("daily_credit_cap"),
                           "monthly": r["monthly_limit"]}
        return rows

    # ---- overview -----------------------------------------------------------------------------------------------------------------
    @app.get("/api/admin/overview")
    def overview(request: Request):
        admin = need_admin(request)
        day = now() - (now() % 86400)
        week = now() - 7 * 86400
        by_plan = db.all("SELECT plan, COUNT(*) users FROM users GROUP BY plan ORDER BY users DESC")
        return {
            "users": db.scalar("SELECT COUNT(*) FROM users"),
            "registered": db.scalar("SELECT COUNT(*) FROM users WHERE email IS NOT NULL"),
            "active_today": db.scalar("SELECT COUNT(DISTINCT user_id) FROM tasks WHERE created_at>=?", (day,)),
            "active_7d": db.scalar("SELECT COUNT(DISTINCT user_id) FROM tasks WHERE created_at>=?", (week,)),
            "queries_today": db.scalar("SELECT COUNT(*) FROM messages WHERE role='user' AND created_at>=?", (day,)),
            "runs_today": db.scalar("SELECT COUNT(*) FROM tasks WHERE created_at>=?", (day,)),
            "credits_used_today": int(db.scalar("SELECT -SUM(delta) FROM credit_ledger WHERE delta<0 AND reason NOT LIKE 'admin%' AND created_at>=?", (day,))),
            "credits_used_total": int(db.scalar("SELECT -SUM(delta) FROM credit_ledger WHERE delta<0 AND reason NOT LIKE 'admin%'")),
            "ai_cost_usd_total": round(float(db.scalar("SELECT SUM(cost_usd) FROM usage_events", (), 0.0)), 4),
            "ai_cost_usd_today": round(float(db.scalar("SELECT SUM(cost_usd) FROM usage_events WHERE created_at>=?", (day,), 0.0)), 4),
            "revenue_usd_total": round(float(db.scalar("SELECT SUM(amount_usd) FROM purchases WHERE status='paid'", (), 0.0)), 2),
            "revenue_usd_30d": round(float(db.scalar("SELECT SUM(amount_usd) FROM purchases WHERE status='paid' AND created_at>=?",
                                                     (now() - 30 * 86400,), 0.0)), 2),
            "pending_purchases": db.scalar("SELECT COUNT(*) FROM purchases WHERE status='pending'"),
            "blocked_users": db.scalar("SELECT COUNT(*) FROM users WHERE status='blocked'"),
            "by_plan": by_plan,
            "top_users": user_rows(sort="credits", limit=8),
            "daily": db.all("SELECT date(created_at,'unixepoch') day, COUNT(*) runs, SUM(credits_used) credits FROM tasks "
                            "WHERE created_at>=? GROUP BY day ORDER BY day", (now() - 14 * 86400,)),
            "ledger_mismatches": len(wallet.ledger_mismatches(db)),
            "you": admin.get("id"),
        }

    # ---- users ------------------------------------------------------------------------------------------------------------------------
    @app.get("/api/admin/users")
    def users(request: Request, q: str = "", sort: str = "recent", plan: str = "", status: str = "",
              page: int = Query(0, ge=0), size: int = Query(50, ge=1, le=200)):
        need_admin(request)
        where, params = [], []
        if q.strip():
            where.append("(u.name LIKE ? OR u.email LIKE ? OR u.id LIKE ?)")
            params += [f"%{q.strip()}%"] * 3
        if plan:
            where.append("u.plan=?")
            params.append(plan)
        if status:
            where.append("u.status=?")
            params.append(status)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        total = db.scalar(f"SELECT COUNT(*) FROM users u {clause}", tuple(params))
        return {"total": total, "page": page, "users": user_rows(clause, tuple(params), sort, size, page * size)}

    @app.get("/api/admin/users/{uid}")
    def user_detail(request: Request, uid: str):
        admin = need_admin(request)
        if not db.one("SELECT id FROM users WHERE id=?", (uid,)):
            raise HTTPException(404, "No such user")
        return activity.blueprint(db, uid)

    @app.put("/api/admin/users/{uid}")
    def user_patch(request: Request, uid: str, body: UserPatch):
        admin = need_admin(request)
        u = db.one("SELECT * FROM users WHERE id=?", (uid,))
        if not u:
            raise HTTPException(404, "No such user")
        actor, changes = admin["id"], {}
        if body.name is not None:
            changes["name"] = body.name.strip()[:40] or u["name"]
        if body.plan is not None and body.plan != u["plan"]:
            p = plans.get(body.plan)
            if not p or p["kind"] != "subscription":
                raise HTTPException(400, "Unknown plan.")
            changes["plan"] = body.plan
            changes["plan_renews_at"] = now() + p["period_days"] * 86400
        if body.extend_plan_days:
            changes["plan_renews_at"] = max(u.get("plan_renews_at") or now(), now()) + body.extend_plan_days * 86400
        if body.status is not None:
            if body.status not in ("active", "blocked"):
                raise HTTPException(400, "Status must be active or blocked.")
            if uid == actor and body.status == "blocked":
                raise HTTPException(400, "You cannot block yourself.")
            changes["status"] = body.status
        if body.role is not None:
            if body.role not in ("user", "admin"):
                raise HTTPException(400, "Role must be user or admin.")
            if body.role == "admin" and not u.get("email"):
                raise HTTPException(400, "Only a registered account (with email and password) can be an admin.")
            if body.role == "user" and u["role"] == "admin" and db.scalar("SELECT COUNT(*) FROM users WHERE role='admin' AND status='active'") <= 1:
                raise HTTPException(400, "You cannot remove the last admin.")
            changes["role"] = body.role
        for field, clear in (("daily_limit", body.clear_daily_limit), ("monthly_limit", body.clear_monthly_limit)):
            if clear:
                changes[field] = None
            elif getattr(body, field) is not None:
                changes[field] = getattr(body, field)
        if body.memory_enabled is not None:
            changes["memory_enabled"] = 1 if body.memory_enabled else 0
        if body.auto_spend is not None:
            changes["auto_spend"] = body.auto_spend
        if body.note is not None:
            changes["note"] = body.note
        if not changes:
            return activity.public_user(u)
        sets = ", ".join(f"{k}=?" for k in changes)
        db.run(f"UPDATE users SET {sets} WHERE id=?", (*changes.values(), uid))
        if changes.get("status") == "blocked":
            db.run("DELETE FROM sessions WHERE user_id=?", (uid,))
        activity.log(db, uid, "admin_changed_user", actor=actor, **{k: v for k, v in changes.items() if k != "plan_renews_at"})
        return activity.public_user(db.one("SELECT * FROM users WHERE id=?", (uid,)))

    @app.post("/api/admin/users/{uid}/credits")
    def adjust_credits(request: Request, uid: str, delta: int = Body(..., ge=-10_000_000, le=10_000_000),
                       reason: str = Body("", max_length=200)):
        admin = need_admin(request)
        if not db.one("SELECT id FROM users WHERE id=?", (uid,)):
            raise HTTPException(404, "No such user")
        if delta == 0:
            raise HTTPException(400, "Choose a number above or below zero.")
        if delta < 0 and wallet.available(db, uid) + delta < 0:
            raise HTTPException(400, f"The user only has {wallet.available(db, uid)} free credits.")
        wallet.add(db, uid, delta, "admin:" + (reason.strip() or ("grant" if delta > 0 else "removal"))[:80])
        activity.log(db, uid, "admin_credits", actor=admin["id"], delta=delta, reason=reason[:80])
        return {"balance": wallet.balance(db, uid), "available": wallet.available(db, uid)}

    @app.delete("/api/admin/users/{uid}")
    def user_delete(request: Request, uid: str, confirm: str = Body(..., embed=True)):
        admin = need_admin(request)
        u = db.one("SELECT * FROM users WHERE id=?", (uid,))
        if not u:
            raise HTTPException(404, "No such user")
        if confirm != u["id"]:
            raise HTTPException(400, "Type the user id to confirm.")
        if u["role"] == "admin":
            raise HTTPException(400, "Remove admin rights first.")
        wipe_user(db, uid)
        return {"ok": True}

    # ---- every user's queries and chats ---------------------------------------------------------------------------------------------
    @app.get("/api/admin/queries")
    def queries(request: Request, q: str = "", user_id: str = "", page: int = Query(0, ge=0), size: int = Query(50, ge=1, le=200)):
        need_admin(request)
        where, params = ["m.role='user'"], []
        if user_id:
            where.append("c.user_id=?")
            params.append(user_id)
        if q.strip():
            where.append("m.content LIKE ?")
            params.append(f"%{q.strip()}%")
        clause = " AND ".join(where)
        base = "FROM messages m JOIN conversations c ON c.id=m.conversation_id LEFT JOIN users u ON u.id=c.user_id " \
               "LEFT JOIN tasks t ON t.id=m.task_id WHERE " + clause
        return {"total": db.scalar("SELECT COUNT(*) " + base, tuple(params)),
                "queries": db.all("SELECT m.id, m.content, m.created_at, c.id conversation_id, c.title, u.id user_id, u.name, u.email, "
                                  "t.mode, t.status, t.credits_used " + base + " ORDER BY m.id DESC LIMIT ? OFFSET ?",
                                  (*params, size, page * size))}

    @app.get("/api/admin/conversations/{cid}")
    def conversation(request: Request, cid: str):
        admin = need_admin(request)
        c = db.one("SELECT * FROM conversations WHERE id=?", (cid,))
        if not c:
            raise HTTPException(404, "No such chat")
        activity.log(db, c["user_id"], "admin_viewed_chat", actor=admin["id"], conversation_id=cid)  # transparency for the user
        msgs = db.all("SELECT m.id,m.role,m.content,m.created_at,m.rating,t.mode,t.credits_used,t.status,t.id task_id FROM messages m "
                      "LEFT JOIN tasks t ON t.id=m.task_id WHERE m.conversation_id=? ORDER BY m.id", (cid,))
        return {"id": cid, "title": c["title"], "user_id": c["user_id"], "summary": c["summary"], "notes": c.get("notes"), "messages": msgs}

    @app.get("/api/admin/activity")
    def all_activity(request: Request, user_id: str = "", before: int | None = None, limit: int = Query(100, ge=1, le=500)):
        need_admin(request)
        if user_id:
            return {"events": activity.timeline(db, user_id, limit, before)}
        rows = db.all("SELECT a.id,a.user_id,a.kind,a.detail,a.actor,a.created_at,u.name,u.email FROM activity a LEFT JOIN users u ON u.id=a.user_id "
                      "WHERE (? IS NULL OR a.id<?) ORDER BY a.id DESC LIMIT ?", (before, before, limit))
        return {"events": [{**r, "detail": jload(r["detail"], {})} for r in rows]}

    # ---- plans: admin controls price, credits, benefits and rules ----------------------------------------------------------------------------
    @app.get("/api/admin/plans")
    def admin_plans(request: Request):
        need_admin(request)
        counts = {r["plan"]: r["n"] for r in db.all("SELECT plan, COUNT(*) n FROM users GROUP BY plan")}
        return {"plans": [{**p, "users": counts.get(p["id"], 0)} for p in plans.all_plans(True)],
                "modes": [{"id": m["id"], "name": m["name"]} for m in __import__("app.modes", fromlist=["listing"]).listing(db)],
                "rule_help": {"tiers": "Brain tiers the plan may use: quick, smart, genius", "max_effort": "off, low, medium, high or max",
                              "daily_credit_cap": "Most credits a user may spend per day", "storage_mb": "File storage", "retention_days": "Days files are kept",
                              "max_rounds": "Think Again rounds", "max_tries": "Overthink tries", "charts_per_day": "Charts a day",
                              "modes": "Mode ids this plan unlocks", "images": "Image generation", "mcp": "MCP tool servers",
                              "private_default": "Private route on by default"}}

    def save_plan(pid: str, body: PlanBody, creating: bool) -> dict:
        if body.kind not in ("subscription", "topup"):
            raise HTTPException(400, "Kind must be subscription or topup.")
        if not creating and not plans.get(pid):
            raise HTTPException(404, "No such plan")
        rules = plans.clean_rules(body.rules) if body.kind == "subscription" else {}
        values = (body.name.strip(), body.kind, body.price_usd, body.credits, body.period_days,
                  jdump([b.strip()[:120] for b in body.benefits if b.strip()]), jdump(rules), 1 if body.active else 0, body.sort, now())
        if creating:
            db.run("INSERT INTO plans(id,name,kind,price_usd,credits,period_days,benefits,rules,active,sort,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (pid, *values))
        else:
            db.run("UPDATE plans SET name=?,kind=?,price_usd=?,credits=?,period_days=?,benefits=?,rules=?,active=?,sort=?,updated_at=? WHERE id=?",
                   (*values, pid))
        plans.invalidate()
        return plans.get(pid)

    @app.post("/api/admin/plans")
    def plan_create(request: Request, body: PlanBody):
        admin = need_admin(request)
        if not body.id or plans.get(body.id):
            raise HTTPException(400, "Choose a new id (lowercase letters, numbers, underscore).")
        row = save_plan(body.id, body, True)
        activity.log(db, admin["id"], "admin_plan_created", actor=admin["id"], plan=body.id)
        return row

    @app.put("/api/admin/plans/{pid}")
    def plan_update(request: Request, pid: str, body: PlanBody):
        admin = need_admin(request)
        row = save_plan(pid, body, False)
        activity.log(db, admin["id"], "admin_plan_updated", actor=admin["id"], plan=pid, price=body.price_usd, credits=body.credits)
        return row

    @app.delete("/api/admin/plans/{pid}")
    def plan_hide(request: Request, pid: str):
        admin = need_admin(request)
        if pid == "free":
            raise HTTPException(400, "The free plan cannot be hidden.")
        if not plans.get(pid):
            raise HTTPException(404, "No such plan")
        db.run("UPDATE plans SET active=0, updated_at=? WHERE id=?", (now(), pid))
        plans.invalidate()
        return {"ok": True, "note": "Hidden from the store. Users already on it keep it."}

    # ---- purchases -----------------------------------------------------------------------------------------------------------------------------
    @app.get("/api/admin/purchases")
    def admin_purchases(request: Request, status: str = ""):
        need_admin(request)
        rows = db.all("SELECT p.*, u.name, u.email FROM purchases p LEFT JOIN users u ON u.id=p.user_id "
                      "WHERE (?='' OR p.status=?) ORDER BY p.created_at DESC LIMIT 200", (status, status))
        return {"purchases": rows}

    @app.post("/api/admin/purchases/{pid}/paid")
    def purchase_paid(request: Request, pid: str):
        admin = need_admin(request)
        try:
            return billing.complete_purchase(db, pid, actor=admin["id"])
        except billing.BillingError as e:
            raise HTTPException(404, str(e))

    @app.post("/api/admin/purchases/{pid}/cancel")
    def purchase_cancel(request: Request, pid: str):
        admin = need_admin(request)
        try:
            return billing.cancel_purchase(db, pid, admin["id"])
        except billing.BillingError as e:
            raise HTTPException(404, str(e))
