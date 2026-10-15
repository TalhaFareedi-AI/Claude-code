"""User-facing routes: sign up, log in, plans and purchases, memory manager, my blueprint, export, delete account."""
import json
import time
from collections import defaultdict, deque

from fastapi import Body, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import accounts, activity, billing, memory, plans, wallet, workspace
from .config import settings
from .db import jdump, jload, now

attempts: dict[str, deque] = defaultdict(deque)


def throttle(key: str, limit: int = 8, window: int = 600, count: bool = True) -> None:
    q = attempts[key]
    while q and q[0] < time.time() - window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many attempts. Wait a few minutes and try again.")
    if count:
        q.append(time.time())


def clear_throttle(*keys: str) -> None:
    for k in keys:
        attempts.pop(k, None)


class Credentials(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=200)
    name: str = Field("", max_length=40)


class MemoryBody(BaseModel):
    content: str = Field(..., min_length=2, max_length=300)
    kind: str = "fact"
    importance: int = Field(3, ge=1, le=5)
    pinned: bool = False


class MemoryPatch(BaseModel):
    content: str | None = Field(None, min_length=2, max_length=300)
    kind: str | None = None
    importance: int | None = Field(None, ge=1, le=5)
    pinned: bool | None = None


def set_session_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie("sid", token, max_age=accounts.SESSION_DAYS * 86400, httponly=True,
                        secure=request.url.scheme == "https", samesite="lax")


def install(app, db, harness, who) -> None:
    ip = lambda r: (r.client.host if r.client else "?")

    # ---- accounts ----------------------------------------------------------------------------------------------------
    @app.post("/api/auth/register")
    def register(request: Request, body: Credentials):
        throttle("reg:" + ip(request))
        user = who(request)
        try:
            u = accounts.register(db, user["id"], body.email, body.password, body.name)
        except accounts.AuthError as e:
            raise HTTPException(400, str(e))
        activity.log(db, u["id"], "registered", email=u["email"])
        resp = JSONResponse({"ok": True, "user": activity.public_user(u)})
        set_session_cookie(request, resp, accounts.create_session(db, u["id"], ip(request), request.headers.get("user-agent", "")))
        return resp

    @app.post("/api/auth/login")
    def login(request: Request, body: Credentials):
        k_ip, k_mail = "login:" + ip(request), "loginmail:" + body.email.strip().lower()
        throttle(k_ip, count=False)       # only failed attempts are counted
        throttle(k_mail, 10, count=False)
        try:
            u = accounts.authenticate(db, body.email, body.password)
        except accounts.AuthError as e:
            throttle(k_ip)
            throttle(k_mail, 10)
            raise HTTPException(401, str(e))
        clear_throttle(k_ip, k_mail)
        activity.log(db, u["id"], "login", ip=ip(request))
        resp = JSONResponse({"ok": True, "user": activity.public_user(u)})
        set_session_cookie(request, resp, accounts.create_session(db, u["id"], ip(request), request.headers.get("user-agent", "")))
        return resp

    @app.post("/api/auth/logout")
    def logout(request: Request):
        accounts.end_session(db, request.cookies.get("sid"))
        resp = JSONResponse({"ok": True})
        resp.delete_cookie("sid")
        return resp

    @app.post("/api/auth/password")
    def change_password(request: Request, old_password: str = Body(...), new_password: str = Body(...)):
        user = who(request)
        if not user.get("email") or not accounts.check_password(old_password, user.get("pw_hash")):
            raise HTTPException(400, "Your current password is wrong.")
        try:
            accounts.check_strength(new_password)
        except accounts.AuthError as e:
            raise HTTPException(400, str(e))
        db.run("UPDATE users SET pw_hash=? WHERE id=?", (accounts.hash_password(new_password), user["id"]))
        accounts.end_all_sessions(db, user["id"])
        activity.log(db, user["id"], "password_changed")
        resp = JSONResponse({"ok": True})
        set_session_cookie(request, resp, accounts.create_session(db, user["id"], ip(request), request.headers.get("user-agent", "")))
        return resp

    # ---- plans and purchases --------------------------------------------------------------------------------------------
    @app.get("/api/plans")
    def list_plans(request: Request):
        user = who(request)
        return {"plans": billing.catalog_for_user(db, user), "current": user["plan"], "provider": settings.payment_provider,
                "renews_at": user.get("plan_renews_at"), "registered": bool(user.get("email")),
                "purchases": db.all("SELECT id,plan_id,kind,amount_usd,credits,status,created_at FROM purchases WHERE user_id=? "
                                    "ORDER BY created_at DESC LIMIT 30", (user["id"],))}

    @app.post("/api/purchase")
    def purchase(request: Request, plan_id: str = Body(..., embed=True)):
        user = who(request)
        try:
            p = billing.start_purchase(db, user, plan_id)
        except billing.BillingError as e:
            raise HTTPException(400, str(e))
        msg = "Done. Your credits are added." if p["status"] == "paid" else \
            "Order received. Credits arrive as soon as the payment is confirmed by the admin."
        return {"purchase": p, "message": msg, "wallet": {"balance": wallet.balance(db, user["id"])}}

    # ---- memory manager ----------------------------------------------------------------------------------------------------
    @app.get("/api/memory")
    def memory_list(request: Request, q: str = ""):
        user = who(request)
        items = memory.search(db, user["id"], q, 30) if q.strip() else memory.listing(db, user["id"])
        return {"enabled": bool(user.get("memory_enabled", 1)), "items": items, "kinds": list(memory.KINDS),
                "profile": jload((db.one("SELECT data FROM profiles WHERE user_id=?", (user["id"],)) or {}).get("data"), {})}

    @app.post("/api/memory")
    def memory_add(request: Request, body: MemoryBody):
        user = who(request)
        row = memory.add(db, user["id"], body.content, body.kind, body.importance, "user", None, body.pinned)
        if not row:
            raise HTTPException(400, "That looks like a secret (password, key or card number), so it was not saved.")
        activity.log(db, user["id"], "memory_added", id=row["id"])
        return row

    @app.put("/api/memory/enabled")
    def memory_enabled(request: Request, enabled: bool = Body(..., embed=True)):
        user = who(request)
        db.run("UPDATE users SET memory_enabled=? WHERE id=?", (1 if enabled else 0, user["id"]))
        activity.log(db, user["id"], "memory_toggled", enabled=enabled)
        return {"enabled": enabled}

    @app.put("/api/memory/{mid}")
    def memory_edit(request: Request, mid: int, body: MemoryPatch):
        user = who(request)
        row = memory.update(db, user["id"], mid, **body.model_dump(exclude_none=True))
        if not row:
            raise HTTPException(404, "No such memory, or the text looks like a secret.")
        return row

    @app.delete("/api/memory/{mid}")
    def memory_delete(request: Request, mid: int):
        user = who(request)
        if not memory.delete(db, user["id"], mid):
            raise HTTPException(404, "No such memory")
        activity.log(db, user["id"], "memory_deleted", id=mid)
        return {"ok": True}

    @app.delete("/api/memory")
    def memory_clear(request: Request):
        user = who(request)
        n = memory.delete_all(db, user["id"])
        activity.log(db, user["id"], "memory_cleared", count=n)
        return {"deleted": n}

    # ---- my blueprint, export, delete ------------------------------------------------------------------------------------------
    @app.get("/api/me/blueprint")
    def my_blueprint(request: Request):
        return activity.blueprint(db, who(request)["id"])

    @app.get("/api/me/export")
    def export(request: Request):
        user = who(request)
        data = {"exported_at": now(), "user": activity.public_user(user), "profile": harness.profile(user["id"]),
                "memories": memory.listing(db, user["id"]),
                "conversations": [{**c, "messages": [{**m, "meta": jload(m["meta"], {})} for m in db.all(
                    "SELECT id,role,content,meta,created_at,rating FROM messages WHERE conversation_id=? ORDER BY id", (c["id"],))]}
                    for c in db.all("SELECT id,title,summary,notes,created_at,updated_at FROM conversations WHERE user_id=?", (user["id"],))],
                "ledger": db.all("SELECT delta,reason,task_id,created_at FROM credit_ledger WHERE user_id=?", (user["id"],)),
                "purchases": db.all("SELECT * FROM purchases WHERE user_id=?", (user["id"],)),
                "activity": activity.timeline(db, user["id"], 500)}
        return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="my-data.json"'})

    @app.delete("/api/me")
    def delete_account(request: Request, confirm: str = Body(..., embed=True)):
        user = who(request)
        if confirm != "DELETE":
            raise HTTPException(400, 'Type DELETE to confirm.')
        if user.get("role") == "admin":
            raise HTTPException(400, "Admins cannot delete themselves here.")
        wipe_user(db, user["id"])
        resp = JSONResponse({"ok": True})
        resp.delete_cookie("sid")
        resp.delete_cookie("uid")
        return resp


def wipe_user(db, user_id: str) -> None:
    """Remove a user and everything they own (privacy: a real delete)."""
    workspace.delete_all(db, user_id)
    db.run("DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE user_id=?)", (user_id,))
    for table in ("conversations", "profiles", "memories", "sessions", "run_requests", "artifacts", "usage_events", "credit_holds",
                  "credit_ledger", "purchases", "activity"):
        db.run(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
    db.run("DELETE FROM run_events WHERE task_id IN (SELECT id FROM tasks WHERE user_id=?)", (user_id,))
    db.run("DELETE FROM tasks WHERE user_id=?", (user_id,))
    db.run("DELETE FROM users WHERE id=?", (user_id,))
