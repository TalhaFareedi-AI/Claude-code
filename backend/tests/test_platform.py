"""Accounts, admin, plans and purchases, limits, memory and the user blueprint."""
import json
import sqlite3

import httpx
import pytest

from app import accounts, activity, billing, memory, plans, wallet
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
