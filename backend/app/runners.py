"""One runner per mode (section 3). Each is a small agent loop with the three safety stops:
a step limit, a credit limit, and a time limit. Every AI call goes through ctx.call (the meter).

A role is a slot for a brain. A mode is a list of roles, so one chain can use a different brain at every step.
"""
import asyncio
import re

from . import prompts, skills, workspace
from .config import settings
from .db import jdump, jload, now
from .harness import LimitReached, RunContext, RunResult, RunStopped, UserError, parse_json, tokens_of
from .openrouter import OpenRouterError
from .postprocess import NEXT, build_chart, new_artifact, svg_artifact
from .tools import calc as calc_tool, diagram, docx_builder, pptx_builder
from . import charts

RUNNERS: dict = {}


def runner(name):
    def deco(fn):
        RUNNERS[name] = fn
        return fn
    return deco


def strip_next(text: str) -> str:
    return NEXT.sub("", text).strip()


def mt(ctx: RunContext, role: str) -> int:
    return ctx.mode["max_tokens"].get(role, 1500)


def step(ctx: RunContext, n: int, title: str, **kw) -> None:
    ctx.emit("step_start", step=n, title=title[:60], **kw)


def step_done(ctx: RunContext, n: int, ok: bool = True, **kw) -> None:
    ctx.emit("step_done", step=n, ok=ok, **kw)


# ======================================================================= Fast / Normal
@runner("single")
async def run_single(ctx: RunContext) -> RunResult:
    model = ctx.brain("answer")
    step(ctx, 1, "Answering with " + model["name"])
    brief = "Fast mode: answer in at most 90 words. One idea, one tiny example." if ctx.mode["id"] == "fast" else ""
    res = await ctx.call("answer", model, ctx.base_messages(brief), max_tokens=mt(ctx, "answer"),
                         effort=ctx.effort("answer"), stream=True)
    if not res.text.strip():  # a host sent nothing: one plain retry, thinking off
        res = await ctx.call("answer", model, ctx.base_messages(), max_tokens=mt(ctx, "answer"), effort="off")
        ctx.emit_text(res.text)
        step_done(ctx, 1)
        return RunResult(res.text)
    step_done(ctx, 1)
    return RunResult(res.text, streamed=True)


# ======================================================================= Think Again
@runner("think_again")
async def run_think_again(ctx: RunContext) -> RunResult:
    writer, critic = ctx.brain("write"), ctx.brain("critic")
    p = ctx.mode["params"]
    rounds = ctx.rounds or p["default_rounds"]
    stop_score = p["stop_score"]
    step(ctx, 1, f"Writing a first draft with {writer['name']}")
    msgs = ctx.base_messages()
    res = await ctx.call("write", writer, msgs, max_tokens=mt(ctx, "write"), effort=ctx.effort("write"))
    answer = res.text
    ctx.best = strip_next(answer)
    step_done(ctx, 1)
    n = 1
    try:
        for r in range(1, rounds + 1):
            n += 1
            step(ctx, n, f"Round {r}: {critic['name']} marks the answer")
            review = await ctx.json_call("critic", critic, [
                {"role": "system", "content": prompts.get("critic")},
                {"role": "user", "content": f"Question:\n{ctx.req.message[:3000]}\n\nAnswer:\n{answer[:6000]}"}],
                max_tokens=mt(ctx, "critic"), effort=ctx.effort("critic"))
            score = _score(review.get("score"))
            problems = [str(x)[:200] for x in (review.get("problems") or [])][:4]
            step_done(ctx, n, score=score, detail="; ".join(problems))
            ctx.emit("round", round=r, score=score, problems=problems)
            if score >= stop_score:  # stop 2: good enough
                break
            n += 1
            step(ctx, n, f"Round {r}: rewriting")
            fix_msgs = [{"role": "system", "content": ctx.system_prompt() + "\n\n" + prompts.get("rewrite")},
                        {"role": "user", "content": f"Question:\n{ctx.req.message[:3000]}\n\nAnswer:\n{answer[:6000]}\n\n"
                                                    "Problems:\n- " + "\n- ".join(problems or ["Make it simpler and more correct."])}]
            res = await ctx.call("rewrite", writer, fix_msgs, max_tokens=mt(ctx, "write"), effort=ctx.effort("write"))
            answer = res.text
            ctx.best = strip_next(answer)
            step_done(ctx, n)
    except LimitReached as e:  # stop 1: money (or time). Keep the best answer so far.
        ctx.notices.append("Stopped early at the " + ("credit" if e.kind == "credits" else "time") + " limit. This is the best answer so far.")
        ctx.emit("notice", text=ctx.notices[-1])
    return RunResult(answer)


def _score(v) -> int:
    try:
        return max(1, min(10, int(float(v))))
    except (TypeError, ValueError):
        return 5


# ======================================================================= Overthink
def candidate(text: str) -> str:
    return re.sub(r"```(chart|svg|quiz).*?```", "", strip_next(text), flags=re.S).strip()[:7000]


@runner("overthink")
async def run_overthink(ctx: RunContext) -> RunResult:
    think, judge = ctx.brain("think"), ctx.brain("judge")
    want = ctx.tries or ctx.mode["params"]["default_tries"]
    msgs = ctx.base_messages()
    # Only start as many tries as the credit cap can pay for.
    n = want
    while n > 1:
        try:
            ctx.check_budget([(think, msgs, mt(ctx, "think"))] * n + [(judge, msgs, mt(ctx, "judge"))])
            break
        except LimitReached:
            n -= 1
    if n < want:
        ctx.notices.append(f"I ran {n} tries instead of {want} to stay inside your cost cap.")
        ctx.emit("notice", text=ctx.notices[-1])
    step(ctx, 1, f"{n} long-thinking tries with {think['name']}")
    results = await ctx.parallel([ctx.call(f"think{i+1}", think, msgs, max_tokens=mt(ctx, "think"),
                                           effort=ctx.effort("think"), budget_check=False) for i in range(n)])
    good = [r for r in results if not isinstance(r, Exception) and r.text.strip()]
    if not good:
        err = next((r for r in results if isinstance(r, Exception)), None)
        raise err or UserError("The tries came back empty. Lower the effort and try again.")
    step_done(ctx, 1, detail=f"{len(good)} of {n} tries finished")
    ctx.best = strip_next(good[0].text)
    if len(good) == 1:
        return RunResult(good[0].text)
    step(ctx, 2, f"{judge['name']} compares the tries")
    labels = "ABCDE"
    body = "\n\n".join(f"Answer {labels[i]}:\n{candidate(r.text)}" for i, r in enumerate(good))
    res = await ctx.call("judge", judge, [
        {"role": "system", "content": ctx.system_prompt() + "\n\n" + prompts.get("judge")},
        {"role": "user", "content": f"Question:\n{ctx.req.message[:3000]}\n\n{body}"}],
        max_tokens=mt(ctx, "judge"), effort=ctx.effort("judge"), stream=True)
    step_done(ctx, 2)
    return RunResult(res.text, streamed=True)


# ======================================================================= Council
@runner("council")
async def run_council(ctx: RunContext) -> RunResult:
    members, judge = ctx.brains("members"), ctx.brain("judge")
    p = ctx.mode["params"]
    members = members[: p["max_members"]]
    if len(members) < 2:
        raise UserError("A council needs at least 2 different brains.")
    msgs = ctx.base_messages()
    step(ctx, 1, "Council: " + ", ".join(m["name"] for m in members))
    results = await ctx.parallel([ctx.call(f"member{i+1}", m, msgs, max_tokens=mt(ctx, "members"),
                                           effort=ctx.effort("members")) for i, m in enumerate(members)])
    ok = [(m, r) for m, r in zip(members, results) if not isinstance(r, Exception) and r.text.strip()]
    if not ok:
        raise next((r for r in results if isinstance(r, Exception)), UserError("No council member answered."))
    step_done(ctx, 1, detail=f"{len(ok)} of {len(members)} answered")
    ctx.best = strip_next(ok[0][1].text)
    if len(ok) == 1:
        return RunResult(ok[0][1].text)
    step(ctx, 2, f"{judge['name']} merges the answers")
    body = "\n\n".join(f"Answer {'ABCDE'[i]} ({m['name']}):\n{candidate(r.text)}" for i, (m, r) in enumerate(ok))
    res = await ctx.call("judge", judge, [
        {"role": "system", "content": ctx.system_prompt() + "\n\n" + prompts.get("judge") +
         "\nAlways add a short 'Where they agreed and disagreed' section."},
        {"role": "user", "content": f"Question:\n{ctx.req.message[:3000]}\n\n{body}"}],
        max_tokens=mt(ctx, "judge"), effort=ctx.effort("judge"), stream=True)
    step_done(ctx, 2)
    return RunResult(res.text, streamed=True)


# ======================================================================= Two Brains / Think Team
def _notes_text(res_text: str, cap_tokens: int) -> str:
    """Keep the notes, not the scrap paper: parse the JSON, re-dump, and cap its length."""
    try:
        notes = parse_json(res_text)
        text = jdump(notes)
    except ValueError:
        text = res_text.strip()
    return text[: int(cap_tokens * 3.5)]


async def _think_notes(ctx: RunContext, role: str, model: dict, cap: int, label: str):
    sys = prompts.render("notes", notes_tokens=cap)
    msgs = [{"role": "system", "content": sys + "\n\n" + (ctx.context_block() or "")},
            *ctx.history_messages(), {"role": "user", "content": ctx.user_content()}]
    max_t = mt(ctx, role)
    res = await ctx.call(label, model, msgs, max_tokens=max_t, effort=ctx.effort(role))
    notes = _notes_text(res.text, cap)
    if not notes.strip():  # thinker ran out of room: retry once at lower effort
        res = await ctx.call(label, model, msgs, max_tokens=int(max_t * 1.3), effort="low", budget_check=False)
        notes = _notes_text(res.text, cap)
    return notes


async def _answer_from_notes(ctx: RunContext, who: str, notes_block: str) -> RunResult:
    answerer = ctx.brain("answer")
    sys = ctx.system_prompt() + "\n\n" + prompts.render("answerer", who=who)
    ctx_block = ctx.context_block()
    msgs = [{"role": "system", "content": sys + ("\n\n" + ctx_block if ctx_block else "")}, *ctx.history_messages(),
            {"role": "user", "content": f"{ctx.user_content()}\n\n<notes>\n{notes_block}\n</notes>"}]
    res = await ctx.call("answer", answerer, msgs, max_tokens=mt(ctx, "answer"), effort=ctx.effort("answer"), stream=True)
    return RunResult(res.text, streamed=True)


@runner("two_brains")
async def run_two_brains(ctx: RunContext) -> RunResult:
    thinker, answerer = ctx.brain("think"), ctx.brain("answer")
    cap = ctx.mode["params"]["notes_max_tokens"]
    step(ctx, 1, f"Thinking with {thinker['name']}")
    notes = await _think_notes(ctx, "think", thinker, cap, "think")
    step_done(ctx, 1, detail=notes[:300])
    if not notes.strip():  # let one brain do both steps
        ctx.notices.append("The thinker sent no notes, so the answerer worked alone.")
        ctx.emit("notice", text=ctx.notices[-1])
        notes = "(no notes)"
    step(ctx, 2, f"Writing the answer with {answerer['name']}")
    out = await _answer_from_notes(ctx, thinker["name"], notes)
    step_done(ctx, 2)
    return out


@runner("think_team")
async def run_think_team(ctx: RunContext) -> RunResult:
    thinkers = ctx.brains("think")[: ctx.mode["params"]["max_thinkers"]]
    if len(thinkers) < 2:
        raise UserError("Think Team needs at least 2 thinkers. Pick another brain, or use Two Brains.")
    cap = ctx.mode["params"]["notes_max_tokens"]
    step(ctx, 1, "Thinking: " + ", ".join(t["name"] for t in thinkers))
    results = await ctx.parallel([_think_notes(ctx, "think", t, cap, f"think{i+1}") for i, t in enumerate(thinkers)])
    ok = [(t, r) for t, r in zip(thinkers, results) if not isinstance(r, Exception) and r.strip()]
    failed = len(thinkers) - len(ok)
    step_done(ctx, 1, detail=f"{len(ok)} of {len(thinkers)} thinkers sent notes")
    if failed:
        ctx.notices.append(f"{failed} thinker(s) failed, so the team carried on with {len(ok)}.")
        ctx.emit("notice", text=ctx.notices[-1])
    if not ok:
        raise next((r for r in results if isinstance(r, Exception)), UserError("No thinker sent notes."))
    if len(ok) < 2:
        ctx.notices.append("Fewer than 2 thinkers were left, so this ran as Two Brains.")
    block = "\n\n".join(f"Notes from {t['name']}:\n{n}" for t, n in ok)
    step(ctx, 2, f"Writing the answer with {ctx.brain('answer')['name']}")
    out = await _answer_from_notes(ctx, "a team of thinkers", block)
    step_done(ctx, 2)
    return out


# ======================================================================= Research
@runner("research")
async def run_research(ctx: RunContext) -> RunResult:
    planner, searcher, writer = ctx.brain("planner"), ctx.brain("search"), ctx.brain("writer")
    n = ctx.mode["params"]["max_searches"]
    step(ctx, 1, "Planning search questions")
    plan = await ctx.json_call("planner", planner, [
        {"role": "system", "content": prompts.render("research_plan", n=n)},
        {"role": "user", "content": ctx.req.message[:1500]}], max_tokens=mt(ctx, "planner"))
    queries = [str(q)[:200] for q in (plan.get("queries") or [])][:n] or [ctx.req.message[:200]]
    step_done(ctx, 1, detail="\n".join(queries))
    step(ctx, 2, f"Searching the web ({len(queries)} searches)")
    ctx.emit("tool_start", step=2, tool="web_search", title=f"{len(queries)} web searches")
    plugins = [{"id": "web", "max_results": 3}]
    results = await ctx.parallel([ctx.call(f"search{i+1}", searcher, [
        {"role": "system", "content": prompts.get("research_search")}, {"role": "user", "content": q}],
        max_tokens=mt(ctx, "search"), effort=ctx.effort("search"), plugins=plugins, extra_usd=0.007)
        for i, q in enumerate(queries)])
    found = [(q, r) for q, r in zip(queries, results) if not isinstance(r, Exception) and r.text.strip()]
    if not found:
        raise next((r for r in results if isinstance(r, Exception)), UserError("The searches found nothing."))
    ctx.emit("tool_result", step=2, tool="web_search", ok=True, summary=f"{len(found)} searches finished",
             cost=ctx.meter.credits)
    step_done(ctx, 2)
    blocks = []
    for q, r in found:
        srcs = "\n".join(f"- {s['title'] or s['url']}: {s['url']}" for s in r.sources[:5])
        blocks.append(f"<search q=\"{q}\">\n{r.text[:1800]}\n{('Sources:' + chr(10) + srcs) if srcs else ''}\n</search>")
    step(ctx, 3, f"Writing the answer with {writer['name']}")
    sys = ctx.system_prompt() + "\n\n" + prompts.get("research_write")
    ctx_block = ctx.context_block()
    res = await ctx.call("writer", writer, [
        {"role": "system", "content": sys + ("\n\n" + ctx_block if ctx_block else "")},
        {"role": "user", "content": ctx.user_content() + "\n\n" + "\n\n".join(blocks)}],
        max_tokens=mt(ctx, "writer"), effort=ctx.effort("writer"), stream=True)
    step_done(ctx, 3)
    return RunResult(res.text, streamed=True)


# ======================================================================= Deep + Developer
async def pick_skill(ctx: RunContext) -> skills.Skill | None:
    enabled = ctx.req.skills
    hdr = skills.headers(enabled)
    if not hdr:
        return None
    name = skills.match_keywords(ctx.req.message, enabled)  # free first guess
    if not name:
        got = await ctx.json_call("skill", ctx.quick(), [
            {"role": "system", "content": prompts.render("skill_pick", headers=hdr)},
            {"role": "user", "content": ctx.req.message[:1200]}], max_tokens=60)
        name = got.get("skill")
    sk = skills.get(name) if name and name != "none" else None
    if sk and (enabled is None or sk.name in enabled):
        return sk
    return None


async def make_plan(ctx: RunContext, skill_text: str, max_steps: int) -> list[dict]:
    planner = ctx.brain("planner")
    tools = ", ".join(t for t in ("calculator", "chart" if "chart" in ctx.req.tools else "", "diagram" if "diagram" in ctx.req.tools else "") if t)
    sys = prompts.render("planner", max_steps=max_steps, tools=tools)
    if skill_text:
        sys += "\n\nFollow this recipe when planning:\n" + skill_text
    got = await ctx.json_call("planner", planner, [{"role": "system", "content": sys},
                                                   {"role": "user", "content": ctx.user_content()[:6000]}],
                              max_tokens=mt(ctx, "planner"), effort=ctx.effort("planner"))
    steps = []
    for s in (got.get("steps") or [])[:max_steps]:
        if not isinstance(s, dict):
            continue
        kind = s.get("kind") if s.get("kind") in ("think", "calculate", "chart", "diagram", "answer") else "think"
        if kind == "chart" and "chart" not in ctx.req.tools:
            kind = "think"
        if kind == "diagram" and "diagram" not in ctx.req.tools:
            kind = "think"
        steps.append({"title": " ".join(str(s.get("title", "Step")).split()[:8]), "kind": kind,
                      "detail": str(s.get("detail", ""))[:300]})
    if not steps or steps[-1]["kind"] != "answer":
        steps = steps[: max_steps - 1] + [{"title": "Write the answer", "kind": "answer", "detail": "Write the final reply."}]
    return steps


def results_block(state: dict, per: int = 1500) -> str:
    return "\n\n".join(f"Step {i+1} ({s['title']}):\n{r[:per]}" for i, (s, r) in enumerate(zip(state["steps"], state["results"])))


@runner("deep")
async def run_deep(ctx: RunContext) -> RunResult:
    p = ctx.mode["params"]
    max_steps = min(int(p.get("max_steps", 8)), settings.max_steps)
    worker = ctx.brain("worker")
    state = None
    if ctx.req.continue_task:
        row = ctx.db.one("SELECT state FROM tasks WHERE id=? AND user_id=?", (ctx.req.continue_task, ctx.user["id"]))
        state = jload(row["state"]) if row else None
    skill = None
    if p.get("skills") and not state:
        skill = await pick_skill(ctx)
        if skill:
            ctx.emit("skill_used", name=skill.name)
    if state is None:
        step(ctx, 0, "Planning")
        steps = await make_plan(ctx, skill.body if skill else "", max_steps)
        state = {"steps": steps, "results": [], "skill": skill.name if skill else None}
        step_done(ctx, 0)
    elif state.get("skill") and skills.get(state["skill"]):
        skill = skills.get(state["skill"])
    ctx.emit("plan", steps=[{"title": s["title"], "kind": s["kind"]} for s in state["steps"]],
             done=len(state["results"]))
    workspace.write_todo(ctx.user["id"], ctx.task["id"], state["steps"], len(state["results"]))
    skill_text = ("\n\nRecipe to follow:\n" + skill.body) if skill else ""
    try:
        for i in range(len(state["results"]), len(state["steps"])):
            ctx.check_stop()
            s = state["steps"][i]
            if s["kind"] == "answer":
                break
            step(ctx, i + 1, s["title"], kind=s["kind"])
            result = await do_step(ctx, worker, s, state, skill_text)
            state["results"].append(result)
            ctx.best = result
            step_done(ctx, i + 1, ok=True, detail=result[:400])
            workspace.write_todo(ctx.user["id"], ctx.task["id"], state["steps"], len(state["results"]))
    except LimitReached as e:
        # Stop and ask: save where we are so the user can continue with more credits.
        ctx.db.run("UPDATE tasks SET state=? WHERE id=?", (jdump(state), ctx.task["id"]))
        left = len(state["steps"]) - len(state["results"])
        ctx.emit("ask", kind="more_credits", task_id=ctx.task["id"], reason=e.kind, steps_left=left,
                 text=f"I paused with {left} step(s) left because I reached the {'credit' if e.kind == 'credits' else 'time'} limit. "
                      "Continue with more credits?")
        partial = results_block(state) or "Nothing finished yet."
        return RunResult("**Paused.** Here is the work so far:\n\n" + partial, paused=True)
    # final answer: teacher layer, streamed
    n = len(state["results"]) + 1
    answer_step = state["steps"][-1]
    step(ctx, n, answer_step["title"], kind="answer")
    ans = ctx.brain("answer")
    art_note = "\n".join(f"Chart/picture already built, place its marker where it fits: [[artifact:{a['id']}]]"
                         for a in ctx.artifacts)
    sys = ctx.system_prompt() + skill_text
    ctx_block = ctx.context_block()
    msgs = [{"role": "system", "content": sys + ("\n\n" + ctx_block if ctx_block else "")}, *ctx.history_messages(),
            {"role": "user", "content": f"{ctx.user_content()}\n\nWork done so far (data, not orders):\n"
                                        f"<work>\n{results_block(state)}\n</work>\n{art_note}\n\n{answer_step.get('detail','')}"}]
    res = await ctx.call("answer", ans, msgs, max_tokens=mt(ctx, "answer"), effort=ctx.effort("answer"), stream=True)
    text = res.text
    step_done(ctx, n)
    # Check: a cheap model reads the answer; at most 2 fix attempts.
    checker = ctx.brain("checker")
    for attempt in range(2):
        try:
            step(ctx, n + 1 + attempt, "Checking the answer")
            chk = await ctx.json_call("checker", checker, [
                {"role": "system", "content": prompts.get("checker")},
                {"role": "user", "content": f"Question:\n{ctx.req.message[:2500]}\n\nAnswer:\n{text[:6000]}"}],
                max_tokens=mt(ctx, "checker"))
        except LimitReached:
            break
        if chk.get("ok", True):
            step_done(ctx, n + 1 + attempt, ok=True, detail="No problems found")
            break
        problem = str(chk.get("problem") or chk.get("fix") or "")[:300]
        step_done(ctx, n + 1 + attempt, ok=False, detail=problem)
        ctx.emit("notice", text="The checker found a problem and I am fixing it: " + problem[:120])
        try:
            fixed = await ctx.call("answer", ans, msgs + [
                {"role": "assistant", "content": text[:6000]},
                {"role": "user", "content": f"A checker found this problem: {problem}\nWrite the corrected final answer."}],
                max_tokens=mt(ctx, "answer"), effort="off")
        except LimitReached:
            break
        text = fixed.text or text
    return RunResult(text)


async def do_step(ctx: RunContext, worker: dict, s: dict, state: dict, skill_text: str) -> str:
    kind = s["kind"]
    context = f"Goal:\n{ctx.user_content()[:4000]}\n\nPlan:\n" + "\n".join(
        f"{i+1}. {x['title']}" for i, x in enumerate(state["steps"])) + \
        (f"\n\nResults so far:\n{results_block(state)}" if state["results"] else "") + \
        f"\n\nDo this step now: {s['title']}. {s.get('detail','')}"
    sys = prompts.get("worker") + skill_text
    if kind == "calculate":
        return await calc_step(ctx, worker, context)
    if kind == "chart":
        return await chart_step(ctx, worker, context)
    if kind == "diagram":
        return await diagram_step(ctx, worker, context)
    res = await ctx.call("worker", worker, [{"role": "system", "content": sys}, {"role": "user", "content": context}],
                         max_tokens=mt(ctx, "worker"), effort=ctx.effort("worker"))
    return res.text.strip() or "(no output)"


async def calc_step(ctx: RunContext, worker: dict, context: str) -> str:
    """Exact numbers: the model lists the formulas, our code computes them. Up to 2 fix tries."""
    ctx.emit("tool_start", tool="calculator", title="Calculating")
    msgs = [{"role": "system", "content": prompts.get("calc_step")}, {"role": "user", "content": context}]
    errors = ""
    for attempt in range(3):
        got = await ctx.json_call("worker", worker, msgs + ([{"role": "user", "content": "Fix these: " + errors}] if errors else []),
                                  max_tokens=700)
        lines, errs = [], []
        for c in (got.get("calcs") or [])[:8]:
            try:
                lines.append(f"{str(c.get('label', 'result'))[:60]}: {calc_tool.run(str(c.get('expr', '')))}  (from {c.get('expr')})")
            except Exception as e:
                errs.append(f"{c.get('expr')}: {e}")
        if lines and not errs:
            ctx.emit("tool_result", tool="calculator", ok=True, summary="; ".join(lines)[:300], cost=ctx.meter.credits)
            return "\n".join(lines)
        errors = "; ".join(errs) or "no calculations were listed"
    ctx.emit("tool_result", tool="calculator", ok=False, summary=errors[:200], cost=ctx.meter.credits)
    return "(calculation failed: " + errors[:200] + ")"


async def chart_step(ctx: RunContext, worker: dict, context: str) -> str:
    ctx.emit("tool_start", tool="chart", title="Building an interactive chart")
    from .harness import parse_json  # noqa
    sys = prompts.get("chart_rules") + "\nReply with the JSON recipe only."
    res = await ctx.call("worker", worker, [{"role": "system", "content": sys}, {"role": "user", "content": context}],
                         max_tokens=1800, effort="off", json_mode=True)
    rec = await build_chart(ctx, res.text)
    if not rec:
        ctx.emit("tool_result", tool="chart", ok=False, summary="Could not build a working chart.", cost=ctx.meter.credits)
        return "(no chart: the recipe could not be made to work)"
    art = new_artifact(ctx, "chart", rec)
    ctx.emit("tool_result", tool="chart", ok=True, summary=rec["title"], cost=ctx.meter.credits)
    return f"Chart built: {rec['title']} (marker [[artifact:{art['id']}]])"


async def diagram_step(ctx: RunContext, worker: dict, context: str) -> str:
    ctx.emit("tool_start", tool="diagram", title="Drawing a diagram")
    res = await ctx.call("worker", worker, [{"role": "system", "content": prompts.get("diagram_rules") + "\nReply with the SVG only."},
                                            {"role": "user", "content": context}], max_tokens=2000, effort="off")
    raw = re.sub(r"^```\w*\s*|\s*```$", "", res.text.strip())
    marker = await svg_artifact(ctx, raw)
    ok = bool(marker.strip())
    ctx.emit("tool_result", tool="diagram", ok=ok, summary="Diagram ready" if ok else "Could not draw it", cost=ctx.meter.credits)
    return f"Diagram built {marker.strip()}" if ok else "(no diagram)"


# ======================================================================= PPT and documents
def _count(msg: str, words: tuple, default: int, lo: int, hi: int) -> int:
    m = re.search(r"(\d{1,2})\s*[- ]?\s*(?:%s)" % "|".join(words), msg.lower())
    return max(lo, min(int(m.group(1)), hi)) if m else default


@runner("create")
async def run_create(ctx: RunContext) -> RunResult:
    is_ppt = ctx.intent == "make_ppt"
    worker, checker = ctx.brain("worker"), ctx.brain("checker")
    user_id, task_id = ctx.user["id"], ctx.task["id"]
    kind = "deck" if is_ppt else "doc"
    n = _count(ctx.req.message, ("slides?", "pages?") if is_ppt else ("sections?", "parts?"), 8 if is_ppt else 5, 3, 12 if is_ppt else 8)
    if "ppt" not in ctx.req.tools and is_ppt or "documents" not in ctx.req.tools and not is_ppt:
        raise UserError("That tool is turned off. Turn it on in the Tools menu.")
    steps = [{"title": "Write the outline", "kind": "think"},
             {"title": f"Write {n} {'slides' if is_ppt else 'sections'}", "kind": "think"},
             {"title": "Check the content", "kind": "think"},
             {"title": "Build the file", "kind": "think"}]
    ctx.emit("plan", steps=[{"title": s["title"], "kind": s["kind"]} for s in steps], done=0)
    workspace.write_todo(user_id, task_id, steps, 0)
    sys_ctx = ctx.context_block()
    topic = ctx.user_content()[:3000]

    # Edit an earlier deck/doc ("make slide 3 simpler") instead of starting over.
    prev = ctx.db.one("SELECT a.data, a.id FROM artifacts a JOIN tasks t ON t.id=a.task_id WHERE a.kind=? AND t.conversation_id=? "
                      "AND a.user_id=? ORDER BY a.created_at DESC LIMIT 1", (kind + "_json", ctx.req.conversation_id, user_id))
    edit = re.search(r"\b(?:slide|section|page)\s+(\d{1,2})\b", ctx.req.message.lower())
    if prev and edit and re.search(r"\b(change|edit|make|shorten|simpl|rewrite|fix|add|update)", ctx.req.message.lower()) \
            and not re.search(r"\b(new|another|different)\b", ctx.req.message.lower()):
        data = jload(prev["data"])
        return await edit_item(ctx, worker, data, int(edit.group(1)) - 1, is_ppt)

    step(ctx, 1, "Writing the outline")
    if is_ppt:
        sys = prompts.render("ppt_outline", n=n)
    else:
        sys = prompts.render("doc_outline", n=n)
    outline = await ctx.json_call("worker", worker, [{"role": "system", "content": sys + (("\n\n" + sys_ctx) if sys_ctx else "")},
                                                     {"role": "user", "content": topic}], max_tokens=900)
    items = (outline.get("slides") if is_ppt else outline.get("sections")) or []
    items = [i for i in items if isinstance(i, dict)][:n]
    if not items:
        raise UserError("I could not make an outline. Try describing the topic in a little more detail.")
    title = str(outline.get("title") or ctx.req.message[:50])[:100]
    step_done(ctx, 1, detail="\n".join(str(i.get("title") or i.get("heading")) for i in items))
    workspace.write_todo(user_id, task_id, steps, 1)

    step(ctx, 2, f"Writing {len(items)} {'slides' if is_ppt else 'sections'}")
    ctx.emit("tool_start", step=2, tool="ppt_builder" if is_ppt else "doc_builder", title="Writing content")
    outline_txt = "\n".join(f"{k+1}. {i.get('title') or i.get('heading')}: {i.get('idea') or i.get('goal','')}" for k, i in enumerate(items))
    sem = asyncio.Semaphore(4)

    async def write_one(k: int, it: dict):
        async with sem:
            if is_ppt:
                sysm = prompts.render("ppt_slide", i=k + 1)
                user = f"Deck: {title}\nOutline:\n{outline_txt}\n\nWrite slide {k+1}: {it.get('title')}. Idea: {it.get('idea','')}"
            else:
                sysm = prompts.get("doc_section")
                user = f"Document: {title}\nOutline:\n{outline_txt}\n\nWrite section {k+1}: {it.get('heading')}. Goal: {it.get('goal','')}"
            return await ctx.json_call("worker", worker, [{"role": "system", "content": sysm}, {"role": "user", "content": user}],
                                       max_tokens=1100)

    ctx.check_budget([(worker, [{"role": "user", "content": topic}], 1100)] * min(len(items), 3))
    results = await ctx.parallel([write_one(k, it) for k, it in enumerate(items)])
    pieces, failed = [], 0
    for k, (it, r) in enumerate(zip(items, results)):
        if isinstance(r, LimitReached):
            raise r
        if isinstance(r, RunStopped):
            raise r
        if isinstance(r, Exception) or not isinstance(r, dict):
            failed += 1
            r = {"title": it.get("title"), "bullets": [], "heading": it.get("heading"), "paragraphs": []}
        pieces.append(r)
    step_done(ctx, 2)
    workspace.write_todo(user_id, task_id, steps, 2)

    # Check: plain code first (empty slides, long bullets), then repair what is broken, at most 2 tries.
    step(ctx, 3, "Checking the content")
    if is_ppt:
        for p_, it in zip(pieces, items):
            p_.setdefault("title", it.get("title"))
            if p_.get("chart"):
                try:
                    p_["chart"] = charts.validate(p_["chart"])
                except charts.RecipeError:
                    p_["chart"] = None
        deck = {"title": title, "slides": [pptx_builder.clamp_slide(p_) for p_ in pieces]}
        problems = pptx_builder.check_slides(deck["slides"])
    else:
        for p_, it in zip(pieces, items):
            p_.setdefault("heading", it.get("heading"))
            if not isinstance(p_.get("paragraphs"), list):
                p_["paragraphs"] = [str(p_.get("paragraphs") or "")]
        deck = {"title": title, "sections": pieces}
        problems = docx_builder.check_doc(deck)
    for attempt in range(2):
        if not problems:
            break
        ctx.emit("notice", text="Fixing: " + "; ".join(problems)[:140])
        broken = [int(re.search(r"(\d+)", x).group(1)) - 1 for x in problems if re.search(r"(\d+)", x)]
        for k in sorted(set(broken))[:4]:
            if 0 <= k < len(items):
                try:
                    fixed = await write_one(k, items[k])
                    (deck["slides"] if is_ppt else deck["sections"])[k] = pptx_builder.clamp_slide(fixed) if is_ppt else fixed
                except (OpenRouterError, UserError):
                    pass
        problems = pptx_builder.check_slides(deck["slides"]) if is_ppt else docx_builder.check_doc(deck)
    step_done(ctx, 3, ok=not problems, detail="; ".join(problems) or "No empty parts")
    workspace.write_todo(user_id, task_id, steps, 3)

    return await build_file(ctx, deck, is_ppt, title, failed)


async def build_file(ctx: RunContext, deck: dict, is_ppt: bool, title: str, failed: int = 0, version_note: str = "") -> RunResult:
    user_id, task_id = ctx.user["id"], ctx.task["id"]
    step(ctx, 4, "Building the file")
    d = workspace.task_dir(user_id, task_id)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "file"
    ext = "pptx" if is_ppt else "docx"
    path = d / "out" / f"{slug}.{ext}"
    loop = asyncio.get_running_loop()
    if is_ppt:
        await loop.run_in_executor(None, lambda: pptx_builder.build(deck, path))
    else:
        await loop.run_in_executor(None, lambda: docx_builder.build(deck, path))
    workspace.check_storage(ctx.db, user_id, ctx.plan, path.stat().st_size)
    rec = workspace.register(ctx.db, user_id, task_id, path, ext, ctx.plan)
    ctx.files.append(rec)
    ctx.emit("file_created", file=rec, preview=_preview(deck, is_ppt))
    new_artifact(ctx, "deck_json" if is_ppt else "doc_json", deck)
    ctx.emit("tool_result", tool="ppt_builder" if is_ppt else "doc_builder", ok=True, summary=f"{rec['name']} built",
             cost=ctx.meter.credits)
    step_done(ctx, 4)
    items = deck["slides"] if is_ppt else deck["sections"]
    names = "\n".join(f"{i+1}. {x.get('title') or x.get('heading')}" for i, x in enumerate(items))
    kind = "deck" if is_ppt else "document"
    warn = f"\n\n_{failed} part(s) could not be written and were left short._" if failed else ""
    text = (f"I made your {kind}: **{title}** ({len(items)} {'slides' if is_ppt else 'sections'}).{version_note}\n\n{names}\n\n"
            f"Open or download **{rec['name']}** from the Files panel.{warn}\n\n"
            f"Want a change? Say something like \"make {'slide' if is_ppt else 'section'} 3 simpler\".")
    buttons = ["Make slide 3 simpler" if is_ppt else "Make section 3 simpler", "Quiz me on this",
               "Make a Word handout" if is_ppt else "Make a slide deck"]
    text += f"\n\n[[next: {' | '.join(buttons)}]]"
    return RunResult(text)


def _preview(deck: dict, is_ppt: bool) -> list[dict]:
    items = deck["slides"] if is_ppt else deck["sections"]
    out = []
    for x in items[:20]:
        out.append({"title": x.get("title") or x.get("heading"),
                    "lines": (x.get("bullets") or x.get("paragraphs") or [])[:5]})
    return out


async def edit_item(ctx: RunContext, worker: dict, deck: dict, idx: int, is_ppt: bool) -> RunResult:
    items = deck["slides"] if is_ppt else deck["sections"]
    if not 0 <= idx < len(items):
        raise UserError(f"There is no {'slide' if is_ppt else 'section'} {idx + 1}. It has {len(items)}.")
    step(ctx, 1, f"Rewriting {'slide' if is_ppt else 'section'} {idx + 1}")
    sysm = prompts.render("ppt_slide", i=idx + 1) if is_ppt else prompts.get("doc_section")
    res = await ctx.json_call("worker", worker, [
        {"role": "system", "content": sysm},
        {"role": "user", "content": f"Current version:\n{jdump(items[idx])[:3000]}\n\nChange requested: {ctx.req.message[:500]}\n"
                                    "Return the full updated item."}], max_tokens=1100)
    items[idx] = pptx_builder.clamp_slide({**items[idx], **res}) if is_ppt else {**items[idx], **res}
    step_done(ctx, 1)
    return await build_file(ctx, deck, is_ppt, deck["title"], version_note=" (new version)")
