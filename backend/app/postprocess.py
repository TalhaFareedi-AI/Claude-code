"""Check + teacher layer (section 3, steps 7 and 8).

Takes the model's raw text and:
  - fills {{calc: ...}} with exact numbers (no mental math)
  - checks chart recipes, SVG drawings and quizzes in code, and repairs them (at most 2 tries)
  - pulls out the 2 or 3 next-step buttons
Nothing in the AI's text is trusted: every block is validated before the screen draws it.
"""
import re
import uuid

from . import charts, prompts, workspace
from .db import jdump, now
from .tools import calc as calc_tool, diagram

NEXT = re.compile(r"\[\[\s*next\s*:\s*(.+?)\]\]", re.I | re.S)
BLOCK = re.compile(r"```(chart|svg|quiz)[ \t]*\n(.*?)```", re.S)
MARK = re.compile(r"\[\[artifact:(a_[0-9a-f]{8,12})\]\]")
DEFAULT_BUTTONS = ["Explain simpler", "Quiz me", "Show a graph"]
MAX_FIX = 2


def clean_label(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" .*_`")[:40]


def validate_quiz(q) -> dict:
    if not isinstance(q, dict) or not isinstance(q.get("questions"), list) or not 1 <= len(q["questions"]) <= 8:
        raise ValueError("quiz needs 1 to 8 questions")
    out = []
    for item in q["questions"]:
        opts = item.get("options")
        if not isinstance(item.get("q"), str) or not isinstance(opts, list) or not 2 <= len(opts) <= 5:
            raise ValueError("each question needs q and 2 to 5 options")
        ans = item.get("answer")
        if not isinstance(ans, int) or isinstance(ans, bool) or not 0 <= ans < len(opts):
            raise ValueError("answer must be the index of one option")
        out.append({"q": item["q"][:300], "options": [str(o)[:120] for o in opts], "answer": ans,
                    "why": str(item.get("why", ""))[:300]})
    return {"questions": out}


def new_artifact(ctx, kind: str, data: dict) -> dict:
    art = {"id": "a_" + uuid.uuid4().hex[:10], "kind": kind, "data": data}
    ctx.db.run("INSERT INTO artifacts(id,user_id,task_id,kind,data,created_at) VALUES(?,?,?,?,?,?)",
               (art["id"], ctx.user["id"], ctx.task["id"], kind, jdump(data), now()))
    ctx.artifacts.append(art)
    ctx.emit("artifact", id=art["id"], kind=kind, data=data)
    return art


def charts_today(ctx) -> int:
    start = now() - (now() % 86400)
    return int(ctx.db.scalar("SELECT COUNT(*) FROM artifacts WHERE user_id=? AND kind='chart' AND created_at>=?",
                             (ctx.user["id"], start)))


async def repair(ctx, kind: str, raw: str, error: str) -> str:
    q = ctx.quick()
    res = await ctx.call("checker", q, [
        {"role": "system", "content": prompts.render("repair", kind=kind, error=error)},
        {"role": "user", "content": raw[:6000]}], max_tokens=1500, budget_check=False)
    return re.sub(r"^```\w*\s*|\s*```$", "", res.text.strip())


async def build_chart(ctx, raw: str) -> dict | None:
    """Validate a chart recipe; ask a cheap model to repair it up to twice. Returns the clean recipe or None."""
    from .harness import parse_json
    for attempt in range(MAX_FIX + 1):
        try:
            return charts.validate(parse_json(raw))
        except (charts.RecipeError, ValueError) as e:
            if attempt == MAX_FIX:
                ctx.notices.append("I could not make the chart work, so I left it out.")
                return None
            try:
                raw = await repair(ctx, "chart recipe", raw, str(e))
            except Exception:
                return None
    return None


async def handle_block(ctx, kind: str, body: str) -> str:
    from .harness import parse_json
    if kind == "chart":
        if charts_today(ctx) >= ctx.rules["charts_per_day"]:
            ctx.notices.append("Daily chart limit reached for your plan.")
            return "_(Chart limit reached for today.)_"
        rec = await build_chart(ctx, body)
        if not rec:
            return ""
        return f"\n\n[[artifact:{new_artifact(ctx, 'chart', rec)['id']}]]\n\n"
    if kind == "quiz":
        raw = body
        for attempt in range(MAX_FIX + 1):
            try:
                quiz = validate_quiz(parse_json(raw))
                return f"\n\n[[artifact:{new_artifact(ctx, 'quiz', quiz)['id']}]]\n\n"
            except (ValueError, KeyError, AttributeError) as e:
                if attempt == MAX_FIX:
                    ctx.notices.append("The quiz was not readable, so I left it out.")
                    return ""
                raw = await repair(ctx, "quiz", raw, str(e))
    if kind == "svg":
        return await svg_artifact(ctx, body)
    return ""


async def svg_artifact(ctx, raw: str, name: str = "diagram") -> str:
    for attempt in range(MAX_FIX + 1):
        try:
            clean = diagram.sanitize(raw)
            break
        except diagram.SvgError as e:
            if attempt == MAX_FIX:
                ctx.notices.append("I could not draw the picture safely, so I left it out.")
                return ""
            raw = await repair(ctx, "svg", raw, str(e))
    art = new_artifact(ctx, "svg", {"svg": clean})
    try:
        d = workspace.task_dir(ctx.user["id"], ctx.task["id"])
        n = len([f for f in ctx.files if f["name"].startswith(name)]) + 1
        p = d / "out" / f"{name}-{n}.svg"
        workspace.check_storage(ctx.db, ctx.user["id"], ctx.plan, len(clean))
        p.write_text(clean)
        rec = workspace.register(ctx.db, ctx.user["id"], ctx.task["id"], p, "svg", ctx.plan)
        ctx.files.append(rec)
        ctx.emit("file_created", file=rec)
    except workspace.PathEscape:
        pass
    return f"\n\n[[artifact:{art['id']}]]\n\n"


async def finalize(ctx, text: str) -> tuple[str, list[str], list[dict]]:
    text, _ = calc_tool.fill(text or "")
    matches = NEXT.findall(text)
    buttons = [clean_label(b) for b in re.split(r"\s*\|\s*", matches[-1])] if matches else []
    buttons = [b for b in buttons if b][:3]
    text = NEXT.sub("", text)
    out, last = [], 0
    for m in BLOCK.finditer(text):
        out.append(text[last:m.start()])
        out.append(await handle_block(ctx, m.group(1), m.group(2)))
        last = m.end()
    out.append(text[last:])
    text = "".join(out)
    known = {a["id"] for a in ctx.artifacts}
    text = MARK.sub(lambda m: m.group(0) if m.group(1) in known else "", text)  # drop invented markers
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not buttons and text:
        buttons = [b for b in DEFAULT_BUTTONS if b != "Show a graph" or "chart" in ctx.req.tools][:3]
    ctx.emit("check", ok=True, note="Numbers, charts and pictures were checked." if ctx.artifacts else "Checked.")
    return text, buttons, ctx.artifacts
