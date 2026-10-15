"""Regression checks for user controls, bounded calls and retry isolation."""
import asyncio
from decimal import Decimal

import pytest

from app import catalog, modes, wallet
from app.harness import Emitter, LimitReached, RunContext, RunRequest, UserError, parse_json


async def run(harness, **kwargs):
    tid, emitter = await harness.start("controls", RunRequest(**kwargs))
    events = [event async for event in emitter.stream()]
    await harness.drain()
    return tid, events


def context(harness, db, cap=20):
    user = harness.get_user("controls")
    task = {"id": "manual", "max_credits": cap}
    return RunContext(harness, user, task, RunRequest(message="Explain gravity", mode="normal"),
                      modes.get(db, "normal"), Emitter(db, "manual"))


def test_json_object_parser_handles_escaped_quotes():
    assert parse_json('prefix {"goal":"a \\\"quoted\\\" {value}","ok":true} suffix')["ok"] is True
    with pytest.raises(ValueError):
        parse_json('[1,2,3]')


async def test_teacher_off_uses_direct_style(harness, fake):
    _, events = await run(harness, message="Explain gravity", mode="normal", teacher_enabled=False)
    assert events[-1]["status"] == "done"
    prompt = fake.requests[0]["messages"][0]["content"]
    assert "precise, helpful assistant" in prompt
    assert "patient tutor" not in prompt
    assert not any(e.get("agent") == "teacher" for e in events)


async def test_selected_teacher_runs_once_and_is_billed(harness, db):
    model = "anthropic/claude-haiku-5.5"
    tid, events = await run(harness, message="Explain gravity", mode="normal", teacher_model=model)
    assert events[-1]["status"] == "done"
    assert db.scalar("SELECT COUNT(*) FROM usage_events WHERE task_id=? AND role='teacher'", (tid,)) == 1
    assert wallet.ledger_mismatches(db) == []


async def test_disabled_teacher_does_not_resolve_unavailable_model(harness):
    _, events = await run(harness, message="hello", mode="fast", teacher_enabled=False, teacher_model="missing/model")
    assert events[-1]["status"] == "done"


async def test_paid_teacher_cannot_bypass_plan(harness):
    _, events = await run(harness, message="hello", mode="fast", teacher_model="anthropic/claude-opus-5.5")
    assert events[-1]["status"] == "error"
    assert any("higher plan" in e.get("text", "") for e in events)


async def test_parallel_calls_reserve_shared_credit_budget(harness, db, fake):
    ctx = context(harness, db, cap=1)
    model = catalog.get(db, "anthropic/claude-haiku-5.5")
    fake.delay = 0.05
    messages = [{"role": "user", "content": "Explain gravity"}]
    results = await ctx.parallel([ctx.call("answer", model, messages, max_tokens=4000) for _ in range(3)])
    assert sum(isinstance(r, LimitReached) for r in results) == 2
    assert len(fake.requests) == 1
    assert ctx.reserved_usd == Decimal(0)


async def test_budget_flag_cannot_bypass_cap(harness, db, fake):
    ctx = context(harness, db, cap=0)
    with pytest.raises(LimitReached):
        await ctx.call("checker", ctx.quick(), [{"role": "user", "content": "repair"}], max_tokens=500, budget_check=False)
    assert not fake.requests


async def test_agent_timeout_releases_reservation(harness, db, fake):
    ctx = context(harness, db)
    fake.delay = 0.2
    with pytest.raises(asyncio.TimeoutError):
        await ctx.call("planner", ctx.quick(), [{"role": "user", "content": "plan"}], max_tokens=100,
                       agent_id="planner", agent_timeout_s=0.01)
    assert ctx.reserved_usd == 0 and ctx.agent_reserved["planner"] == 0


async def test_duplicate_request_replays_without_another_charge(harness, db, fake):
    args = dict(message="hello", mode="fast", request_id="retry-once")
    first, events = await run(harness, **args)
    calls = len(fake.requests)
    second, replay = await run(harness, **args)
    assert first == second and replay == events
    assert len(fake.requests) == calls
    assert db.scalar("SELECT COUNT(*) FROM messages WHERE role='user'") == 1
    with pytest.raises(UserError, match="different message"):
        await harness.start("controls", RunRequest(**{**args, "message": "different"}))


async def test_resume_rejects_unowned_task(harness, db):
    db.run("INSERT INTO tasks(id,user_id,status,conversation_id) VALUES('someone-elses','other','paused','c_other')")
    with pytest.raises(UserError, match="own paused"):
        await harness.start("controls", RunRequest(message="Continue", continue_task="someone-elses"))


async def test_school_private_setting_applies_to_learning(harness, db, fake):
    harness.get_user("controls")
    db.run("UPDATE users SET plan='school',private_route=0 WHERE id='controls'")
    wallet.add(db, "controls", 1000, "test")
    _, events = await run(harness, message="hello", mode="fast", private_route=False)
    assert events[-1]["status"] == "done"
    assert len(fake.requests) >= 2  # answer and background profile update
    for request in fake.requests:
        assert request["provider"]["zdr"] is True


async def test_reasoning_event_never_exposes_raw_notes(harness, db):
    harness.get_user("controls")
    db.run("UPDATE users SET plan='student' WHERE id='controls'")
    wallet.add(db, "controls", 1000, "test")
    _, events = await run(harness, message="Explain gravity", mode="think_again", rounds=1, confirm=True)
    thinking = [e for e in events if e["type"] == "thinking"]
    assert thinking and all("considered the task" in e["summary"] for e in thinking)


async def test_resume_preserves_private_setting_and_cannot_run_twice(harness, db, fake):
    harness.get_user("controls")
    db.run("UPDATE users SET plan='student' WHERE id='controls'")
    wallet.add(db, "controls", 1000, "test")
    tid, events = await run(harness, message="Compare savings options", mode="deep", confirm=True,
                            private_route=True, team={"plan_mode": "ask", "researchers": {"count": 0}})
    plan = next(e["plan"] for e in events if e.get("kind") == "approve_plan")
    req = RunRequest(message="Continue", continue_task=tid, approved_plan=plan, extra_credits=100)
    child, emitter = await harness.start("controls", req)
    assert req.private_route is True and req.message == "Compare savings options"
    with pytest.raises(UserError):
        await harness.start("controls", RunRequest(message="Continue", continue_task=tid, approved_plan=plan))
    resumed = [e async for e in emitter.stream()]
    await harness.drain()
    assert resumed[-1]["status"] == "done"
    assert db.one("SELECT status FROM tasks WHERE id=?", (tid,))["status"] == "continued"
    assert db.one("SELECT status FROM tasks WHERE id=?", (child,))["status"] == "done"


def test_restart_reconciles_held_credits_without_new_calls(harness, db, fake):
    harness.get_user("controls")
    db.run("INSERT INTO tasks(id,user_id,status,max_credits,credits_used,state,config) "
           "VALUES('interrupted','controls','running',20,2,?, '{}')", ('{"steps":[{"title":"Answer","kind":"answer"}],"results":[]}',))
    wallet.hold(db, "controls", "interrupted", 20)
    assert harness.recover_interrupted() == 1
    assert wallet.held(db, "controls") == 0 and wallet.balance(db, "controls") == 98
    assert db.one("SELECT status FROM tasks WHERE id='interrupted'")["status"] == "paused"
    assert db.scalar("SELECT COUNT(*) FROM run_events WHERE task_id='interrupted' AND type='run_done'") == 1
    assert harness.recover_interrupted() == 0
    assert not fake.requests


def test_auto_greeting_skips_full_team_and_fast_preset_skips_planning(harness):
    greeting = RunRequest(message="hello", team={"preset": "full"})
    assert harness.choose_mode(greeting, harness.route_rules(greeting), "pro")["id"] == "fast"
    fast = RunRequest(message="Design a complete plan for a Python application", team={"preset": "fast"})
    assert harness.choose_mode(fast, harness.route_rules(fast), "pro")["id"] == "fast"
    explicit = RunRequest(message="Explain gravity", mode="normal", team={"preset": "full"})
    assert harness.choose_mode(explicit, harness.route_rules(explicit), "pro")["id"] == "normal"


async def test_plan_approval_only_uses_remaining_budget(harness, db):
    harness.get_user("controls")
    db.run("UPDATE users SET plan='student' WHERE id='controls'")
    wallet.add(db, "controls", 1000, "test")
    tid, events = await run(harness, message="Compare savings options", mode="deep", confirm=True, max_credits=30,
                            team={"plan_mode": "ask", "researchers": {"count": 0}})
    plan = next(e["plan"] for e in events if e.get("kind") == "approve_plan")
    before = db.one("SELECT * FROM tasks WHERE id=?", (tid,))
    child, resumed = await run(harness, message="Continue", continue_task=tid, approved_plan=plan, extra_credits=100)
    after = db.one("SELECT * FROM tasks WHERE id=?", (child,))
    assert after["max_credits"] == 30 - before["credits_used"]
    assert before["credits_used"] + after["credits_used"] <= 30
    assert db.scalar("SELECT COUNT(*) FROM messages WHERE role='user'") == 1


async def test_simultaneous_send_retries_share_one_run(harness, db, fake):
    fake.delay = 0.01
    requests = [RunRequest(message="hello", mode="fast", request_id="same-live-request") for _ in range(3)]
    started = await asyncio.gather(*(harness.start("controls", request) for request in requests))
    async def collect(emitter):
        return [event async for event in emitter.stream()]
    events = await asyncio.gather(*(collect(emitter) for _, emitter in started))
    await harness.drain()
    assert len({task for task, _ in started}) == 1
    assert events[0] == events[1] == events[2]
    assert db.scalar("SELECT COUNT(*) FROM tasks") == 1
    assert wallet.balance(db, "controls") == 99


async def test_copied_inputs_expire_with_original_upload(harness, db):
    from app import workspace
    harness.get_user("controls")
    folder = workspace.task_dir("controls", "uploads")
    source = folder / "inputs" / "abc123_notes.txt"
    source.write_text("Notes about photosynthesis.")
    rec = workspace.register(db, "controls", "uploads", source, "txt", "free")
    tid, events = await run(harness, message="summarize notes", mode="fast", uploads=[rec["id"]])
    assert events[-1]["status"] == "done"
    rows = db.all("SELECT * FROM workspace_files WHERE user_id='controls'")
    assert len(rows) == 2 and {r["task_id"] for r in rows} == {"uploads",tid}
    paths = [workspace.path_of(row) for row in rows]
    assert all(path.exists() for path in paths)
    db.run("UPDATE workspace_files SET delete_after=0 WHERE user_id='controls'")
    assert workspace.purge_expired(db) == 2
    assert not any(path.exists() for path in paths)


async def test_teacher_cannot_drop_original_code_and_sources(harness, fake, monkeypatch):
    original = fake._reply
    answer = "Here is the code:\n```python\nprint(17 + 23)\n```\nSource: https://example.com/reference"
    def reply(body):
        system = body["messages"][0]["content"]
        if "Rewrite the completed answer" in system:
            return "A shorter answer that accidentally dropped the code and citation."
        if "patient tutor" in system:
            return answer
        return original(body)
    monkeypatch.setattr(fake, "_reply", reply)
    _, events = await run(harness, message="Show the code", mode="normal", teacher_model="anthropic/claude-haiku-5.5")
    final = [e for e in events if e["type"] == "text" and e.get("replace")][-1]["delta"]
    assert final == answer
    assert any(e["type"] == "notice" and "original answer is preserved" in e["text"] for e in events)
