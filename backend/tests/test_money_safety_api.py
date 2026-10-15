import json
import time

import httpx
import pytest

from app import catalog, modes, wallet, workspace
from app.estimate import estimate
from app.main import create_app
from app.openrouter import build_reasoning


# ---------------------------------------------------------------- estimates equal the plan's worked examples
@pytest.fixture
def M(db):
    g = lambda i: catalog.get(db, i)
    return lambda mid: modes.get(db, mid), g


def test_plan_numbers_for_every_mode(db, M):
    mode, g = M
    ds, so, op, kimi = (g(i) for i in ["deepseek/deepseek-v4-pro-0813", "anthropic/claude-sonnet-5.5", "anthropic/claude-opus-5.5", "moonshotai/kimi-k3"])
    qm, qf, hk, mm = (g(i) for i in ["qwen/qwen3.8-max-0902", "qwen/qwen3.8-flash", "anthropic/claude-haiku-5.5", "minimax/minimax-m3"])
    E = lambda mid, b, **k: estimate(mode(mid), b, **k)["credits"]
    assert [E("normal", {"answer": [m]}) for m in (ds, kimi, so, op)] == [1, 5, 5, 10]
    assert [E("think_again", {"write": [m], "critic": [m]}) for m in (ds, kimi, so, op)] == [4, 34, 35, 69]
    assert [E("overthink", {"think": [m], "judge": [m]}) for m in (ds, kimi, so, op)] == [9, 136, 100, 200]
    assert E("council", {"members": [ds, qm, hk], "judge": [so]}) == 16
    assert E("council", {"members": [ds, mm, qf], "judge": [hk]}) == 3
    assert E("two_brains", {"think": [qm], "answer": [ds]}) == 18
    assert E("two_brains", {"think": [ds], "answer": [op]}) == 13
    assert E("think_team", {"think": [qm, ds, hk], "answer": [so]}) == 16
    assert E("think_team", {"think": [qm, ds, hk], "answer": [op]}) == 22
    # Deep on Opus: 6 steps alone are 122 credits in the plan; planner + checker add a little
    parts = estimate(mode("deep"), {r: [op] for r in ("planner", "worker", "checker", "answer")})["parts"]
    steps = sum(p["usd"] for p in parts if p["name"].startswith("step"))
    from app.pricing import credits_for_cost
    assert credits_for_cost(steps) == 122


def test_effort_changes_the_estimate(db, M):
    mode, g = M
    so = g("anthropic/claude-sonnet-5.5")
    b = {"think": [so], "judge": [so]}
    low = estimate(mode("overthink"), b, effort="low")["credits"]
    high = estimate(mode("overthink"), b, effort="high")["credits"]
    off = estimate(mode("overthink"), b, effort="off")["credits"]
    assert off < low < high


def test_reasoning_object_rules(db):
    g = lambda i: catalog.get(db, i)
    assert build_reasoning(g("deepseek/deepseek-v4.1-flash"), "high", 4000) is None        # model does not think
    assert build_reasoning(g("moonshotai/kimi-k3"), "high", 4000) == {"effort": "high"}     # level style
    assert build_reasoning(g("moonshotai/kimi-k3"), "max", 4000) == {"effort": "xhigh"}
    assert build_reasoning(g("anthropic/claude-sonnet-5.5"), "medium", 8000) == {"max_tokens": 4000}  # budget style
    assert build_reasoning(g("anthropic/claude-sonnet-5.5"), "max", 2000) == {"max_tokens": 1744}   # leaves room for the answer
    assert build_reasoning(g("anthropic/claude-sonnet-5.5"), "off", 8000) == {"enabled": False}
    assert build_reasoning(g("moonshotai/kimi-k3"), "auto", 4000) is None


# ---------------------------------------------------------------- wallet (plan section 9, step 5)
def test_hold_then_settle_example_from_the_plan(db):
    db.run("INSERT INTO users(id,name,plan,created_at) VALUES('w','W','pro',0)")
    wallet.add(db, "w", 200, "start")
    wallet.hold(db, "w", "ppt", 120)
    assert wallet.available(db, "w") == 80
    with pytest.raises(wallet.InsufficientCredits):
        wallet.hold(db, "w", "deep", 150)                 # needs 150, only 80 free
    assert wallet.settle(db, "w", "ppt", 85) == 85         # real cost 85, release 35
    assert wallet.balance(db, "w") == 115 and wallet.held(db, "w") == 0


def test_settle_never_charges_more_than_the_hold(db):
    db.run("INSERT INTO users(id,name,plan,created_at) VALUES('w','W','pro',0)")
    wallet.add(db, "w", 50, "start")
    wallet.hold(db, "w", "t", 10)
    assert wallet.settle(db, "w", "t", 500) == 10 and wallet.balance(db, "w") == 40
    assert wallet.settle(db, "w", "t", 5) == 0            # settled twice does nothing


# ---------------------------------------------------------------- workspace safety
def test_path_traversal_is_blocked(tmp_path):
    for bad in ("../u_2/secret.txt", "/etc/passwd", "a/../../u_2"):
        with pytest.raises(workspace.PathEscape):
            workspace.safe_path("u_1", bad)
    with pytest.raises(workspace.PathEscape):
        workspace.user_root("../u_2")
    assert workspace.clean_name("../../etc/passwd") == "passwd"
    assert workspace.clean_name("a b<script>.txt").endswith(".txt")


def test_signed_links_expire_and_bind_to_user():
    t = workspace.sign("f_1", "u_1", ttl=60)
    assert workspace.verify(t, "u_1") == "f_1"
    assert workspace.verify(t, "u_2") is None                       # another user cannot reuse it
    fid, exp, sig = t.split(".")
    assert workspace.verify(f"{fid}.{int(exp) + 999}.{sig}", "u_1") is None   # tampered
    assert workspace.verify(workspace.sign("f_1", "u_1", ttl=-1), "u_1") is None  # expired


# ---------------------------------------------------------------- catalog sync
def test_catalog_sync_updates_prices_flags_alarms_and_holds_new_models(db, fake):
    import asyncio
    from app.openrouter import OpenRouter
    llm = OpenRouter(api_key="k", base_url="http://fake", transport=fake.transport())
    db.run("UPDATE model_catalog SET price_out=1.0 WHERE id='anthropic/claude-sonnet-5.5'")   # live is 10.0
    rep = asyncio.get_event_loop().run_until_complete(llm.list_models()) if False else None
    models = asyncio.run(llm.list_models())
    rep = catalog.sync_live(db, models)
    assert "anthropic/claude-fable-5.1" in rep["missing"]
    assert db.one("SELECT available FROM model_catalog WHERE id='anthropic/claude-fable-5.1'")["available"] == 0
    assert any(a["model"] == "anthropic/claude-sonnet-5.5" for a in rep["alarms"])
    assert catalog.get(db, "anthropic/claude-sonnet-5.5")["price_out"] == pytest.approx(10.0)
    new = catalog.get(db, "newlab/new-model")
    assert new["approved"] == 0                                        # appears only after you approve it
    assert "newlab/new-model" not in [m["id"] for m in catalog.listing(db)]
    catalog.approve(db, "newlab/new-model", "quick")
    assert "newlab/new-model" in [m["id"] for m in catalog.listing(db)]
    assert db.scalar("SELECT COUNT(*) FROM model_prices WHERE model_id='anthropic/claude-sonnet-5.5'") == 2


def test_cheap_policy_and_free_models_are_never_offered(db):
    r = catalog.resolve(db, "genius", policy="cheap")
    assert r["tier"] in ("quick", "smart")
    db.run("INSERT INTO model_catalog(id,name,lab,region,tier,price_in,price_out,thinks,approved,available) VALUES('x/y:free','f','x','west','quick',0,0,1,1,1)")
    assert catalog.resolve(db, "quick", policy="cheap")["id"] != "x/y:free"
    assert catalog.resolve(db, "genius", policy="preferred")["tier"] == "genius"


# ---------------------------------------------------------------- HTTP API
@pytest.fixture
async def client(db, llm):
    app = create_app(llm=llm, db=db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def sse_events(client, body, headers=None):
    events = []
    async with client.stream("POST", "/api/chat", json=body, headers=headers or {}) as r:
        assert r.status_code == 200
        async for line in r.aiter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return events


async def test_bootstrap_lists_modes_models_efforts_for_plan(client):
    b = (await client.get("/api/bootstrap", headers={"x-user-id": "u_api1"})).json()
    assert len(b["modes"]) == 10 and {m["id"] for m in b["modes"]} >= {"fast", "think_team", "developer"}
    free_locked = {m["id"] for m in b["modes"] if not m["allowed"]}
    assert {"overthink", "council", "think_team"} <= free_locked
    assert {e["id"]: e["allowed"] for e in b["efforts"]}["max"] is False
    assert any(m["lab"] == "DeepSeek" and m["region"] == "china" for m in b["models"])
    assert b["wallet"]["balance"] == 100 and len(b["skills"]) == 7


async def test_estimate_endpoint_is_live(client):
    h = {"x-user-id": "u_api2"}
    a = (await client.post("/api/estimate", json={"mode": "normal", "message": "hi"}, headers=h)).json()
    assert a["credits"] >= 1 and a["cap"] >= a["credits"]
    bad = await client.post("/api/estimate", json={"mode": "overthink", "message": "hi"}, headers=h)
    assert bad.status_code == 400


async def test_chat_stream_end_to_end_and_conversation_reload(client):
    h = {"x-user-id": "u_api3"}
    ev = await sse_events(client, {"message": "hello", "mode": "fast"}, h)
    assert ev[0]["type"] == "hello" and ev[-1]["type"] == "run_done"
    cid = ev[0]["conversation_id"]
    conv = (await client.get(f"/api/conversations/{cid}", headers=h)).json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"] and conv["messages"][1]["buttons"]
    # a reload replays the run from saved events
    rep = (await client.get(f"/api/runs/{ev[0]['task_id']}/events", headers=h)).json()
    assert rep["status"] == "done" and rep["events"][-1]["type"] == "run_done"
    # another user can not read it
    assert (await client.get(f"/api/conversations/{cid}", headers={"x-user-id": "u_other"})).status_code == 404
    assert (await client.get(f"/api/runs/{ev[0]['task_id']}/events", headers={"x-user-id": "u_other"})).status_code == 404


async def test_upload_download_and_isolation(client):
    h = {"x-user-id": "u_api4"}
    r = await client.put("/api/upload", params={"name": "notes.txt"}, content=b"photosynthesis notes", headers=h)
    assert r.status_code == 200
    ev = await sse_events(client, {"message": "summarize my notes", "mode": "fast", "uploads": [r.json()["id"]]}, h)
    assert ev[-1]["type"] == "run_done"
    assert (await client.put("/api/upload", params={"name": "evil.exe"}, content=b"MZ", headers=h)).status_code == 400
    assert (await client.put("/api/upload", params={"name": "fake.pdf"}, content=b"not a pdf", headers=h)).status_code == 400
    big = await client.put("/api/upload", params={"name": "big.txt"}, content=b"a" * (3 * 1024 * 1024), headers=h)
    assert big.status_code == 413


async def test_file_links_download_and_other_users_are_refused(client):
    h = {"x-user-id": "u_api5"}
    ev = await sse_events(client, {"message": "Make a 4 slides PPT on plants", "mode": "auto", "confirm": True}, {"x-user-id": "u_api5"})
    # free plan can't run Deep, so it falls back to normal and no file: upgrade in dev and retry
    await client.post("/api/dev/plan", json={"plan": "student"}, headers=h)
    await client.post("/api/dev/topup", json={"credits": 500}, headers=h)
    ev = await sse_events(client, {"message": "Make a 4 slides PPT on plants", "mode": "auto", "confirm": True}, h)
    f = [e["file"] for e in ev if e["type"] == "file_created" and e["file"]["name"].endswith(".pptx")][0]
    link = (await client.get(f"/api/files/{f['id']}/link", headers=h)).json()["url"]
    dl = await client.get(link, headers=h)
    assert dl.status_code == 200 and dl.content[:2] == b"PK"
    assert "attachment" in dl.headers["content-disposition"] and dl.headers["x-content-type-options"] == "nosniff"
    assert (await client.get(link, headers={"x-user-id": "u_thief"})).status_code == 403
    assert (await client.get(f"/api/files/{f['id']}/link", headers={"x-user-id": "u_thief"})).status_code == 404
    prev = (await client.get(f"/api/files/{f['id']}/preview", headers=h)).json()
    assert prev["items"] and prev["items"][0]["title"]
    await client.delete("/api/workspace", headers=h)
    assert (await client.get("/api/files", headers=h)).json()["files"] == []


async def test_rate_limit_and_security_headers(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "rate_per_minute", 2)
    h = {"x-user-id": "u_api6"}
    for _ in range(2):
        await sse_events(client, {"message": "hi", "mode": "fast"}, h)
    r = await client.post("/api/chat", json={"message": "hi", "mode": "fast"}, headers=h)
    assert r.status_code == 429
    b = await client.get("/api/bootstrap", headers=h)
    assert "default-src 'self'" in b.headers["content-security-policy"] and b.headers["x-content-type-options"] == "nosniff"


async def test_profile_can_be_seen_edited_and_deleted(client):
    h = {"x-user-id": "u_api7"}
    await client.put("/api/profile", json={"level": "beginner", "interests": ["cricket"], "evil": "x"}, headers=h)
    p = (await client.get("/api/profile", headers=h)).json()
    assert p == {"level": "beginner", "interests": ["cricket"]}
    await client.delete("/api/profile", headers=h)
    assert (await client.get("/api/profile", headers=h)).json() == {}
