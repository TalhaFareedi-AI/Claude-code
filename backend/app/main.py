"""FastAPI app. Web and phone app both read the same lists (modes, models) from here."""
import asyncio
import json
import os
import re
import shutil
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, Cookie, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import catalog, modes as modes_mod, skills, wallet, workspace
from .config import ROOT, settings
from .db import DB, jdump, jload, now
from .harness import Harness, RunContext, RunRequest, UserError
from .openrouter import OpenRouter, OpenRouterError
from .plans import PLAN_RULES, rules as plan_rules
from .pricing import EFFORT_ORDER, PLAN_MAX_EFFORT

FRONTEND = ROOT / "frontend"
TOOLS = [
    {"id": "chart", "label": "Charts", "default": True},
    {"id": "diagram", "label": "Diagrams", "default": True},
    {"id": "documents", "label": "Word documents", "default": True},
    {"id": "ppt", "label": "PowerPoint", "default": True},
    {"id": "web", "label": "Web search", "default": True},
]
EFFORTS = [{"id": "auto", "label": "Auto"}, {"id": "off", "label": "Off"}, {"id": "low", "label": "Low"},
           {"id": "medium", "label": "Medium"}, {"id": "high", "label": "High"}, {"id": "max", "label": "Max"}]
ROLE_LABELS = {"answer": "Answerer", "write": "Writer", "critic": "Critic", "think": "Thinker", "judge": "Judge",
               "members": "Members", "planner": "Planner", "worker": "Worker", "checker": "Checker",
               "search": "Searcher", "writer": "Writer"}


class ChatBody(BaseModel):
    message: str = Field("", max_length=12000)
    conversation_id: str | None = None
    mode: str = "auto"
    brains: dict = Field(default_factory=dict)
    effort: str = "auto"
    rounds: int | None = None
    tries: int | None = None
    max_credits: int | None = Field(None, ge=1, le=2000)
    tools: list[str] | None = None
    skills: list[str] | None = None
    intent: str | None = None
    confirm: bool = False
    continue_task: str | None = None
    extra_credits: int = Field(0, ge=0, le=2000)
    private_route: bool | None = None
    target_message: int | None = None
    uploads: list[str] = Field(default_factory=list)


class NullEmitter:
    def emit(self, *a, **k):
        return {}


def price_level(m: dict) -> str:
    o = m["price_out"] or 0
    return "$" if o < 1 else "$$" if o < 6 else "$$$" if o < 15 else "$$$$"


def create_app(llm: OpenRouter | None = None, db: DB | None = None) -> FastAPI:
    db = db or DB(settings.db_path)
    catalog.seed(db)
    modes_mod.seed(db)
    llm = llm or OpenRouter()
    harness = Harness(db, llm)
    hits: dict[str, deque] = defaultdict(deque)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async def nightly():
            while True:
                try:
                    if llm.api_key:
                        rep = catalog.sync_live(db, await llm.list_models())
                        app.state.last_sync = {"at": now(), **rep}
                    workspace.purge_expired(db)
                except Exception as e:  # offline or blocked: keep the seeded table
                    app.state.last_sync = {"at": now(), "error": str(e)[:200]}
                await asyncio.sleep(24 * 3600)
        t = asyncio.create_task(nightly())
        yield
        t.cancel()
        await llm.aclose()

    app = FastAPI(title=settings.app_title, lifespan=lifespan)
    app.state.harness, app.state.db, app.state.last_sync = harness, db, {}

    @app.middleware("http")
    async def headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                                   "script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        return resp

    # ---- who is this -------------------------------------------------------------------
    def who(request: Request, response: Response | None = None) -> dict:
        uid = request.cookies.get("uid")
        if settings.dev_mode and request.headers.get("x-user-id"):
            uid = request.headers["x-user-id"]
        if not uid or not re.fullmatch(r"u_[A-Za-z0-9_-]{4,40}", uid):
            uid = "u_" + uuid.uuid4().hex[:12]
            request.state.new_uid = uid
        return harness.get_user(uid)

    @app.middleware("http")
    async def set_cookie(request: Request, call_next):
        resp = await call_next(request)
        uid = getattr(request.state, "new_uid", None)
        if uid:
            resp.set_cookie("uid", uid, max_age=365 * 86400, httponly=True, samesite="lax")
        return resp

    def plan_modes(user: dict) -> list[dict]:
        out = []
        for m in modes_mod.listing(db):
            ok = modes_mod.allowed(m, user["plan"])
            order = ["free", "student", "pro", "school"]
            need = next((p for p in order if p in m["plans"]), "pro")
            out.append({**m, "allowed": ok, "locked": None if ok else f"Needs the {need.title()} plan"})
        return out

    # ---- bootstrap: everything the pickers need ----------------------------------------------
    @app.get("/api/bootstrap")
    def bootstrap(request: Request):
        user = who(request)
        rl = plan_rules(user["plan"])
        models = []
        for m in catalog.listing(db):
            models.append({"id": m["id"], "name": m["name"], "lab": m["lab"], "region": m["region"], "tier": m["tier"],
                           "thinks": bool(m["thinks"]), "level": price_level(m), "price_in": m["price_in"],
                           "price_out": m["price_out"], "private": bool(m["private_route"]),
                           "allowed": m["tier"] in rl["tiers"]})
        top = PLAN_MAX_EFFORT[user["plan"]]
        efforts = [{**e, "allowed": e["id"] == "auto" or EFFORT_ORDER.index(e["id"]) <= EFFORT_ORDER.index(top)} for e in EFFORTS]
        return {
            "app": settings.app_title,
            "user": {"id": user["id"], "name": user["name"], "plan": user["plan"], "auto_spend": user["auto_spend"],
                     "private_route": bool(user["private_route"])},
            "wallet": {"balance": wallet.balance(db, user["id"]), "held": wallet.held(db, user["id"]),
                       "available": wallet.available(db, user["id"])},
            "plans": {k: {**v, **{"rules": PLAN_RULES[k]}} for k, v in wallet.PLANS.items()},
            "modes": plan_modes(user),
            "models": models,
            "efforts": efforts,
            "tools": TOOLS,
            "skills": [{"name": s.name, "description": s.description} for s in skills.all_skills().values()],
            "roles": ROLE_LABELS,
            "dev_mode": settings.dev_mode,
            "has_key": bool(llm.api_key),
            "catalog_sync": app.state.last_sync,
        }

    # ---- estimate (live, before every run) --------------------------------------------------------
    @app.post("/api/estimate")
    def estimate_ep(request: Request, body: ChatBody):
        user = who(request)
        req = to_request(body)
        task = {"id": "estimate", "max_credits": 0}
        route = harness.route_rules(req)
        try:
            mode = harness.choose_mode(req, route, user["plan"])
            ctx = RunContext(harness, user, task, req, mode, NullEmitter())
            est = harness.make_estimate(ctx, route)
        except (UserError, LookupError) as e:
            raise HTTPException(400, str(e))
        cap = req.max_credits or min(mode["max_credits"], max(user["auto_spend"], est["credits"]))
        brains = {r: [m["name"] for m in ctx.brains(r)] for r in mode["slots"]}
        return {"mode": mode["id"], "mode_name": mode["name"], "credits": est["credits"], "usd": est["usd"],
                "cap": max(1, min(cap, mode["max_credits"])), "max_cap": mode["max_credits"], "big": mode["big"],
                "needs_confirm": mode["big"] and est["credits"] > user["auto_spend"], "brains": brains,
                "rounds": est.get("rounds"), "tries": est.get("tries"), "parts": est["parts"]}

    def to_request(b: ChatBody) -> RunRequest:
        return RunRequest(message=b.message, mode=b.mode, brains=b.brains, effort=b.effort, rounds=b.rounds, tries=b.tries,
                          max_credits=b.max_credits, tools=b.tools if b.tools is not None else [t["id"] for t in TOOLS if t["default"]],
                          skills=b.skills, intent=b.intent, conversation_id=b.conversation_id, confirm=b.confirm,
                          continue_task=b.continue_task, extra_credits=b.extra_credits, private_route=b.private_route,
                          target_message=b.target_message, uploads=b.uploads)

    # ---- chat: a stream of small events -----------------------------------------------------------------
    @app.post("/api/chat")
    async def chat(request: Request, body: ChatBody):
        user = who(request)
        if not body.message.strip() and not body.continue_task:
            raise HTTPException(400, "Write a message first.")
        q = hits[user["id"]]
        while q and q[0] < time.time() - 60:
            q.popleft()
        if len(q) >= settings.rate_per_minute:
            raise HTTPException(429, "Too many messages. Wait a moment.")
        q.append(time.time())
        req = to_request(body)
        if body.continue_task and not body.message.strip():
            req.message = "Continue the task."
        task_id, em = await harness.start(user["id"], req)

        async def gen():
            yield sse({"seq": 0, "type": "hello", "task_id": task_id, "conversation_id": req.conversation_id})
            while True:
                try:
                    ev = await asyncio.wait_for(em.queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if ev is None:
                    return
                yield sse(ev)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def sse(ev: dict) -> str:
        return f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    @app.post("/api/runs/{task_id}/stop")
    def stop(request: Request, task_id: str):
        user = who(request)
        t = db.one("SELECT user_id FROM tasks WHERE id=?", (task_id,))
        if not t or t["user_id"] != user["id"]:
            raise HTTPException(404, "No such run")
        return {"stopped": harness.stop(task_id)}

    @app.get("/api/runs/{task_id}/events")
    def run_events(request: Request, task_id: str, after: int = 0):
        user = who(request)
        t = db.one("SELECT * FROM tasks WHERE id=? AND user_id=?", (task_id, user["id"]))
        if not t:
            raise HTTPException(404, "No such run")
        rows = db.all("SELECT seq,type,data FROM run_events WHERE task_id=? AND seq>? ORDER BY seq", (task_id, after))
        return {"status": t["status"], "events": [{"seq": r["seq"], "type": r["type"], **jload(r["data"], {})} for r in rows]}

    # ---- conversations ----------------------------------------------------------------------------------------------
    @app.get("/api/conversations")
    def conversations(request: Request):
        user = who(request)
        return db.all("SELECT id,title,updated_at FROM conversations WHERE user_id=? ORDER BY updated_at DESC LIMIT 100", (user["id"],))

    @app.get("/api/conversations/{cid}")
    def conversation(request: Request, cid: str):
        user = who(request)
        c = db.one("SELECT * FROM conversations WHERE id=? AND user_id=?", (cid, user["id"]))
        if not c:
            raise HTTPException(404, "No such chat")
        msgs = []
        for m in db.all("SELECT id,role,content,meta,task_id,rating FROM messages WHERE conversation_id=? ORDER BY id", (cid,)):
            meta = jload(m["meta"], {})
            arts = []
            for aid in meta.get("artifacts", []):
                a = db.one("SELECT id,kind,data FROM artifacts WHERE id=? AND user_id=?", (aid, user["id"]))
                if a:
                    arts.append({"id": a["id"], "kind": a["kind"], "data": jload(a["data"])})
            files = []
            for fid in meta.get("files", []):
                if db.one("SELECT id FROM workspace_files WHERE id=? AND user_id=?", (fid, user["id"])):
                    files.append(workspace.file_row(db, fid))
            msgs.append({"id": m["id"], "role": m["role"], "content": m["content"], "task_id": m["task_id"],
                         "rating": m["rating"], "buttons": meta.get("buttons", []), "artifacts": arts, "files": files,
                         "notices": meta.get("notices", []), "mode": meta.get("mode"), "credits": meta.get("credits")})
        return {"id": cid, "title": c["title"], "messages": msgs}

    @app.delete("/api/conversations/{cid}")
    def delete_conversation(request: Request, cid: str):
        user = who(request)
        db.run("DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE id=? AND user_id=?)", (cid, user["id"]))
        db.run("DELETE FROM conversations WHERE id=? AND user_id=?", (cid, user["id"]))
        return {"ok": True}

    @app.post("/api/messages/{mid}/rating")
    def rate(request: Request, mid: int, rating: int = Body(..., embed=True)):
        user = who(request)
        if rating not in (-1, 0, 1):
            raise HTTPException(400, "rating must be -1, 0 or 1")
        db.run("UPDATE messages SET rating=? WHERE id=? AND conversation_id IN (SELECT id FROM conversations WHERE user_id=?)",
               (rating or None, mid, user["id"]))
        return {"ok": True}

    # ---- files ---------------------------------------------------------------------------------------------------------------
    def own_file(user: dict, fid: str) -> dict:
        r = db.one("SELECT * FROM workspace_files WHERE id=? AND user_id=?", (fid, user["id"]))
        if not r:
            raise HTTPException(404, "No such file")
        return r

    @app.get("/api/files")
    def files(request: Request, task_id: str | None = None, conversation_id: str | None = None):
        user = who(request)
        if task_id:
            rows = db.all("SELECT id FROM workspace_files WHERE user_id=? AND task_id=? AND path LIKE 'out/%' ORDER BY created_at", (user["id"], task_id))
        elif conversation_id:
            rows = db.all("SELECT f.id FROM workspace_files f JOIN tasks t ON t.id=f.task_id WHERE f.user_id=? AND t.conversation_id=? "
                          "AND f.path LIKE 'out/%' ORDER BY f.created_at", (user["id"], conversation_id))
        else:
            rows = db.all("SELECT id FROM workspace_files WHERE user_id=? AND path LIKE 'out/%' ORDER BY created_at DESC LIMIT 100", (user["id"],))
        return {"files": [workspace.file_row(db, r["id"]) for r in rows],
                "used_bytes": workspace.usage_bytes(db, user["id"]),
                "limit_bytes": plan_rules(user["plan"])["storage_mb"] * 1024 * 1024,
                "workspace_name": f"{user['name']}'s workspace"}

    @app.get("/api/files/{fid}/link")
    def file_link(request: Request, fid: str):
        user = who(request)
        own_file(user, fid)
        return {"url": f"/download?token={workspace.sign(fid, user['id'])}", "expires_in": settings.link_ttl_s}

    @app.get("/download")
    def download(request: Request, token: str):
        user = who(request)
        fid = workspace.verify(token, user["id"])
        if not fid:
            raise HTTPException(403, "This link expired. Ask for a new one.")
        r = own_file(user, fid)
        try:
            p = workspace.path_of(r)
        except workspace.PathEscape:
            raise HTTPException(404, "No such file")
        if not p.exists():
            raise HTTPException(404, "The file is gone (files are kept for a limited time).")
        return FileResponse(p, filename=r["name"], headers={"Content-Disposition": f'attachment; filename="{r["name"]}"',
                                                            "X-Content-Type-Options": "nosniff"})

    @app.get("/api/files/{fid}/preview")
    def preview(request: Request, fid: str):
        user = who(request)
        r = own_file(user, fid)
        if r["kind"] in ("pptx", "docx"):
            a = db.one("SELECT data FROM artifacts WHERE user_id=? AND task_id=? AND kind IN ('deck_json','doc_json') ORDER BY created_at DESC",
                       (user["id"], r["task_id"]))
            deck = jload(a["data"], {}) if a else {}
            items = deck.get("slides") or deck.get("sections") or []
            return {"kind": r["kind"], "title": deck.get("title"),
                    "items": [{"title": x.get("title") or x.get("heading"), "lines": (x.get("bullets") or x.get("paragraphs") or [])[:6]} for x in items]}
        if r["kind"] == "svg":
            return {"kind": "svg", "svg": workspace.path_of(r).read_text()}
        return {"kind": r["kind"], "note": "Download to open this file."}

    @app.put("/api/upload")
    async def upload(request: Request, name: str = Query(..., max_length=120)):
        user = who(request)
        data = await request.body()
        if len(data) > settings.upload_max_bytes:
            raise HTTPException(413, f"File too large (limit {settings.upload_max_bytes // 1024} KB).")
        clean = workspace.clean_name(name)
        ext = Path(clean).suffix.lower()
        if ext not in workspace.ALLOWED_UPLOAD:
            raise HTTPException(400, "That file type is not allowed.")
        if not _magic_ok(ext, data):
            raise HTTPException(400, "The file does not look like a real " + ext + " file.")
        try:
            workspace.check_storage(db, user["id"], user["plan"], len(data))
        except workspace.PathEscape as e:
            raise HTTPException(413, str(e))
        d = workspace.task_dir(user["id"], "uploads", "uploads")
        p = d / "inputs" / f"{uuid.uuid4().hex[:6]}_{clean}"
        p.write_bytes(data)
        rec = workspace.register(db, user["id"], "uploads", p, ext.lstrip("."), user["plan"])
        return {"id": rec["id"], "name": clean, "size": rec["size"]}

    @app.delete("/api/workspace")
    def delete_workspace(request: Request):
        user = who(request)
        workspace.delete_all(db, user["id"])
        return {"ok": True}

    # ---- wallet and profile ----------------------------------------------------------------------------------------------------------
    @app.get("/api/wallet")
    def wallet_ep(request: Request):
        user = who(request)
        return {"balance": wallet.balance(db, user["id"]), "held": wallet.held(db, user["id"]),
                "available": wallet.available(db, user["id"]),
                "ledger": db.all("SELECT delta,reason,task_id,created_at FROM credit_ledger WHERE user_id=? ORDER BY id DESC LIMIT 50", (user["id"],))}

    @app.get("/api/runs/{task_id}/usage")
    def usage(request: Request, task_id: str):
        user = who(request)
        return db.all("SELECT step_no,role,model,input_tokens,cached_tokens,output_tokens,reasoning_tokens,cost_usd,credits_charged,finish_reason "
                      "FROM usage_events WHERE user_id=? AND task_id=? ORDER BY step_no", (user["id"], task_id))

    @app.get("/api/profile")
    def get_profile(request: Request):
        return harness.profile(who(request)["id"])

    @app.put("/api/profile")
    def put_profile(request: Request, data: dict = Body(...)):
        user = who(request)
        keys = ("level", "interests", "language", "likes", "weak_topics", "goal")
        clean = {k: data[k] for k in keys if k in data}
        if len(jdump(clean)) > 1500:
            raise HTTPException(400, "Profile too long")
        db.run("INSERT OR REPLACE INTO profiles(user_id,data,updated_at) VALUES(?,?,?)", (user["id"], jdump(clean), now()))
        return clean

    @app.delete("/api/profile")
    def del_profile(request: Request):
        db.run("DELETE FROM profiles WHERE user_id=?", (who(request)["id"],))
        return {"ok": True}

    @app.put("/api/settings")
    def put_settings(request: Request, data: dict = Body(...)):
        user = who(request)
        if "auto_spend" in data:
            db.run("UPDATE users SET auto_spend=? WHERE id=?", (max(1, min(int(data["auto_spend"]), 500)), user["id"]))
        if "private_route" in data:
            db.run("UPDATE users SET private_route=? WHERE id=?", (1 if data["private_route"] else 0, user["id"]))
        if "name" in data:
            db.run("UPDATE users SET name=? WHERE id=?", (str(data["name"])[:40] or "Student", user["id"]))
        return {"ok": True}

    # ---- dev + admin ---------------------------------------------------------------------------------------------------------------------------
    def need_admin(request: Request) -> None:
        if settings.dev_mode:
            return
        if not settings.admin_token or request.headers.get("x-admin-token") != settings.admin_token:
            raise HTTPException(403, "admin only")

    @app.post("/api/dev/plan")
    def dev_plan(request: Request, plan: str = Body(..., embed=True)):
        if not settings.dev_mode:
            raise HTTPException(403, "dev mode only")
        user = who(request)
        if plan not in wallet.PLANS:
            raise HTTPException(400, "unknown plan")
        db.run("UPDATE users SET plan=? WHERE id=?", (plan, user["id"]))
        return {"plan": plan}

    @app.post("/api/dev/topup")
    def dev_topup(request: Request, credits: int = Body(..., embed=True)):
        if not settings.dev_mode:
            raise HTTPException(403, "dev mode only")
        user = who(request)
        wallet.add(db, user["id"], max(1, min(credits, 5000)), "dev-topup")
        return {"balance": wallet.balance(db, user["id"])}

    @app.post("/api/admin/catalog/sync")
    async def sync(request: Request):
        need_admin(request)
        try:
            rep = catalog.sync_live(db, await llm.list_models())
        except OpenRouterError as e:
            raise HTTPException(502, f"OpenRouter said: {e}")
        except Exception as e:
            raise HTTPException(502, f"Could not reach OpenRouter: {e}")
        app.state.last_sync = {"at": now(), **rep}
        return rep

    @app.get("/api/admin/catalog")
    def admin_catalog(request: Request):
        need_admin(request)
        return db.all("SELECT * FROM model_catalog ORDER BY approved DESC, tier, price_out")

    @app.post("/api/admin/catalog/approve")
    def admin_approve(request: Request, model_id: str = Body(...), tier: str | None = Body(None), on: bool = Body(True)):
        need_admin(request)
        catalog.approve(db, model_id, tier, on)
        return {"ok": True}

    @app.get("/api/admin/health")
    def health(request: Request):
        need_admin(request)
        return {"ledger_mismatches": wallet.ledger_mismatches(db), "last_sync": app.state.last_sync}

    if FRONTEND.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="ui")
    return app


def _magic_ok(ext: str, data: bytes) -> bool:
    if ext == ".pdf":
        return data[:5] == b"%PDF-"
    if ext == ".png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    if ext in (".jpg", ".jpeg"):
        return data[:3] == b"\xff\xd8\xff"
    if ext in (".docx", ".pptx"):
        return data[:4] == b"PK\x03\x04"
    try:  # text types must be real text
        data.decode("utf-8")
        return b"\x00" not in data
    except UnicodeDecodeError:
        return False


app = create_app() if not os.environ.get("NO_AUTO_APP") else None
