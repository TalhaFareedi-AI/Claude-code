"""Behavioral coverage for the configurable team, approval and durable progress."""
import asyncio
import copy
import json

import pytest

from app import team, wallet, workspace
from app.db import jload
from app.harness import Emitter, LimitReached, RunContext, RunRequest, UserError
from app.openrouter import LLMResult, Usage
from app import modes
from test_harness import answer_text, go, last


def pro(harness, db, user="u_team"):
    harness.get_user(user)
    db.run("UPDATE users SET plan='pro', auto_spend=200 WHERE id=?", (user,))
    wallet.add(db, user, 2000, "test")
    return user


def short_plan():
    return [{"title": "Investigate", "kind": "think", "goal": "Find the required facts", "check": "Facts address the question"},
            {"title": "Answer", "kind": "answer", "goal": "Answer the user", "check": "All requested parts covered"}]


def reply_with_plan(fake, monkeypatch, steps=None):
    original = fake._reply
    def reply(body):
        system = body["messages"][0]["content"]
        if "bounded agent team" in system:
            return json.dumps({"steps": steps or short_plan()})
        return original(body)
    monkeypatch.setattr(fake, "_reply", reply)


@pytest.mark.parametrize("raw", [[], {"preset": []}, {"plan_mode": []}, {"plan_depth": {}},
    {"planners": {"count": True}}, {"planners": {"count": 4}}, {"researchers": {"count": 6}},
    {"researchers": {"engine": []}}, {"planners": {"effort": []}}, {"architects": [["ui"]]},
    {"architects": ["ui", "ui"]}, {"checker": {"timeout_s": 0}}, {"builder": {"max_credits": -1}},
    {"planners": {"agents": ["invalid"]}}, {"researchers": {"agents": [{"max_searches_each": 11}]}}])
def test_invalid_team_profiles_are_user_errors(raw):
    with pytest.raises(UserError):
        team.normalize_team(raw)


def test_presets_and_individual_settings_are_independent():
    raw = {"preset": "full", "planners": {"models": [None, "", "qwen/qwen3.8-flash"],
           "agents": [None, {"effort": "high"}]}, "researchers": {"agents": [{"engine": "exa"}, {"engine": "parallel"}]}}
    original = copy.deepcopy(raw)
    cfg = team.normalize_team(raw)
    assert cfg["planners"]["count"] == 3 and cfg["plan_depth"] == "deep"
    assert cfg["planners"]["agents"][1]["effort"] == "high"
    assert cfg["researchers"]["agents"][0]["engine"] == "exa"
    cfg["architects"].clear()
    assert raw == original and len(team.PRESETS["full"]["architects"]) == 4
    assert team.normalize_team({"preset": "fast"})["planners"]["count"] == 0


async def test_ask_plan_pauses_before_builder_and_edit_is_used_on_resume(harness, db, fake, monkeypatch, tmp_path):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    tid, events = await go(harness, user, message="Design a reliable calculator", mode="deep", confirm=True,
                           team={"plan_mode": "ask", "architects": ["code"]}, teacher_enabled=False)
    assert last(events, "run_done")["status"] == "paused"
    approval = last(events, "ask")
    assert approval["kind"] == "approve_plan"
    assert all(s["goal"] and s["check"] for s in approval["plan"])
    assert not any(e["type"] == "agent_start" and e["agent"] in ("builder", "architect_code") for e in events)
    saved = jload(db.one("SELECT state FROM tasks WHERE id=?", (tid,))["state"])
    assert saved["awaiting_plan_approval"] and saved["results"] == []
    edited = short_plan()
    edited[0]["goal"] = "Check division by zero and Unicode digits"
    child, events2 = await go(harness, user, message="continue", continue_task=tid, approved_plan=edited,
                              extra_credits=150)
    assert last(events2, "run_done")["status"] == "done"
    assert not [e for e in events2 if e["type"] == "ask" and e["kind"] == "approve_plan"]
    assert any(e["type"] == "agent_start" and e["agent"] == "architect_code" for e in events2)
    assert fake.calls("Check division by zero and Unicode digits")
    blueprint = db.one("SELECT * FROM workspace_files WHERE task_id=? AND name='blueprint-code.md'", (child,))
    assert workspace.path_of(blueprint).read_text()
    todo = next((tmp_path / "ws" / user).glob(child + "_*/todo.md")).read_text()
    assert "[ ]" not in todo
    assert wallet.held(db, user) == 0 and wallet.ledger_mismatches(db) == []


async def test_parallel_planners_survive_independent_failure_then_judge(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    original = team.agent_json
    active = 0
    peak = 0
    async def fail_one(ctx, name, *args, **kwargs):
        nonlocal active, peak
        if name.startswith("planner"):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
        if name == "planner2":
            raise UserError("This planner is unavailable")
        return await original(ctx, name, *args, **kwargs)
    monkeypatch.setattr(team, "agent_json", fail_one)
    _, events = await go(harness, user, message="Plan a careful comparison", mode="deep", confirm=True,
                         team={"planners": {"count": 3}, "plan_depth": "light"}, teacher_enabled=False)
    assert last(events, "run_done")["status"] == "done" and peak == 3
    assert any(e["type"] == "agent_start" and e["agent"] == "plan_judge" for e in events)
    assert any(e["type"] == "notice" and "planner(s) failed" in e["text"] for e in events)


async def test_failed_step_has_two_repairs_then_replans_remaining_work(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    checked = 0
    async def fail_step(ctx, step, result):
        nonlocal checked
        checked += 1
        return {"ok": False, "problem": "The acceptance criterion was not met"}
    monkeypatch.setattr(team, "check_step", fail_step)
    _, events = await go(harness, user, message="Design a clear explanation", mode="deep", confirm=True,
                         team={"plan_depth": "normal"}, teacher_enabled=False)
    assert last(events, "run_done")["status"] == "done"
    assert checked <= 3 * 7
    assert any(e["type"] == "plan" and e.get("replanned") for e in events)
    assert any(e["type"] == "step_done" and not e["ok"] for e in events)
    assert fake.calls("The latest step failed")


async def test_final_answer_credit_pause_resumes_without_repeating_builder(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    original = team.agent_call
    fail = True
    async def cap_finisher(ctx, name, *args, **kwargs):
        nonlocal fail
        if name == "finisher" and fail:
            fail = False
            raise LimitReached("credits")
        return await original(ctx, name, *args, **kwargs)
    monkeypatch.setattr(team, "agent_call", cap_finisher)
    tid, events = await go(harness, user, message="Design a small answer", mode="deep", confirm=True,
                           teacher_enabled=False, team={"plan_depth": "light"})
    assert last(events, "run_done")["status"] == "paused"
    assert last(events, "ask")["kind"] == "more_credits"
    child, events2 = await go(harness, user, message="continue", continue_task=tid, extra_credits=150)
    assert last(events2, "run_done")["status"] == "done"
    assert not [e for e in events2 if e["type"] == "agent_start" and e["agent"] == "builder"]
    assert db.one("SELECT state FROM tasks WHERE id=?", (child,))["state"]


async def test_disabled_checker_does_not_resolve_its_model(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    _, events = await go(harness, user, message="Design a compact response", mode="deep", confirm=True,
                         team={"checker": {"enabled": False, "model": "unavailable/brain"}}, teacher_enabled=False)
    assert last(events, "run_done")["status"] == "done"
    assert not [e for e in events if e["type"] == "agent_start" and e["agent"] == "checker"]


async def test_research_assignments_engines_and_citations_are_distinct(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    _, events = await go(harness, user, message="Research solar panel efficiency", mode="research", confirm=True,
        tools=["web"], teacher_enabled=False, max_credits=150,
        team={"researchers": {"count": 3, "agents": [{"engine": "exa", "max_searches_each": 1},
              {"engine": "parallel", "max_searches_each": 2}, {"engine": "perplexity", "max_searches_each": 3}]}})
    assert last(events, "run_done")["status"] == "done"
    searches = [r for r in fake.requests if r.get("tools")]
    assert len(searches) == 3
    assert {r["tools"][0]["parameters"]["engine"] for r in searches} == {"exa", "parallel", "perplexity"}
    assert {r["max_tool_calls"] for r in searches} == {1, 2, 3}
    assert len({r["messages"][-1]["content"] for r in searches}) == 3
    assert len([e for e in events if e["type"] == "sources"]) == 3
    assert "example.com" in answer_text(events)


async def test_research_disabled_web_fails_before_paid_calls(harness, db, fake):
    user = pro(harness, db)
    _, events = await go(harness, user, message="Research solar panels", mode="research", confirm=True,
                         tools=[], teacher_enabled=False)
    assert last(events, "run_done")["status"] == "error"
    assert "Web search is turned off" in last(events, "error")["text"]
    assert not fake.requests


async def test_sparse_auto_model_slots_keep_later_explicit_selection(harness, db):
    user = pro(harness, db)
    req = RunRequest(message="Plan", team={"planners": {"count": 3, "models": [None, "", "qwen/qwen3.8-flash"]}})
    task = {"id": "t_slots", "max_credits": 150}
    ctx = RunContext(harness, harness.get_user(user), task, req, modes.get(db, "deep"), Emitter(db, "t_slots"))
    chosen = team.team_models(ctx, "planners", "planner")
    assert len(chosen) == 3 and chosen[2]["id"] == "qwen/qwen3.8-flash"


async def test_agent_card_cost_does_not_include_parallel_siblings(harness, db, monkeypatch):
    user = pro(harness, db)
    req = RunRequest(message="Plan")
    task = {"id": "t_cost", "max_credits": 150}
    ctx = RunContext(harness, harness.get_user(user), task, req, modes.get(db, "deep"), Emitter(db, "t_cost"))
    from decimal import Decimal
    async def call(role, model, messages, **kwargs):
        ctx.agent_usd[role] = Decimal("0.001")
        ctx.meter.credits = 80
        return LLMResult("done", model["id"], Usage())
    monkeypatch.setattr(ctx, "call", call)
    await team.agent_call(ctx, "planner1", ctx.brain("planner"), [], max_tokens=100)
    event = jload(db.one("SELECT data FROM run_events WHERE task_id=? AND type='agent_done'", (task["id"],))["data"])
    assert event["credits"] == 1


async def test_research_credit_pause_keeps_completed_searches_on_resume(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    original = team.agent_call
    first = True
    async def cap(ctx, name, *args, **kwargs):
        nonlocal first
        if name == "finisher" and first:
            first = False
            raise LimitReached("credits")
        return await original(ctx, name, *args, **kwargs)
    monkeypatch.setattr(team, "agent_call", cap)
    tid, events = await go(harness, user, message="Research solar panels", mode="research", tools=["web"],
                           confirm=True, teacher_enabled=False)
    assert last(events, "run_done")["status"] == "paused"
    before = len([r for r in fake.requests if r.get("tools")])
    assert before == 1
    _, resumed = await go(harness, user, message="continue", continue_task=tid, extra_credits=100)
    assert last(resumed, "run_done")["status"] == "done"
    assert len([r for r in fake.requests if r.get("tools")]) == before


async def test_document_credit_pause_reuses_outline_and_finished_sections(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    original = team.agent_json
    first = True
    async def cap(ctx, name, model, messages, **kwargs):
        nonlocal first
        if name == "builder" and "Write one section" in messages[0]["content"] and first:
            first = False
            raise LimitReached("credits")
        return await original(ctx, name, model, messages, **kwargs)
    monkeypatch.setattr(team, "agent_json", cap)
    tid, events = await go(harness, user, message="Write a document about solar power with five sections", intent="make_doc",
        mode="deep", confirm=True, teacher_enabled=False, team={"preset": "fast"})
    assert last(events, "run_done")["status"] == "paused"
    before = len(fake.calls("Write one section"))
    assert before == 4
    _, resumed = await go(harness, user, message="continue", continue_task=tid, extra_credits=150)
    assert last(resumed, "run_done")["status"] == "done"
    assert len(fake.calls("outline for a document")) == 1
    assert len(fake.calls("Write one section")) == before + 1
    assert last(resumed, "file_created")["file"]["name"].endswith(".docx")


async def test_final_checker_failure_preserves_completed_answer(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    original = team.agent_json
    async def unavailable(ctx, name, *args, **kwargs):
        if name == "checker":
            raise UserError("Checker service unavailable")
        return await original(ctx, name, *args, **kwargs)
    async def pass_step(*args):
        return {"ok": True}
    monkeypatch.setattr(team, "agent_json", unavailable)
    monkeypatch.setattr(team, "check_step", pass_step)
    _, events = await go(harness, user, message="Design a concise answer", mode="deep", confirm=True, teacher_enabled=False)
    assert last(events, "run_done")["status"] == "done" and answer_text(events)
    assert any(e["type"] == "notice" and "final checker was unavailable" in e["text"] for e in events)


async def test_disabled_builder_returns_preparation_without_executing(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    _, events = await go(harness, user, message="Design a compact plan", mode="deep", confirm=True,
        team={"builder": {"enabled": False}}, teacher_enabled=False)
    assert last(events, "run_done")["status"] == "done"
    assert "builder is disabled" in answer_text(events)
    assert not [e for e in events if e["type"] == "agent_start" and e["agent"] == "builder"]


@pytest.mark.parametrize("invalid", [{"plan": short_plan()}, {"steps": [*short_plan()] * 5},
                                     {"steps": [{"kind": "answer"}]}])
async def test_planner_repairs_valid_json_with_invalid_step_schema(harness, db, fake, monkeypatch, invalid):
    user = pro(harness, db)
    original = fake._reply
    planning_calls = 0
    def reply(body):
        nonlocal planning_calls
        if "bounded agent team" in body["messages"][0]["content"]:
            planning_calls += 1
            return json.dumps(invalid if planning_calls == 1 else {"steps": short_plan()})
        return original(body)
    monkeypatch.setattr(fake, "_reply", reply)
    _, events = await go(harness, user, message="Design a useful answer", mode="deep", confirm=True,
                         team={"plan_depth": "light"}, teacher_enabled=False)
    assert last(events, "run_done")["status"] == "done" and planning_calls == 2
    assert fake.calls("Validation error:")


async def test_planner_semantic_repairs_are_bounded(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    original = fake._reply
    planning_calls = 0
    def reply(body):
        nonlocal planning_calls
        if "bounded agent team" in body["messages"][0]["content"]:
            planning_calls += 1
            return json.dumps({"steps": []})
        return original(body)
    monkeypatch.setattr(fake, "_reply", reply)
    _, events = await go(harness, user, message="Design a useful answer", mode="deep", confirm=True,
                         team={"plan_depth": "light"}, teacher_enabled=False)
    assert last(events, "run_done")["status"] == "error" and planning_calls == 2
    assert "No planner produced a usable plan" in last(events, "error")["text"]


async def test_checker_sees_validated_artifact_contents_and_resolved_calculations(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    planned = [{"title": "Draw the water cycle", "kind": "diagram", "goal": "Show sun in a diagram", "check": "The Sun label is visible"},
               {"title": "Answer", "kind": "answer", "goal": "Explain the interest calculation", "check": "Numbers and diagram are correct"}]
    reply_with_plan(fake, monkeypatch, planned)
    _, events = await go(harness, user, message="Draw a diagram and calculate interest", mode="deep", confirm=True,
        team={"plan_depth": "light"}, teacher_enabled=False)
    assert last(events, "run_done")["status"] == "done"
    checks = [r for r in fake.requests if "strict checker" in r["messages"][0]["content"]]
    assert checks and "<svg" in checks[0]["messages"][-1]["content"] and "Sun" in checks[0]["messages"][-1]["content"]
    assert all("{{calc:" not in r["messages"][-1]["content"] for r in checks)
