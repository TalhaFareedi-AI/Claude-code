"""Accounts, admin, plans and purchases, limits, memory and the user blueprint."""
import json
import sqlite3

import httpx
import pytest

from app import accounts, activity, billing, memory, plans, wallet, workspace
from app.config import settings
from app.db import DB, now
from app.harness import RunRequest
from app.main import create_app


# ---------------------------------------------------------------- helpers
async def run(harness, user, **kw):
    tid, em = await harness.start(user, RunRequest(**kw))
    events = [e async for e in em.stream()]
    await harness.drain()
    return tid, events


def last(events, t):
    return [e for e in events if e["type"] == t][-1]


@pytest.fixture
def api(db, llm, monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "test")
    app = create_app(llm=llm, db=db)
    return app


def client(app, **kw):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", **kw)


async def signup(c, email="sam@example.com", password="correct horse 9", name="Sam"):
    r = await c.post("/api/auth/register", json={"email": email, "password": password, "name": name})
    assert r.status_code == 200, r.text
    return r


# ---------------------------------------------------------------- database
def test_old_database_is_migrated(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE users(id TEXT PRIMARY KEY, name TEXT, plan TEXT, country TEXT, auto_spend INTEGER, private_route INTEGER, created_at REAL)")
    con.execute("INSERT INTO users(id,name,plan) VALUES('u_old','Old','free')")
    con.commit()
    con.close()
    db = DB(str(path))
    row = db.one("SELECT * FROM users WHERE id='u_old'")
    assert {"email", "pw_hash", "role", "status", "daily_limit", "monthly_limit", "memory_enabled"} <= set(row)
    assert row["role"] in (None, "user") and db.fts in (True, False)


def test_fulltext_search_follows_message_changes(db):
    db.run("INSERT INTO users(id,name,plan) VALUES('u1','A','free')")
    db.run("INSERT INTO conversations(id,user_id,title,created_at,updated_at) VALUES('c1','u1','t',0,0)")
    db.run("INSERT INTO messages(conversation_id,role,content,created_at) VALUES('c1','user','photosynthesis in leaves',0)")
    assert db.all("SELECT rowid FROM messages_fts WHERE messages_fts MATCH 'photosynthesis'")
    db.run("DELETE FROM messages WHERE conversation_id='c1'")
    assert not db.all("SELECT rowid FROM messages_fts WHERE messages_fts MATCH 'photosynthesis'")


# ---------------------------------------------------------------- accounts
def test_passwords_are_hashed_and_checked():
    h = accounts.hash_password("secret-pass-1")
    assert "secret-pass-1" not in h and h.startswith("pbkdf2_sha256$")
    assert accounts.check_password("secret-pass-1", h) and not accounts.check_password("nope", h)
    assert accounts.hash_password("secret-pass-1") != h            # random salt every time
    with pytest.raises(accounts.AuthError):
        accounts.check_strength("short")


async def test_signup_keeps_the_guests_chats_and_login_logout(api, db):
    async with client(api) as c:
        h = {"x-user-id": "u_guest1"}
        ev = []
        async with c.stream("POST", "/api/chat", json={"message": "hello", "mode": "fast"}, headers=h) as r:
            async for line in r.aiter_lines():
                if line.startswith("data:"):
                    ev.append(json.loads(line[5:]))
        await api.state.harness.drain()
        r = await c.post("/api/auth/register", json={"email": "Sam@Example.com", "password": "correct horse 9", "name": "Sam"}, headers=h)
        assert r.status_code == 200 and "sid" in r.cookies
        me = (await c.get("/api/bootstrap")).json()["user"]
        assert me["registered"] and me["email"] == "sam@example.com" and me["id"] == "u_guest1"
        assert len((await c.get("/api/conversations")).json()) == 1          # chats stayed with the new account
        assert (await c.post("/api/auth/register", json={"email": "sam@example.com", "password": "another pass 1"})).status_code == 400
        await c.post("/api/auth/logout")
        c.cookies.clear()
        assert (await c.post("/api/auth/login", json={"email": "sam@example.com", "password": "wrong password"})).status_code == 401
        assert (await c.post("/api/auth/login", json={"email": "sam@example.com", "password": "correct horse 9"})).status_code == 200
        assert (await c.get("/api/bootstrap")).json()["user"]["email"] == "sam@example.com"


async def test_login_is_rate_limited(api):
    from app import routes_account
    routes_account.attempts.clear()
    async with client(api) as c:
        codes = [(await c.post("/api/auth/login", json={"email": "x@example.com", "password": "bad password"})).status_code for _ in range(12)]
    assert codes[0] == 401 and 429 in codes


async def test_blocked_user_cannot_use_the_app(api, db):
    accounts.ensure_admin(db, "boss@example.com", "admin pass 123")
    async with client(api) as c:
        await signup(c)
        uid = (await c.get("/api/bootstrap")).json()["user"]["id"]
    db.run("UPDATE users SET status='blocked' WHERE id=?", (uid,))
    async with client(api) as c2:
        assert (await c2.post("/api/auth/login", json={"email": "sam@example.com", "password": "correct horse 9"})).status_code == 401


# ---------------------------------------------------------------- admin
async def admin_login(c, db):
    accounts.ensure_admin(db, "boss@example.com", "admin pass 123")
    r = await c.post("/api/auth/login", json={"email": "boss@example.com", "password": "admin pass 123"})
    assert r.status_code == 200
    return c


async def test_admin_routes_need_an_admin(api, db):
    async with client(api) as c:
        for path in ("/api/admin/users", "/api/admin/overview", "/api/admin/queries", "/api/admin/plans", "/api/admin/catalog"):
            assert (await c.get(path)).status_code == 403
        await signup(c)                                  # a normal signed-in user is still not an admin
        assert (await c.get("/api/admin/users")).status_code == 403
        assert (await c.put("/api/admin/users/u_x", json={"role": "admin"})).status_code == 403


async def test_admin_sees_users_queries_credits_and_can_limit(api, db, harness):
    async with client(api) as admin:
        await admin_login(admin, db)
        h = {"x-user-id": "u_student1"}
        harness_ = api.state.harness
        await run(harness_, "u_student1", message="explain gravity please", mode="fast")
        await run(harness_, "u_student1", message="what is a noun", mode="fast")
        users = (await admin.get("/api/admin/users?q=student")).json()
        row = next(u for u in users["users"] if u["id"] == "u_student1")
        assert row["queries"] == 2 and row["runs"] == 2 and row["credits_used"] >= 2
        qs = (await admin.get("/api/admin/queries?q=gravity")).json()
        assert qs["total"] == 1 and qs["queries"][0]["user_id"] == "u_student1" and qs["queries"][0]["credits_used"] >= 1
        bp = (await admin.get("/api/admin/users/u_student1")).json()
        assert bp["totals"]["queries" if "queries" in bp["totals"] else "messages"] == 2 and bp["by_mode"] and bp["timeline"]
        ov = (await admin.get("/api/admin/overview")).json()
        assert ov["users"] >= 2 and ov["queries_today"] >= 2 and ov["ledger_mismatches"] == 0
        # read a chat: it is recorded in the user's own activity (transparency)
        cid = bp["conversations"][0]["id"]
        chat = (await admin.get(f"/api/admin/conversations/{cid}")).json()
        assert [m["role"] for m in chat["messages"]][:2] == ["user", "assistant"]
        assert any(e["kind"] == "admin_viewed_chat" for e in activity.timeline(db, "u_student1"))
        # give credits, take credits
        r = await admin.post("/api/admin/users/u_student1/credits", json={"delta": 500, "reason": "welcome gift"})
        assert r.status_code == 200
        before = r.json()["balance"]
        assert (await admin.post("/api/admin/users/u_student1/credits", json={"delta": -100000})).status_code == 400
        assert wallet.balance(db, "u_student1") == before
        # limit to zero credits a day: the next message is stopped before any AI call
        assert (await admin.put("/api/admin/users/u_student1", json={"daily_limit": 0})).status_code == 200
        tid, ev = await run(harness_, "u_student1", message="one more question", mode="fast")
        assert last(ev, "ask")["kind"] == "limit" and last(ev, "run_done")["status"] == "blocked"
        # raise the limit and it works again
        await admin.put("/api/admin/users/u_student1", json={"daily_limit": 50})
        tid, ev = await run(harness_, "u_student1", message="one more question", mode="fast")
        assert last(ev, "run_done")["status"] == "done"
        # admin actions are in the user's log with the admin as actor
        kinds = {(e["kind"], e["actor"]) for e in activity.timeline(db, "u_student1")}
        assert ("admin_credits", "u_admin") in kinds and ("admin_changed_user", "u_admin") in kinds


async def test_admin_can_block_change_plan_and_not_remove_last_admin(api, db):
    async with client(api) as admin:
        await admin_login(admin, db)
        api.state.harness.get_user("u_t1")
        r = await admin.put("/api/admin/users/u_t1", json={"plan": "pro"})
        assert r.json()["plan"] == "pro" and db.one("SELECT plan_renews_at FROM users WHERE id='u_t1'")["plan_renews_at"] > now()
        assert (await admin.put("/api/admin/users/u_t1", json={"plan": "nonsense"})).status_code == 400
        assert (await admin.put("/api/admin/users/u_t1", json={"status": "blocked"})).json()["status"] == "blocked"
        assert (await admin.put("/api/admin/users/u_admin", json={"status": "blocked"})).status_code == 400   # not yourself
        assert (await admin.put("/api/admin/users/u_admin", json={"role": "user"})).status_code == 400        # last admin
        assert (await admin.put("/api/admin/users/u_t1", json={"role": "admin"})).status_code == 400          # needs an account


async def test_admin_token_header_works_for_scripts(api, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "tok-123456")
    async with client(api) as c:
        assert (await c.get("/api/admin/users", headers={"x-admin-token": "wrong"})).status_code == 403
        assert (await c.get("/api/admin/users", headers={"x-admin-token": "tok-123456"})).status_code == 200


# ---------------------------------------------------------------- plans and purchases
async def test_admin_edits_plans_and_users_see_the_change(api, db):
    async with client(api) as admin:
        await admin_login(admin, db)
        p = (await admin.get("/api/admin/plans")).json()
        student = next(x for x in p["plans"] if x["id"] == "student")
        student.update(price_usd=9.5, credits=1200, benefits=["1,200 credits", "New benefit"])
        student["rules"] = {**student["rules"], "max_effort": "medium", "storage_mb": 777}
        r = await admin.put("/api/admin/plans/student", json=student)
        assert r.status_code == 200 and r.json()["price_usd"] == 9.5
        # a user sees the new price, credits and benefits
    async with client(api) as u:
        shown = next(x for x in (await u.get("/api/plans", headers={"x-user-id": "u_shop1"})).json()["plans"] if x["id"] == "student")
        assert shown["price_usd"] == 9.5 and shown["credits"] == 1200 and "New benefit" in shown["benefits"]
        boot = (await u.get("/api/bootstrap", headers={"x-user-id": "u_shop1"})).json()
        assert boot["plans"]["student"]["rules"]["storage_mb"] == 777
    assert plans.rules("student")["max_effort"] == "medium"
    from app.pricing import clamp_effort
    assert clamp_effort("high", "student") == "medium"      # the new rule is enforced, not just shown


async def test_admin_can_create_a_plan_and_hide_it(api, db):
    async with client(api) as admin:
        await admin_login(admin, db)
        body = {"id": "team", "name": "Team", "kind": "subscription", "price_usd": 40, "credits": 5000, "period_days": 30,
                "benefits": ["5,000 credits"], "rules": {"tiers": ["quick", "smart"], "max_effort": "high", "modes": ["fast", "normal", "deep"]}}
        assert (await admin.post("/api/admin/plans", json=body)).status_code == 200
        assert (await admin.post("/api/admin/plans", json=body)).status_code == 400          # id taken
        await admin.put("/api/admin/users/u_admin", json={"plan": "team"})
        from app import modes
        deep = modes.get(db, "deep")
        assert modes.allowed(deep, "team") and not modes.allowed(modes.get(db, "council"), "team")
        assert (await admin.delete("/api/admin/plans/team")).status_code == 200
        assert (await admin.delete("/api/admin/plans/free")).status_code == 400
    async with client(api) as u:
        assert "team" not in [x["id"] for x in (await u.get("/api/plans", headers={"x-user-id": "u_shop2"})).json()["plans"]]


async def test_purchase_needs_an_account_then_adds_credits_once(api, db):
    async with client(api) as c:
        h = {"x-user-id": "u_buyer1"}
        r = await c.post("/api/purchase", json={"plan_id": "pack_small"}, headers=h)
        assert r.status_code == 400 and "account" in r.json()["detail"].lower()
        await c.post("/api/auth/register", json={"email": "buy@example.com", "password": "buyer pass 123"}, headers=h)
        before = wallet.balance(db, "u_buyer1")
        r = await c.post("/api/purchase", json={"plan_id": "pack_small"})
        assert r.status_code == 200 and r.json()["purchase"]["status"] == "paid"
        assert wallet.balance(db, "u_buyer1") == before + 800
        pid = r.json()["purchase"]["id"]
        billing.complete_purchase(db, pid)                               # a repeated confirmation grants nothing more
        assert wallet.balance(db, "u_buyer1") == before + 800
        r = await c.post("/api/purchase", json={"plan_id": "pro"})
        assert (await c.get("/api/bootstrap")).json()["user"]["plan"] == "pro"
        assert (await c.post("/api/purchase", json={"plan_id": "pro"})).status_code == 400   # already on it
        assert (await c.post("/api/purchase", json={"plan_id": "nope"})).status_code == 400


async def test_manual_provider_waits_for_the_admin(api, db, monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "manual")
    async with client(api) as c, client(api) as admin:
        await admin_login(admin, db)
        await signup(c, "pay@example.com")
        uid = (await c.get("/api/bootstrap")).json()["user"]["id"]
        before = wallet.balance(db, uid)
        r = await c.post("/api/purchase", json={"plan_id": "pack_large"})
        assert r.json()["purchase"]["status"] == "pending" and wallet.balance(db, uid) == before
        pid = r.json()["purchase"]["id"]
        pend = (await admin.get("/api/admin/purchases?status=pending")).json()["purchases"]
        assert pid in [p["id"] for p in pend]
        assert (await admin.post(f"/api/admin/purchases/{pid}/paid")).json()["status"] == "paid"
        assert (await admin.get("/api/admin/overview")).json()["revenue_usd_total"] == 25.0
        assert wallet.balance(db, uid) == before + 2500


def test_monthly_renewal_free_tops_up_paid_lapses(db):
    db.run("INSERT INTO users(id,name,plan,plan_renews_at,created_at) VALUES('u_r1','R','free',?,0)", (now() - 5,))
    wallet.add(db, "u_r1", 30, "start")
    billing.renew(db, db.one("SELECT * FROM users WHERE id='u_r1'"))
    assert wallet.balance(db, "u_r1") == 100                              # topped up to the allowance, not +100
    db.run("INSERT INTO users(id,name,plan,plan_renews_at,created_at) VALUES('u_r2','R','pro',?,0)", (now() - 5,))
    billing.renew(db, db.one("SELECT * FROM users WHERE id='u_r2'"))
    assert db.one("SELECT plan FROM users WHERE id='u_r2'")["plan"] == "free"   # no payment, no paid plan


# ---------------------------------------------------------------- memory
def test_memory_dedupes_refuses_secrets_and_deletes_for_real(db):
    db.run("INSERT INTO users(id,name,plan) VALUES('u1','A','free')")
    a = memory.add(db, "u1", "Prefers short answers with examples")
    b = memory.add(db, "u1", "prefers short answers, with examples!")
    assert a["id"] == b["id"] and len(memory.listing(db, "u1")) == 1
    assert memory.add(db, "u1", "My password is hunter2") is None
    assert memory.add(db, "u1", "card number 4111111111111111") is None
    assert memory.delete(db, "u1", a["id"]) and db.scalar("SELECT COUNT(*) FROM memories") == 0
    assert not db.all("SELECT rowid FROM memories_fts WHERE memories_fts MATCH 'prefers'")


def test_memory_belongs_to_one_user(db):
    for u in ("u1", "u2"):
        db.run("INSERT INTO users(id,name,plan) VALUES(?,?, 'free')", (u, u))
    m = memory.add(db, "u1", "Studies physics for an exam in June")
    assert memory.get(db, "u2", m["id"]) is None and not memory.delete(db, "u2", m["id"])
    assert memory.update(db, "u2", m["id"], content="hacked") is None
    assert memory.search(db, "u2", "physics") == []


async def test_remember_command_saves_and_is_used_in_later_chats(harness, db, fake):
    harness.get_user("u_m1")
    tid, ev = await run(harness, "u_m1", message="Remember that I always want answers in simple Urdu words", mode="fast")
    assert any(e["type"] == "memory" and e["action"] == "saved" for e in ev)
    saved = memory.listing(db, "u_m1")
    assert saved[0]["pinned"] == 1 and saved[0]["kind"] == "instruction"
    # a brand new chat still knows it
    fake.requests.clear()
    tid, ev = await run(harness, "u_m1", message="Explain gravity", mode="fast")
    assert any("simple Urdu" in str(r["messages"][0]["content"]) for r in fake.requests)


async def test_secret_in_remember_is_refused(harness, db):
    harness.get_user("u_m2")
    tid, ev = await run(harness, "u_m2", message="remember that my password is hunter2", mode="fast")
    assert memory.listing(db, "u_m2") == []
    assert any("secret" in n for n in last(ev, "answer")["notices"])      # the refusal is told to the user


async def test_forget_command_really_deletes(harness, db):
    harness.get_user("u_m3")
    memory.add(db, "u_m3", "Likes cricket examples")
    memory.add(db, "u_m3", "Studies chemistry")
    tid, ev = await run(harness, "u_m3", message="forget about cricket", mode="fast")
    assert [m["content"] for m in memory.listing(db, "u_m3")] == ["Studies chemistry"]


async def test_auto_memory_and_session_notes_are_learned_after_each_turn(harness, db, fake):
    fake.memory_add = True
    harness.get_user("u_m4")
    tid, ev = await run(harness, "u_m4", message="Explain seeds to me", mode="fast")
    mems = memory.listing(db, "u_m4")
    assert any("cricket" in m["content"] for m in mems) and mems[0]["source"] == "auto"
    conv = db.one("SELECT notes FROM conversations WHERE user_id='u_m4'")
    assert "Studied seeds" in conv["notes"]
    assert any(e["kind"] == "memory_learned" for e in activity.timeline(db, "u_m4"))


async def test_session_notes_and_earlier_chats_reach_the_ai(harness, db, fake):
    harness.get_user("u_m5")
    tid, ev = await run(harness, "u_m5", message="Explain photosynthesis in leaves", mode="fast")
    cid = last(ev, "run_start")["conversation_id"]
    tid, ev = await run(harness, "u_m5", message="Why is it green?", mode="fast", conversation_id=cid)
    assert "Studied seeds" in fake.requests[-1]["messages"][0]["content"] or any("Studied seeds" in str(r["messages"][0]["content"]) for r in fake.requests[-3:])
    # new chat: related moments from the old chat are recalled
    fake.requests.clear()
    tid, ev = await run(harness, "u_m5", message="Remind me about photosynthesis", mode="fast")
    sys = next(r["messages"][0]["content"] for r in fake.requests if "Related moments" in r["messages"][0]["content"])
    assert "photosynthesis" in sys.lower() and any(e["type"] == "memory" and e.get("recalled_chats") for e in ev)


async def test_memory_can_be_turned_off(harness, db, fake):
    harness.get_user("u_m6")
    memory.add(db, "u_m6", "Loves astronomy examples", importance=5)
    db.run("UPDATE users SET memory_enabled=0 WHERE id='u_m6'")
    await run(harness, "u_m6", message="Explain stars", mode="fast")
    assert not any("astronomy" in str(r["messages"][0]["content"]) for r in fake.requests)
    assert not any("long-term memory" in str(r["messages"][0]["content"]) for r in fake.requests)   # and nothing new is learned
    assert len(memory.listing(db, "u_m6")) == 1


async def test_memory_api_crud_and_isolation(api, db):
    async with client(api) as c:
        h = {"x-user-id": "u_mema1"}
        r = await c.post("/api/memory", json={"content": "Wants step by step maths", "kind": "preference", "importance": 4, "pinned": True}, headers=h)
        mid = r.json()["id"]
        assert (await c.post("/api/memory", json={"content": "my api key is sk-abcdefghijkl"}, headers=h)).status_code == 400
        assert (await c.put(f"/api/memory/{mid}", json={"content": "Wants step by step maths and examples"}, headers=h)).json()["content"].endswith("examples")
        assert (await c.get("/api/memory?q=maths", headers=h)).json()["items"][0]["id"] == mid
        assert (await c.delete(f"/api/memory/{mid}", headers={"x-user-id": "u_other1"})).status_code == 404
        assert (await c.put("/api/memory/enabled", json={"enabled": False}, headers=h)).json()["enabled"] is False
        assert (await c.delete(f"/api/memory/{mid}", headers=h)).status_code == 200
        assert (await c.get("/api/memory", headers=h)).json()["items"] == []


# ---------------------------------------------------------------- blueprint, export, delete
async def test_blueprint_export_and_delete_account(api, db):
    harness_ = api.state.harness
    async with client(api) as c:
        h = {"x-user-id": "u_bprnt1"}
        await run(harness_, "u_bprnt1", message="explain gravity", mode="fast")
        memory.add(db, "u_bprnt1", "Studies for the physics exam")
        bp = (await c.get("/api/me/blueprint", headers=h)).json()
        assert bp["totals"]["runs"] == 1 and bp["totals"]["conversations"] == 1 and bp["memories"] and bp["wallet"]["balance"] < 100
        assert [e["kind"] for e in bp["timeline"]][-1] == "account_created" or any(e["kind"] == "chat_sent" for e in bp["timeline"])
        data = (await c.get("/api/me/export", headers=h)).json()
        assert data["conversations"][0]["messages"][0]["content"] == "explain gravity" and "pw_hash" not in json.dumps(data)
        assert (await c.request("DELETE", "/api/me", json={"confirm": "no"}, headers=h)).status_code == 400
        assert (await c.request("DELETE", "/api/me", json={"confirm": "DELETE"}, headers=h)).status_code == 200
    for table in ("conversations", "messages", "tasks", "memories", "credit_ledger", "usage_events", "activity"):
        col = "user_id"
        if table == "messages":
            assert db.scalar("SELECT COUNT(*) FROM messages") == 0
        else:
            assert db.scalar(f"SELECT COUNT(*) FROM {table} WHERE user_id='u_bprnt1'") == 0
    assert db.one("SELECT id FROM users WHERE id='u_bprnt1'") is None


async def test_login_cookie_user_cannot_read_another_users_blueprint(api, db):
    async with client(api) as a, client(api) as b:
        await signup(a, "a@example.com")
        await signup(b, "b@example.com")
        mine = (await a.get("/api/me/blueprint")).json()["user"]["id"]
        theirs = (await b.get("/api/me/blueprint")).json()["user"]["id"]
        assert mine != theirs
        assert (await a.get(f"/api/admin/users/{theirs}")).status_code == 403


# ---------------------------------------------------------------- owner mode (UNLOCK_ALL)
async def test_unlock_all_gives_the_owner_everything(api, db, monkeypatch):
    monkeypatch.setattr(settings, "unlock_all", True)
    async with client(api) as c:
        h = {"x-user-id": "u_owner1"}
        boot = (await c.get("/api/bootstrap", headers=h)).json()
        assert boot["user"]["plan"] == "owner" and boot["unlock_all"] is True
        assert boot["wallet"]["balance"] >= 100000
        assert all(m["allowed"] for m in boot["modes"]) and len(boot["modes"]) == 10
        assert all(e["allowed"] for e in boot["efforts"]) and all(m["allowed"] for m in boot["models"])
        assert boot["plans"]["owner"]["rules"]["max_effort"] == "max"
        # it is hidden from the store, and a Pro-only mode really runs
        assert "owner" not in [p["id"] for p in (await c.get("/api/plans", headers=h)).json()["plans"]]
    tid, ev = await run(api.state.harness, "u_owner1", message="explain gravity", mode="council", confirm=True)
    assert last(ev, "run_done")["status"] == "done"


async def test_without_unlock_all_the_plan_limits_still_apply(api, db):
    async with client(api) as c:
        boot = (await c.get("/api/bootstrap", headers={"x-user-id": "u_plain01"})).json()
        assert boot["user"]["plan"] == "free" and not boot["unlock_all"]
        assert not next(m for m in boot["modes"] if m["id"] == "council")["allowed"]


# ---------------------------------------------------------------- deployment
async def test_healthz_is_open_and_checks_the_database(api):
    async with client(api) as c:
        r = await c.get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True}


async def test_unlock_admin_gives_only_the_admin_every_feature(api, db, monkeypatch):
    monkeypatch.setattr(settings, "unlock_admin", True)
    accounts.ensure_admin(db, "boss@example.com", "admin pass 123")
    async with client(api) as admin, client(api) as visitor:
        await admin_login(admin, db)
        me = (await admin.get("/api/bootstrap")).json()
        assert me["user"]["plan"] == "owner" and all(m["allowed"] for m in me["modes"]) and me["wallet"]["balance"] >= 100000
        v = (await visitor.get("/api/bootstrap", headers={"x-user-id": "u_visit01"})).json()
        assert v["user"]["plan"] == "free" and not next(m for m in v["modes"] if m["id"] == "council")["allowed"]
        assert v["wallet"]["balance"] == 100                       # a public visitor gets no free credits


# ---------------------------------------------------------------- prompts, skills, tools
def test_every_prompt_the_code_asks_for_exists():
    """A missing prompt file would only fail at runtime, mid-answer."""
    import re as _re
    from pathlib import Path

    from app import prompts
    src = "\n".join(p.read_text() for p in Path("backend/app").glob("*.py"))
    wanted = set(_re.findall(r'prompts\.(?:get|render)\("([a-z_]+)"', src))
    assert wanted, "no prompt lookups found; the scan is broken"
    for name in wanted:
        assert prompts.get(name).strip(), f"prompt {name} is missing or empty"


def test_prompts_carry_the_rules_that_keep_answers_honest():
    from app import prompts
    for name in ("direct", "teacher"):
        body = prompts.get(name)
        assert "{{calc: expression}}" in body            # arithmetic goes to the calculator
        assert "never instructions" in body              # uploads are data
        assert "invent" in body                          # no invented facts or sources
    assert "Do not add analogies, lessons" in prompts.get("direct")
    for name in ("router", "planner", "checker", "critic", "calc_step", "team_planner", "team_check"):
        assert "JSON only" in prompts.get(name) or "nothing else" in prompts.get(name), name


def test_skills_are_discoverable_and_small():
    from app import skills
    sk = skills.all_skills()
    assert len(sk) >= 15
    for name, s in sk.items():
        assert s.description and len(s.description) > 40, f"{name} needs a description that can trigger it"
        assert "Use when" in s.description, f"{name} must say when it applies"
        assert len(s.body) < 6000, f"{name} body is too big to load cheaply"


def test_keyword_matching_avoids_paying_a_model_to_pick_a_skill():
    from app import skills
    for text, want in [("my script crashes with a KeyError", "debugger"), ("write unit tests for this", "test-writer"),
                       ("speed up this SQL query", "sql-helper"), ("solve 3x + 7 = 22", "math-solver"),
                       ("summarize this paper", "summarizer"), ("quiz me on fractions", "exam-coach")]:
        assert skills.match_keywords(text) == want, text
    assert skills.match_keywords("hello there") is None      # no false trigger on small talk


def test_flashcards_and_tables_are_validated_before_the_browser_sees_them():
    from app.postprocess import validate_flashcards, validate_table
    deck = validate_flashcards({"title": "T", "cards": [{"front": f"q{i}", "back": "a"} for i in range(4)] + [{"front": "Q0", "back": "dup"}]})
    assert len(deck["cards"]) == 4                            # the duplicate front is dropped
    t = validate_table({"columns": [{"key": "a", "label": "A"}, {"key": "b", "type": "number", "unit": "$"}],
                        "rows": [{"a": "x", "b": "3"}, {"a": "y"}]})
    assert t["rows"][0]["b"] == 3.0 and t["rows"][1]["b"] is None    # text numbers parsed, missing stays empty
    for bad in ({"cards": [{"front": "q", "back": "a"}]}, {"cards": []}):
        with pytest.raises(ValueError):
            validate_flashcards(bad)
    for bad in ({"columns": [{"key": "a"}], "rows": [{}]}, {"columns": [{"key": "a"}, {"key": "b"}], "rows": []}):
        with pytest.raises(ValueError):
            validate_table(bad)


async def test_flashcard_and_table_blocks_become_artifacts(harness, fake, db):
    fake.extra_blocks = True
    harness.get_user("u_art1")
    tid, events = await run(harness, "u_art1", message="make me flashcards and a table to compare them", mode="fast")
    kinds = {e["kind"] for e in events if e["type"] == "artifact"}
    assert {"flashcards", "table"} <= kinds
    text = ""
    for e in events:
        if e["type"] == "text":
            text = e["delta"] if e.get("replace") else text + e["delta"]
    assert "```flashcards" not in text and "[[artifact:" in text      # the raw block is replaced by a marker


async def test_a_greeting_does_not_drag_in_memory_or_reopen_an_old_question(harness, db, fake):
    """'hi' once made the model answer the previous chat's question, because memories were on the desk."""
    harness.get_user("u_greet1")
    memory.add(db, "u_greet1", "Wants to memorise the planets in order", importance=5, pinned=True)
    db.run("INSERT OR REPLACE INTO profiles(user_id,data,updated_at) VALUES('u_greet1',?,0)",
           ('{"goal": "memorise the planets in order", "level": "beginner"}',))
    fake.requests.clear()
    tid, ev = await run(harness, "u_greet1", message="hi", mode="fast")
    system = fake.requests[0]["messages"][0]["content"]
    assert "planets" not in system and "BACKGROUND" not in system
    assert not any(e["type"] == "memory" and e.get("action") == "recalled" for e in ev)
    # a real question still gets the background
    fake.requests.clear()
    await run(harness, "u_greet1", message="Explain how orbits work", mode="fast")
    system = fake.requests[0]["messages"][0]["content"]
    assert "planets" in system and "BACKGROUND" in system


def test_memory_is_labelled_as_background_not_as_a_task(db):
    db.run("INSERT INTO users(id,name,plan,memory_enabled) VALUES('u_bg','B','free',1)")
    memory.add(db, "u_bg", "Studying for a June physics exam", importance=5, pinned=True)
    block, ids = memory.desk_block(db, db.one("SELECT * FROM users WHERE id='u_bg'"), None, "Explain inertia")
    assert ids and "not a task to carry out" in block and "Never answer it" in block


# ---------------------------------------------------------------- documents
async def test_a_document_becomes_a_real_file_the_user_owns(harness, db, fake, tmp_path):
    fake.doc_block = True
    harness.get_user("u_doc1")
    tid, events = await run(harness, "u_doc1", message="create a document for learning AI", mode="normal")
    art = [e for e in events if e["type"] == "artifact" and e["kind"] == "doc"][0]
    assert art["data"]["title"] == "AI Learning Guide" and art["data"]["words"] > 5
    row = db.one("SELECT * FROM workspace_files WHERE user_id='u_doc1' AND kind='doc'")
    assert row and row["path"].endswith(".md") and row["size"] > 40
    assert workspace.path_of(row).read_text().startswith("# AI Learning Guide")
    assert art["data"]["file_id"] == row["id"]                      # the card points at the stored file
    text = ""
    for e in events:
        if e["type"] == "text":
            text = e["delta"] if e.get("replace") else text + e["delta"]
    assert "```doc" not in text and f"[[artifact:{art['id']}]]" in text


async def test_deleting_a_document_removes_the_file_and_the_row(api, db):
    harness_ = api.state.harness
    api.state.harness.llm._client._transport  # noqa: B018  (the fake transport is already wired)
    async with client(api) as c:
        h = {"x-user-id": "u_docdel"}
        harness_.get_user("u_docdel")
        d = workspace.task_dir("u_docdel", "t_manual", "manual")
        p = d / "out" / "guide.md"
        p.write_text("# Guide\n\nSome body text that is long enough to keep.")
        rec = workspace.register(db, "u_docdel", "t_manual", p, "doc", "free")
        assert (await c.get("/api/files", headers=h)).json()["files"]
        prev = (await c.get(f"/api/files/{rec['id']}/preview", headers=h)).json()
        assert prev["kind"] == "doc" and prev["markdown"].startswith("# Guide")
        assert (await c.delete(f"/api/files/{rec['id']}", headers={"x-user-id": "u_other99"})).status_code == 404
        assert (await c.delete(f"/api/files/{rec['id']}", headers=h)).status_code == 200
    assert not p.exists()
    assert db.one("SELECT id FROM workspace_files WHERE id=?", (rec["id"],)) is None


async def test_documents_count_against_the_storage_quota(api, db, monkeypatch):
    from app import plans as plans_mod
    harness_ = api.state.harness
    harness_.get_user("u_quota")
    async with client(api) as c:
        files = (await c.get("/api/files", headers={"x-user-id": "u_quota"})).json()
        assert files["limit_bytes"] == 20 * 1024 * 1024          # 20 MB on the free plan
    assert plans_mod.rules("free")["storage_mb"] == 20
    d = workspace.task_dir("u_quota", "t_big", "big")
    big = d / "out" / "big.md"
    big.write_text("x" * 1000)
    workspace.register(db, "u_quota", "t_big", big, "doc", "free")
    with pytest.raises(workspace.PathEscape):
        workspace.check_storage(db, "u_quota", "free", 21 * 1024 * 1024)


async def test_slides_are_saved_as_a_deck_file(harness, db, fake):
    fake.slides_block = True
    harness.get_user("u_sl1")
    tid, events = await run(harness, "u_sl1", message="make me a slide deck about water", mode="normal")
    art = [e for e in events if e["type"] == "artifact" and e["kind"] == "slides"][0]
    assert art["data"]["slides"] == 3
    row = db.one("SELECT * FROM workspace_files WHERE user_id='u_sl1' AND kind='slides'")
    assert row and workspace.path_of(row).read_text().count("---") >= 2


# ---------------------------------------------------------------- generated pictures
def test_image_models_are_detected_from_the_live_list(db):
    from app import catalog
    live = [{"id": "google/nano-banana-2.1", "name": "Nano Banana", "pricing": {"prompt": "0.0000015", "completion": "0.00003"},
             "architecture": {"output_modalities": ["image", "text"]}, "supported_parameters": []},
            {"id": "lab/text-only", "name": "Text", "pricing": {"prompt": "0.000001", "completion": "0.000002"},
             "architecture": {"output_modalities": ["text"]}, "supported_parameters": []}]
    catalog.sync_live(db, live)
    assert catalog.image_models(db) == []                      # new models wait for approval
    catalog.approve(db, "google/nano-banana-2.1", "smart")
    assert [m["id"] for m in catalog.image_models(db)] == ["google/nano-banana-2.1"]


def test_only_a_real_picture_is_accepted():
    import base64
    from app.tools.image import ImageError, decode
    png = b"\x89PNG\r\n\x1a\n" + b"body" * 10
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    raw, ext = decode([{"image_url": {"url": url}}])
    assert ext == "png" and raw == png
    for bad in ([], [{"image_url": {"url": "https://example.com/a.png"}}],
                [{"image_url": {"url": "data:image/png;base64,###"}}],
                [{"image_url": {"url": "data:image/png;base64," + base64.b64encode(b"<svg onload=x>").decode()}}]):
        with pytest.raises(ImageError):
            decode(bad)


# The catalog seeds real picture models, approved but never chosen for the user.
IMAGE_MODEL = "google/gemini-3.1-flash-image"


def test_picture_models_are_seeded_but_never_used_as_a_thinking_brain(db):
    from app import catalog
    assert IMAGE_MODEL in [m["id"] for m in catalog.image_models(db)]
    assert IMAGE_MODEL not in [m["id"] for m in catalog.listing(db)]


async def test_the_user_is_asked_which_image_model_before_anything_is_drawn(harness, db, fake):
    fake.image_block = True
    harness.get_user("u_img1")
    tid, events = await run(harness, "u_img1", message="draw me a leaf", mode="fast", tools=["images"])
    ask = [e for e in events if e["type"] == "ask" and e["kind"] == "image_model"]
    assert ask and "pick which image model" in ask[0]["text"]
    assert not db.all("SELECT id FROM workspace_files WHERE user_id='u_img1'")     # nothing drawn, nothing paid
    assert not [e for e in events if e["type"] == "artifact" and e["kind"] == "image"]


async def test_a_chosen_model_draws_and_stores_the_picture(harness, db, fake):
    fake.image_block = True
    fake.returns_image = True
    harness.get_user("u_img2")
    tid, events = await run(harness, "u_img2", message="draw me a leaf", mode="fast", tools=["images"],
                            image_model=IMAGE_MODEL)
    art = [e for e in events if e["type"] == "artifact" and e["kind"] == "image"]
    assert art and art[0]["data"]["model"] == "Nano Banana 2"
    row = db.one("SELECT * FROM workspace_files WHERE user_id='u_img2'")
    assert row and row["kind"] == "png" and workspace.path_of(row).read_bytes().startswith(b"\x89PNG")


async def test_images_stay_off_unless_the_tool_is_on(harness, db, fake):
    fake.image_block = True
    harness.get_user("u_img3")
    tid, events = await run(harness, "u_img3", message="draw me a leaf", mode="fast", tools=["chart"])
    assert not [e for e in events if e["type"] == "ask" and e["kind"] == "image_model"]
    assert not db.all("SELECT id FROM workspace_files WHERE user_id='u_img3'")
