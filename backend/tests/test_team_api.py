"""Boundary checks for team preferences, request identity and browser ownership."""
import httpx
import pytest

from app.config import settings
from app.main import create_app


@pytest.fixture
async def team_client(db, llm):
    app = create_app(llm=llm, db=db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, app


async def test_estimate_receives_team_and_teacher_preferences(team_client, monkeypatch):
    client, app = team_client
    seen = {}

    original_route = app.state.harness.route_rules
    def capture_route(req):
        seen.update(vars(req))
        return original_route(req)
    monkeypatch.setattr(app.state.harness, "route_rules", capture_route)
    estimate = await client.post("/api/estimate", json={"message": "hello", "mode": "fast", "team": {"preset": "fast"}, "teacher_enabled": False})
    assert estimate.status_code == 200 and seen["team"] == {"preset": "fast"} and seen["teacher_enabled"] is False
    seen.clear()

    # Chat uses the same conversion, including approval and request identity.
    class DoneEmitter:
        def __init__(self):
            import asyncio
            self.queue = asyncio.Queue()
            self.queue.put_nowait(None)

    async def capture_start(uid, req):
        seen.update(vars(req))
        return "test_task", DoneEmitter()

    monkeypatch.setattr(app.state.harness, "start", capture_start)
    plan = [{"goal": "Read the sources", "check": "Cite two links", "title": "Read sources"}]
    body = {"message": "Research a topic", "team": {"preset": "full", "plan_mode": "ask"},
            "teacher_enabled": False, "teacher_model": "deepseek/deepseek-v4-pro-0813",
            "approved_plan": plan, "request_id": "stable-request-1", "continue_task": "prior_task", "confirm": True}
    response = await client.post("/api/chat", json=body)
    assert response.status_code == 200
    for key in ("team", "teacher_enabled", "teacher_model", "approved_plan", "request_id", "continue_task", "confirm"):
        assert seen[key] == body[key]


@pytest.mark.parametrize("patch", [
    {"request_id": "../invalid"}, {"request_id": "x" * 129}, {"team": "full"},
    {"approved_plan": [{"goal": "step"}] * 13}, {"teacher_model": "x" * 201},
])
async def test_invalid_team_request_is_rejected_before_a_run(team_client, patch):
    client, _ = team_client
    response = await client.post("/api/chat", json={"message": "Hello", **patch})
    assert response.status_code == 422


async def test_signed_browser_cookie_survives_reload_and_rejects_tampering(team_client, monkeypatch):
    client, _ = team_client
    monkeypatch.setattr(settings, "dev_mode", False)
    first = (await client.get("/api/bootstrap")).json()["user"]["id"]
    signed = client.cookies.get("uid")
    assert signed.startswith(first + ".") and len(signed.split(".")[1]) == 64
    assert (await client.get("/api/bootstrap")).json()["user"]["id"] == first
    client.cookies.clear()
    client.cookies.set("uid", signed[:-1] + ("a" if signed[-1] != "a" else "b"))
    second = (await client.get("/api/bootstrap")).json()["user"]["id"]
    assert second != first
    client.cookies.clear()
    client.cookies.set("uid", first)
    assert (await client.get("/api/bootstrap")).json()["user"]["id"] != first


async def test_user_header_only_works_in_development(team_client, monkeypatch):
    client, _ = team_client
    monkeypatch.setattr(settings, "dev_mode", False)
    actual = (await client.get("/api/bootstrap", headers={"x-user-id": "u_victim"})).json()["user"]["id"]
    assert actual != "u_victim"


async def test_invalid_continuation_returns_a_useful_client_error(team_client):
    client, _ = team_client
    response = await client.post("/api/chat", json={"message": "continue", "continue_task": "t_missing"})
    assert response.status_code == 400 and "paused" in response.json()["detail"]


async def test_estimate_honors_team_cap_and_task_intent(team_client):
    client, _ = team_client
    headers = {"x-user-id": "u_team_cap"}
    await client.post("/api/dev/plan", json={"plan": "pro"}, headers=headers)
    response = await client.post("/api/estimate", json={"message": "Create a document about photosynthesis", "mode": "auto", "max_credits": 100,
        "team": {"preset": "balanced", "max_credits": 7, "architects": ["document"]}}, headers=headers)
    assert response.status_code == 200
    estimate = response.json()
    assert estimate["cap"] == estimate["max_cap"] == 7
    assert any("architect" in part["name"] for part in estimate["parts"])
