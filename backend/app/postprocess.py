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
BLOCK = re.compile(r"```(chart|svg|quiz|flashcards|table)[ \t]*\n(.*?)```", re.S)
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


def validate_flashcards(d) -> dict:
    cards = d.get("cards") if isinstance(d, dict) else None
    if not isinstance(cards, list) or not 3 <= len(cards) <= 20:
        raise ValueError("flashcards need between 3 and 20 cards")
    out, seen = [], set()
    for c in cards:
        if not isinstance(c, dict) or not str(c.get("front", "")).strip() or not str(c.get("back", "")).strip():
            raise ValueError("every card needs a front and a back")
        front = str(c["front"]).strip()[:120]
        if front.lower() in seen:
            continue
        seen.add(front.lower())
        out.append({"front": front, "back": str(c["back"]).strip()[:240],
                    "hint": str(c.get("hint", "")).strip()[:120] or None})
    if len(out) < 3:
        raise ValueError("too many duplicate cards")
    return {"title": str(d.get("title", "Flashcards"))[:80], "cards": out}


def validate_table(d) -> dict:
    cols, rows = (d.get("columns"), d.get("rows")) if isinstance(d, dict) else (None, None)
    if not isinstance(cols, list) or not 2 <= len(cols) <= 8:
        raise ValueError("a table needs 2 to 8 columns")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 60:
        raise ValueError("a table needs 1 to 60 rows")
    clean_cols, keys = [], []
    for c in cols:
        if not isinstance(c, dict) or not str(c.get("key", "")).strip():
            raise ValueError("every column needs a key")
        key = str(c["key"]).strip()[:40]
        keys.append(key)
        clean_cols.append({"key": key, "label": str(c.get("label", key))[:60],
                           "type": "number" if c.get("type") == "number" else "text",
                           "unit": str(c.get("unit", ""))[:12]})
    clean_rows = []
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError("every row must be an object")
        row = {}
        for col in clean_cols:
            v = r.get(col["key"], "")
            if col["type"] == "number":
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    v = None
            else:
                v = str(v)[:120]
            row[col["key"]] = v
        clean_rows.append(row)
    return {"title": str(d.get("title", "Table"))[:80], "columns": clean_cols, "rows": clean_rows}


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
    if kind in ("flashcards", "table"):
        validator = validate_flashcards if kind == "flashcards" else validate_table
        raw = body
        for attempt in range(MAX_FIX + 1):
            try:
                data = validator(parse_json(raw))
                return f"\n\n[[artifact:{new_artifact(ctx, kind, data)['id']}]]\n\n"
            except (ValueError, KeyError, AttributeError, TypeError) as e:
                if attempt == MAX_FIX:
                    ctx.notices.append(f"The {kind} block was not readable, so I left it out.")
                    return ""
                raw = await repair(ctx, kind, raw, str(e))
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
        defaults = DEFAULT_BUTTONS if ctx.req.teacher_enabled else ["Expand this answer", "Show an example"]
        buttons = [b for b in defaults if b != "Show a graph" or "chart" in ctx.req.tools][:3]
    ctx.emit("check", ok=True, note="Numbers, charts and pictures were checked." if ctx.artifacts else "Checked.")
    return text, buttons, ctx.artifacts
