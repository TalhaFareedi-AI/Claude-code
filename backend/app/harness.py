"""The harness (sections 2 and 3). Same checklist for every message:

 receive -> wallet check -> build desk -> route -> (plan) -> do steps -> check -> teacher layer -> bill -> learn

Every AI call goes through RunContext.call, which is the meter: no call goes uncounted.
"""
import asyncio
import hashlib
import json
import math
import re
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal

from . import activity, catalog, charts, memory, modes as modes_mod, prompts, skills, wallet, workspace
from .config import settings
from .db import DB, jdump, jload, now
from .estimate import estimate
from .openrouter import LLMResult, OpenRouter, OpenRouterError, Usage, build_reasoning
from . import plans as plans_mod
from .plans import rules as plan_rules
from .pricing import EFFORT_ORDER, call_cost, clamp_effort, credits_for_cost
from .tools import calc as calc_tool, diagram

RECENT_MESSAGES = 8  # kept word for word; older turns live in the summary and session notes
CONTROL_ROLES = {"planner", "checker", "critic", "judge"}  # effort dial does not touch these
GREETING = re.compile(r"^\s*(hi|hello|hey|thanks?|thank you|ok(ay)?|good (morning|evening|night)|bye)\b[\s!.?]*$", re.I)
HARD_WORDS = re.compile(r"\b(step by step|prove|derive|design|build|plan|compare|analy[sz]e|research paper|in depth|complete|full)\b", re.I)


class RunStopped(Exception):
    pass


class LimitReached(Exception):
    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind  # "credits" | "time" | "steps"


class UserError(Exception):
    """A problem the user can fix (bad mode, plan limit). Never a crash."""


@dataclass
class RunRequest:
    message: str
    mode: str = "auto"
    brains: dict = field(default_factory=dict)      # role -> model id (or list of ids)
    effort: str = "auto"
    rounds: int | None = None
    tries: int | None = None
    max_credits: int | None = None
    tools: list[str] = field(default_factory=lambda: ["chart", "diagram", "documents", "ppt"])
    skills: list[str] | None = None                 # None = all enabled
    intent: str | None = None                       # set by buttons: simplify, quiz, chart, make_ppt...
    conversation_id: str | None = None
    confirm: bool = False
    continue_task: str | None = None
    extra_credits: int = 0
    private_route: bool | None = None
    target_message: int | None = None               # message id for "Explain simpler"
    uploads: list[str] = field(default_factory=list)  # workspace_files ids from /api/upload
    team: dict = field(default_factory=dict)
    teacher_enabled: bool = False  # teaching style is opt-in: by default the assistant answers directly
    length: str = "auto"           # auto | short | medium | long: how much room the answer gets
    image_model: str | None = None  # which model draws pictures; the user picks it
    teacher_model: str | None = None
    approved_plan: list[dict] | None = None
    request_id: str | None = None


def tokens_of(text: str) -> int:
    return max(1, int(len(text) / 3.5))


def parse_json(text: str):
    """Pull the first JSON object out of a model reply (handles fences and chatter)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S).strip()
    try:
        value = json.loads(t)
        if isinstance(value, dict):
            return value
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    start = t.find("{")
    while start != -1:
        try:
            value, _ = decoder.raw_decode(t[start:])
            if isinstance(value, dict):
                return value
        except ValueError:
            pass
        start = t.find("{", start + 1)
    raise ValueError("no JSON found")


# ---------------------------------------------------------------------------------
class Emitter:
    """Sends small events to the screen and saves each one, so a reload can replay the run."""

    def __init__(self, db: DB, task_id: str):
        self.db, self.task_id, self.seq = db, task_id, 0
        self.queue: asyncio.Queue = asyncio.Queue()
        self.closed = False

    def emit(self, type_: str, **data) -> dict:
        self.seq += 1
        ev = {"seq": self.seq, "type": type_, **data}
        self.db.run("INSERT INTO run_events(task_id,seq,type,data,created_at) VALUES(?,?,?,?,?)",
                    (self.task_id, self.seq, type_, jdump(data), now()))
        if not self.closed:
            self.queue.put_nowait(ev)
        return ev

    def close(self) -> None:
        self.closed = True
        self.queue.put_nowait(None)

    async def stream(self):
        while True:
            ev = await self.queue.get()
            if ev is None:
                return
            yield ev


class Meter:
    """Counts every token of every call. One usage_events row per call."""

    def __init__(self, db: DB, user_id: str, task_id: str, max_credits: int):
        self.db, self.user_id, self.task_id = db, user_id, task_id
        self.max_credits = max_credits
        self.usd = Decimal(0)
        self.credits = 0
        self.step_no = 0
        self.lock = asyncio.Lock()

    def credits_if(self, extra_usd: Decimal) -> int:
        return credits_for_cost(self.usd + extra_usd)

    async def record(self, role: str, model: dict, res: LLMResult, *, tool_units: dict | None = None,
                     extra_usd: float = 0.0, billable: bool = True, latency_ms: int = 0) -> int:
        async with self.lock:
            u = res.usage
            if u.cost is not None:
                cost, src = Decimal(repr(float(u.cost))), "openrouter"
            else:
                cost = call_cost(model["price_in"], model["price_out"], u.prompt, u.completion, u.cached,
                                 model.get("price_cached"))
                src = "table"
            if src == "table":  # OpenRouter's own cost already includes plugin fees
                cost += Decimal(repr(float(extra_usd)))
            self.usd += cost if billable else Decimal(0)
            new_credits = credits_for_cost(self.usd) if billable else self.credits
            delta = new_credits - self.credits
            self.credits = new_credits
            self.step_no += 1
            self.db.run(
                "INSERT INTO usage_events(user_id,task_id,step_no,role,model,input_tokens,cached_tokens,output_tokens,"
                "reasoning_tokens,tool_units,cost_usd,cost_source,credits_charged,finish_reason,created_at,latency_ms) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.user_id, self.task_id, self.step_no, role, res.model, u.prompt, u.cached, u.completion,
                 u.reasoning, jdump(tool_units if tool_units is not None else
                                    ({"web_search_requests": u.searches} if getattr(u, "searches", None) is not None else {})),
                 float(cost), src, delta, res.finish_reason, now(), latency_ms))
            if billable:
                self.db.run("UPDATE tasks SET credits_used=?, usd_used=? WHERE id=?",
                            (self.credits, float(self.usd), self.task_id))
            return delta


class RunContext:
    def __init__(self, harness: "Harness", user: dict, task: dict, req: RunRequest, mode: dict, emitter: Emitter):
        self.h, self.db, self.llm = harness, harness.db, harness.llm
        self.user, self.task, self.req, self.mode, self.em = user, task, req, mode, emitter
        self.plan = user["plan"]
        self.rules = plan_rules(self.plan)
        self.private = self.plan == "school" or bool(req.private_route if req.private_route is not None else user.get("private_route"))
        self.meter = Meter(self.db, user["id"], task["id"], task["max_credits"])
        self.stop_flag = False
        self.deadline = time.monotonic() + settings.task_time_limit_s
        self.intent = req.intent or "chat"
        self.needs: list[str] = []
        self.artifacts: list[dict] = []
        self.files: list[dict] = []
        self.notices: list[str] = []
        self.history: list[dict] = []
        self.file_texts: list[tuple[str, str]] = []
        self.profile: dict = {}
        self.summary = ""
        self.memory_block = ""
        self.memory_command: dict | None = None
        self.images_made = 0
        self.asked_image_model = False
        self._brain_cache: dict = {}
        self.runner = mode["runner"]
        self.rounds: int | None = None
        self.tries: int | None = None
        self.best = ""
        from .team import normalize_team
        self.team = normalize_team(req.team)
        self.budget_lock = asyncio.Lock()
        self.reserved_usd = Decimal(0)
        self.agent_usd: dict[str, Decimal] = {}
        self.agent_reserved: dict[str, Decimal] = {}

    # ---- events -------------------------------------------------------------
    def emit(self, type_: str, **data):
        return self.em.emit(type_, **data)

    def cost_event(self) -> None:
        self.emit("cost", used=min(self.meter.credits, self.task["max_credits"]), max=self.task["max_credits"])

    def emit_text(self, text: str) -> None:
        """Send a finished answer as text pieces (the screen types it live)."""
        for i in range(0, len(text), 160):
            self.emit("text", delta=text[i:i + 160])

    # ---- brains ---------------------------------------------------------------
    #: How much room an answer gets. Multiplies the mode's own max_tokens for output-facing roles.
    LENGTH_FACTOR = {"short": 0.5, "medium": 1.0, "long": 2.0}
    OUTPUT_ROLES = ("answer", "judge", "write", "rewrite", "writer", "worker", "teacher", "finisher", "builder")

    def out_tokens(self, role: str, base: int | None = None) -> int:
        """Token budget for one call, after the user's length preference."""
        base = base if base is not None else self.mode["max_tokens"].get(role, 1500)
        if role not in self.OUTPUT_ROLES:
            return base
        factor = self.LENGTH_FACTOR.get(self.req.length, 1.0)
        return max(256, min(int(base * factor), 32000))

    def effort(self, role: str) -> str:
        default = self.mode["reasoning"].get(role, "off")
        if self.req.effort != "auto" and role not in CONTROL_ROLES and default != "off":
            return clamp_effort(self.req.effort, self.plan)
        return clamp_effort(default, self.plan)

    def _pick(self, spec: str, role: str, exclude: tuple = ()) -> dict:
        tiers = self.rules["tiers"]
        if spec == "code":
            for mid in catalog.CODING_BRAINS:
                m = catalog.get(self.db, mid)
                if m and m["available"] and m["approved"] and m["tier"] in tiers:
                    return m
            spec = "tier:smart"
        tier = spec.split(":", 1)[1] if spec.startswith("tier:") else None
        if tier is None:
            if spec.endswith(":free"):
                raise UserError("Free-tier provider models are not available in this app.")
            m = catalog.get(self.db, spec)
            if not m or not m["available"] or not m["approved"]:
                raise UserError(f"The model {spec} is not available.")
            if m["tier"] not in tiers:
                raise UserError(f"{m['name']} needs a higher plan.")
            if self.private and not m.get("private_route"):
                raise UserError(f"{m['name']} does not support private routing.")
            return m
        need = self.effort(role) not in ("off", "auto")
        if self.private:
            exclude = tuple(exclude) + tuple(m["id"] for m in catalog.listing(self.db) if not m.get("private_route"))
        return catalog.resolve(self.db, tier, need_thinks=need, exclude=exclude, tiers_allowed=tiers)

    def brains(self, role: str) -> list[dict]:
        if role in self._brain_cache:
            return self._brain_cache[role]
        user_pick = self.req.brains.get(role)
        out: list[dict] = []
        if user_pick:
            ids = user_pick if isinstance(user_pick, list) else [user_pick]
            for mid in ids:
                if not isinstance(mid, str) or not mid.strip() or mid.endswith(":free"):
                    raise UserError("Pick an approved model; free-tier provider models are not allowed.")
                m = catalog.get(self.db, mid)
                if not m or not m["available"] or not m["approved"]:
                    raise UserError(f"The model {mid} is not available.")
                if m["tier"] not in self.rules["tiers"]:
                    raise UserError(f"{m['name']} needs a higher plan.")
                out.append(m)
        else:
            slot = self.mode["slots"][role]
            specs = slot if isinstance(slot, list) else [slot]
            picked: list[dict] = []
            for spec in specs:
                taken = tuple(p["id"] for p in picked)
                labs = {p["lab"] for p in picked}
                try:  # prefer a new lab: different labs make different mistakes
                    m = self._pick(spec, role, exclude=taken + tuple(
                        r["id"] for r in catalog.listing(self.db) if r["lab"] in labs and len(specs) > 1))
                except LookupError:
                    m = self._pick(spec, role, exclude=taken)
                picked.append(m)
            out = picked
        if self.private:
            bad = [m["name"] for m in out if not m.get("private_route")]
            if bad:
                raise UserError(f"Private route is on, and {', '.join(bad)} cannot use it.")
        self._brain_cache[role] = out
        return out

    def brain(self, role: str) -> dict:
        return self.brains(role)[0]

    def quick(self) -> dict:
        key = "_quick"
        if key not in self._brain_cache:
            rows = catalog.listing(self.db, self.rules["tiers"])
            if self.private:
                rows = [m for m in rows if m.get("private_route")]
            if not rows:
                raise UserError("No approved private model is available.")
            quick = [m for m in rows if m["tier"] == "quick"] or rows
            self._brain_cache[key] = [min(quick, key=lambda m: m["price_in"] + m["price_out"])]
        return self._brain_cache[key][0]

    # ---- stops --------------------------------------------------------------
    def check_stop(self) -> None:
        if self.stop_flag:
            raise RunStopped()
        if time.monotonic() > self.deadline:
            raise LimitReached("time")

    def check_budget(self, planned: list[tuple[dict, list, int]]) -> None:
        """Stop 1: money. Upper-bound the next calls before sending them."""
        extra = Decimal(0)
        for model, messages, max_tokens in planned:
            tin = sum(tokens_of(m["content"]) if isinstance(m["content"], str) else 500 for m in messages)
            extra += call_cost(model["price_in"], model["price_out"], tin, max_tokens)
        if self.meter.credits_if(extra) > self.task["max_credits"]:
            raise LimitReached("credits")

    # ---- the one place AI is called -------------------------------------------------
    async def call(self, role: str, model: dict, messages: list, *, max_tokens: int, effort: str = "off",
                   json_mode: bool = False, stream: bool = False, plugins: list | None = None,
                   extra_usd: float = 0.0, budget_check: bool = True, tools: list | None = None,
                   max_tool_calls: int | None = None, modalities: list | None = None,
                   agent_id: str | None = None,
                   agent_max_credits: int | None = None, agent_timeout_s: float | None = None,
                   _empty_retry: bool = False, _continued: bool = False) -> LLMResult:
        self.check_stop()
        reasoning = build_reasoning(model, effort, max_tokens)
        fallbacks = catalog.fallbacks(self.db, model["id"], 2, private_only=self.private)
        fallbacks = [mid for mid in fallbacks if catalog.get(self.db, mid)["tier"] in self.rules["tiers"]]
        candidates = [model, *(catalog.get(self.db, mid) for mid in fallbacks)]
        # UTF-8 bytes plus framing is a conservative token bound, including non-English text.
        tin = sum(len(jdump(m).encode("utf-8")) + 12 for m in messages)
        required = max(call_cost(m["price_in"], m["price_out"], tin, max_tokens) for m in candidates)
        if tools:
            n = max_tool_calls or 1
            # Every server-tool step can repeat the context and produce another completion;
            # reserve the loop plus the final answer, including accumulated page results.
            tool_input = tin * (n + 1) + 48000 * n * (n + 1) // 2
            required = max(call_cost(m["price_in"], m["price_out"], tool_input, max_tokens * (n + 1)) for m in candidates)
        required += Decimal(repr(float(extra_usd)))
        async with self.budget_lock:
            # budget_check is retained for compatibility; paid calls never bypass the cap.
            if self.meter.credits_if(self.reserved_usd + required) > self.task["max_credits"]:
                raise LimitReached("credits")
            if agent_id and agent_max_credits is not None:
                agent_total = self.agent_usd.get(agent_id, Decimal(0)) + self.agent_reserved.get(agent_id, Decimal(0))
                if credits_for_cost(agent_total + required) > agent_max_credits:
                    raise UserError(f"The {agent_id} agent reached its credit cap.")
            self.reserved_usd += required
            if agent_id:
                self.agent_reserved[agent_id] = self.agent_reserved.get(agent_id, Decimal(0)) + required
        t0 = time.monotonic()
        kw = dict(reasoning=reasoning, fallbacks=fallbacks, json_mode=json_mode, private=self.private, modalities=modalities,
                  zdr=self.private and self.plan == "school", plugins=plugins)
        if tools is not None:
            kw["tools"] = tools
        if max_tool_calls is not None:
            kw["max_tool_calls"] = max_tool_calls
        if tools:
            kw["stop_server_tools_when"] = [
                {"type": "step_count_is", "step_count": max_tool_calls or 1},
                {"type": "max_cost", "max_cost_in_dollars": max(0.000001, float(required) / 2)},
            ]
        try:
            if stream:
                async def on_delta(piece: str):
                    self.emit("text", delta=piece)
                request = self.llm.chat_stream(model["id"], messages, max_tokens=max_tokens, on_delta=on_delta, **kw)
            else:
                request = self.llm.chat(model["id"], messages, max_tokens=max_tokens, **kw)
            running = asyncio.create_task(request)
            try:
                end = min(self.deadline, t0 + (agent_timeout_s or settings.task_time_limit_s))
                while not running.done():
                    self.check_stop()
                    if time.monotonic() >= end:
                        raise asyncio.TimeoutError()
                    await asyncio.wait({running}, timeout=min(0.2, max(0.001, end-time.monotonic())))
                res = running.result()
            finally:
                if not running.done():
                    running.cancel()
                    await asyncio.gather(running, return_exceptions=True)
            used = catalog.get(self.db, res.model) or model
            ms = int((time.monotonic() - t0) * 1000)
            async with self.budget_lock:
                before = self.meter.usd
                fallback_fee = extra_usd
                if tools and max_tool_calls and getattr(res.usage, "searches", None) is not None:
                    fallback_fee *= res.usage.searches / max_tool_calls
                await self.meter.record(role, used, res, extra_usd=fallback_fee, latency_ms=ms)
                if agent_id:
                    self.agent_usd[agent_id] = self.agent_usd.get(agent_id, Decimal(0)) + self.meter.usd-before
        except OpenRouterError as exc:
            if getattr(exc, "usage", None) is not None:
                partial = LLMResult(getattr(exc, "partial_text", ""), model["id"], exc.usage, "error")
                await self.meter.record(role, model, partial, extra_usd=extra_usd, billable=False)
            raise
        finally:
            async with self.budget_lock:
                self.reserved_usd -= required
                if agent_id:
                    self.agent_reserved[agent_id] -= required
        self.emit("call", role=role, model=used["name"], ms=ms, tokens_in=res.usage.prompt + res.usage.cached,
                  tokens_out=res.usage.completion, thinking=res.usage.reasoning, usd=round(float(self.meter.usd), 6))
        if res.reasoning_text or (res.usage.reasoning and effort not in ("off", "auto")):
            self.emit("thinking", seconds=round(time.monotonic() - t0), tokens=res.usage.reasoning,
                      summary=f"{used['name']} considered the task before answering.")
        self.cost_event()
        # Thinking can eat all of max_tokens and leave an empty answer. Retry once, lower effort.
        if not res.text.strip() and res.finish_reason == "length" and not _empty_retry:
            self.notices.append(f"{model['name']} ran out of room while thinking, so I retried with lower effort.")
            self.emit("notice", text=self.notices[-1])
            return await self.call(role, model, messages, max_tokens=min(16000, int(max_tokens * 1.5)), effort="off",
                                   json_mode=json_mode, stream=stream, plugins=plugins, tools=tools,
                                   max_tool_calls=max_tool_calls, extra_usd=extra_usd, agent_id=agent_id,
                                   agent_max_credits=agent_max_credits, agent_timeout_s=agent_timeout_s,
                                   _empty_retry=True)
        # Cut off mid-sentence: finish it once rather than leaving a half-written answer on screen.
        if (res.finish_reason == "length" and res.text.strip() and not json_mode
                and not _continued and role in self.OUTPUT_ROLES):
            try:
                more = await self.call(role, model, messages + [
                    {"role": "assistant", "content": res.text},
                    {"role": "user", "content": "You were cut off by the output limit. Continue from exactly where you "
                     "stopped, starting with the very next character. Do not repeat anything, do not restate the "
                     "question, and do not add a closing summary that was not already due."}],
                    max_tokens=max_tokens, effort="off", stream=stream, plugins=plugins, extra_usd=0.0,
                    agent_id=agent_id, agent_max_credits=agent_max_credits, agent_timeout_s=agent_timeout_s,
                    budget_check=budget_check, _continued=True)
            except (LimitReached, OpenRouterError, UserError):
                self.notices.append("The answer was cut short by the output limit. Ask for the rest, or pick a longer "
                                    "response length in Settings.")
                self.emit("notice", text=self.notices[-1])
                return res
            joined = res.text.rstrip() + ("\n\n" if res.text.rstrip().endswith((".", "!", "?", ":", "`")) else " ") + more.text.lstrip()
            usage = Usage(prompt=res.usage.prompt + more.usage.prompt, cached=res.usage.cached + more.usage.cached,
                          completion=res.usage.completion + more.usage.completion,
                          reasoning=res.usage.reasoning + more.usage.reasoning,
                          cost=(res.usage.cost or 0) + (more.usage.cost or 0) if res.usage.cost is not None else None)
            self.emit("notice", text="The answer hit the output limit, so I finished it in a second pass.")
            return LLMResult(joined, more.model, usage, more.finish_reason, more.reasoning_text,
                             res.images + more.images, res.sources + more.sources)
        if not res.text.strip():
            raise UserError("The model returned no answer. Try a different brain or a larger output budget.")
        return res

    async def json_call(self, role: str, model: dict, messages: list, *, max_tokens: int, effort: str = "off",
                        budget_check: bool = True) -> dict:
        res = await self.call(role, model, messages, max_tokens=max_tokens, effort=effort, json_mode=True,
                              budget_check=budget_check)
        try:
            return parse_json(res.text)
        except ValueError:
            fix = messages + [{"role": "assistant", "content": res.text[:1500]},
                              {"role": "user", "content": "That was not valid JSON. Reply again with valid JSON only."}]
            res = await self.call(role, model, fix, max_tokens=max_tokens, effort="off", json_mode=True,
                                  budget_check=budget_check)
            try:
                return parse_json(res.text)
            except ValueError as e:
                raise UserError("The model did not return a readable answer. Please retry.") from e

    async def parallel(self, coros: list):
        """Start all tries at once; the user waits for the slowest, not the sum."""
        results = await asyncio.gather(*coros, return_exceptions=True)
        return results

    # ---- the desk (context budget, section 4) ----------------------------------------
    def system_prompt(self) -> str:
        """Tool rules are loaded only when that artifact is actually wanted, so a plain answer stays cheap."""
        parts = [prompts.get("teacher") if self.req.teacher_enabled else prompts.get("direct")]
        wants = set(self.needs) | ({"quiz"} if self.intent == "quiz" else set())
        # a document or deck can embed a chart or a diagram, so those rules travel with it
        if wants & {"doc", "slides"}:
            wants |= {"chart", "diagram"}
        for need, tool, rules in (("doc", "documents", "doc_rules"), ("slides", "ppt", "slides_rules"),
                                  ("chart", "chart", "chart_rules"), ("diagram", "diagram", "diagram_rules"),
                                  ("quiz", None, "quiz_rules"), ("flashcards", "flashcards", "flashcard_rules"),
                                  ("table", "table", "table_rules"), ("image", "images", "image_rules")):
            if need in wants and (tool is None or tool in self.req.tools):
                parts.append(prompts.get(rules))
        return "\n\n".join(parts)

    def context_block(self) -> str:
        """Background for the model. A greeting gets none of it: profile and memory would otherwise
        read as the current task, and they are wasted input tokens on a message that needs none."""
        bits = []
        if memory.SMALL_TALK.match(self.req.message or ""):
            return ""
        if self.profile:
            bits.append("BACKGROUND on this reader, from past chats, so you can pitch the answer right. "
                        "It is not their current question and not a task: never answer it or mention it.\n"
                        + jdump(self.profile))
        if self.summary:
            bits.append("Earlier in this chat: " + self.summary)
        if self.memory_block:
            bits.append(self.memory_block)
        if self.memory_command and self.memory_command["kind"] in ("saved", "forgot", "refused"):
            bits.append(f"Memory action just done for the user: {self.memory_command['text']} Confirm it in one short sentence.")
        return "\n\n".join(bits)

    def history_messages(self, max_chars: int = 14000) -> list[dict]:
        out, used = [], 0
        for m in reversed(self.history[-RECENT_MESSAGES:]):
            c = m["content"]
            if used + len(c) > max_chars:
                c = c[: max(0, max_chars - used)]
            if not c:
                break
            out.append({"role": m["role"], "content": c})
            used += len(c)
        return list(reversed(out))

    def user_content(self, text: str | None = None) -> str:
        text = text if text is not None else self.req.message
        if self.file_texts:
            files = "\n".join(f'<file name="{n}">\n{t}\n</file>' for n, t in self.file_texts)
            return f"{files}\n\n{text}"
        return text

    def base_messages(self, extra_system: str = "") -> list[dict]:
        sys = self.system_prompt()
        ctx = self.context_block()
        if ctx:
            sys += "\n\n" + ctx
        if extra_system:
            sys += "\n\n" + extra_system
        return [{"role": "system", "content": sys}] + self.history_messages() + \
               [{"role": "user", "content": self.user_content()}]


# ---------------------------------------------------------------------------------
@dataclass
class RunResult:
    text: str
    paused: bool = False
    streamed: bool = False
    extra: dict = field(default_factory=dict)


class Harness:
    def __init__(self, db: DB, llm: OpenRouter):
        self.db, self.llm = db, llm
        self.active: dict[str, RunContext] = {}
        self.background: set[asyncio.Task] = set()

    # ---- helpers -------------------------------------------------------------------
    def get_user(self, user_id: str) -> dict:
        u = self.db.one("SELECT * FROM users WHERE id=?", (user_id,))
        if not u:
            self.db.run("INSERT INTO users(id,name,plan,auto_spend,created_at) VALUES(?,?,?,?,?)",
                        (user_id, "Student", "free", settings.auto_spend_limit, now()))
            wallet.grant_plan(self.db, user_id, "free")
            self.db.run("UPDATE users SET plan_renews_at=? WHERE id=?", (now() + 30 * 86400, user_id))
            activity.log(self.db, user_id, "account_created", plan="free")
            u = self.db.one("SELECT * FROM users WHERE id=?", (user_id,))
        owner = settings.unlock_all or (settings.unlock_admin and u.get("role") == "admin" and u.get("status") != "blocked")
        if owner and u["plan"] != "owner":
            self.db.run("UPDATE users SET plan='owner', plan_renews_at=NULL WHERE id=?", (user_id,))
            top_up = plans_mod.OWNER_CREDITS - wallet.balance(self.db, user_id)
            if top_up > 0:
                wallet.add(self.db, user_id, top_up, "owner:credits")
            activity.log(self.db, user_id, "plan_changed", plan="owner", via="UNLOCK_ALL" if settings.unlock_all else "UNLOCK_ALL=admin")
            u = self.db.one("SELECT * FROM users WHERE id=?", (user_id,))
        elif u.get("plan_renews_at") and u["plan_renews_at"] < now() and u["plan"] != "owner":
            from . import billing
            billing.renew(self.db, u)
            u = self.db.one("SELECT * FROM users WHERE id=?", (user_id,))
        return u

    def remaining_limit(self, user: dict) -> int:
        """Credits the user may still spend today and this month (admin limits, else the plan's daily cap)."""
        daily = user.get("daily_limit")
        if daily is None:
            daily = plan_rules(user["plan"]).get("daily_credit_cap") or 10**9
        left = daily - wallet.spent_today(self.db, user["id"])
        if user.get("monthly_limit") is not None:
            left = min(left, user["monthly_limit"] - wallet.spent_month(self.db, user["id"]))
        return int(left)

    def attach_uploads(self, user_id: str, task_id: str, ids: list[str]) -> None:
        """Copy the user's uploaded files into this task's inputs folder."""
        inputs = workspace.task_dir(user_id, task_id) / "inputs"
        for fid in ids[:5]:
            row = self.db.one("SELECT * FROM workspace_files WHERE id=? AND user_id=? AND task_id='uploads'", (fid, user_id))
            if row:
                src = workspace.path_of(row)
                if src.exists():
                    workspace.check_storage(self.db, user_id, self.get_user(user_id)["plan"], src.stat().st_size)
                    target = inputs / re.sub(r"^[0-9a-f]{6}_", "", src.name)
                    if target.exists():
                        target = inputs / src.name
                    shutil.copy2(src, target)
                    workspace.register(self.db, user_id, task_id, target, row["kind"], self.get_user(user_id)["plan"])

    def profile(self, user_id: str) -> dict:
        r = self.db.one("SELECT data FROM profiles WHERE user_id=?", (user_id,))
        return jload(r["data"], {}) if r else {}

    def task_chain(self, user_id: str, task_id: str) -> list[str]:
        chain, seen = [], set()
        while task_id and task_id not in seen:
            task = self.db.one("SELECT id,config FROM tasks WHERE id=? AND user_id=?", (task_id,user_id))
            if not task:
                break
            chain.append(task_id)
            seen.add(task_id)
            task_id = jload(task["config"], {}).get("request", {}).get("continue_task")
        return list(reversed(chain))

    async def drain(self) -> None:
        """Wait for runs and background learning to finish (used by tests and shutdown)."""
        while True:
            pending = [t for t in self.background if not t.done()]
            if not pending:
                self.background.clear()
                return
            await asyncio.gather(*pending, return_exceptions=True)
            await asyncio.sleep(0)

    def stop(self, task_id: str) -> bool:
        ctx = self.active.get(task_id)
        if ctx:
            ctx.stop_flag = True
        return bool(ctx)

    def recover_interrupted(self) -> int:
        """Reconcile local single-process runs after a server restart, without reissuing paid calls."""
        rows = self.db.all("SELECT * FROM tasks WHERE status IN ('starting','running') ORDER BY created_at")
        count = 0
        for task in rows:
            if task["id"] in self.active:
                continue
            state = jload(task["state"], {})
            status = "paused" if isinstance(state, dict) and state.get("steps") else "stopped"
            charged = wallet.settle(self.db, task["user_id"], task["id"], task["credits_used"] or 0, "interrupted run")
            self.db.run("UPDATE tasks SET status=?,finished_at=?,credits_used=? WHERE id=?",
                        (status, now(), charged, task["id"]))
            emitter = Emitter(self.db, task["id"])
            emitter.seq = self.db.scalar("SELECT MAX(seq) FROM run_events WHERE task_id=?", (task["id"],))
            emitter.emit("notice", text="The server restarted. Completed work was kept and unused credits released.")
            if status == "paused":
                emitter.emit("ask", kind="more_credits", task_id=task["id"], reason="restart",
                             text="This task paused when the server restarted. Continue from the saved plan?",
                             used=charged, max=task["max_credits"])
            emitter.emit("run_done", status=status, used=charged, max=task["max_credits"])
            source = jload(task["config"], {}).get("request", {}).get("continue_task")
            if source:
                self.db.run("UPDATE tasks SET status='continued' WHERE id=? AND status='resuming'", (source,))
            count += 1
        self.db.run("UPDATE tasks SET status='paused' WHERE status='resuming'")
        return count

    # ---- routing (rules first, AI only when unsure) -------------------------------
    def _office_kind(self, req: RunRequest) -> str | None:
        """pptx or docx, when this chat already built one. A follow-up then edits that file."""
        if not req.conversation_id:
            return None
        row = self.db.one("SELECT f.kind FROM workspace_files f JOIN tasks t ON t.id=f.task_id "
                          "WHERE t.conversation_id=? AND f.kind IN ('pptx','docx') ORDER BY f.id DESC LIMIT 1",
                          (req.conversation_id,))
        return row["kind"] if row else None

    def route_rules(self, req: RunRequest) -> dict:
        m = req.message.strip()
        low = m.lower()
        words = len(m.split())
        intent, needs = req.intent or "", []
        if not intent:
            # The Office builders (.pptx, .docx) are the slow, expensive path, so they wait for a request
            # that actually asks for that file. A plain "write me a document" gets the quick reading
            # document instead: Markdown, shown in the chat and kept in the workspace.
            office = bool(re.search(r"\b(pptx?|powerpoint|docx?|word|download(able)?|office|"
                                    r"file i can (open|edit|share|send)|send me the file)\b", low))
            office = office or self._office_kind(req) is not None  # a follow-up edits the file this chat built
            make = bool(re.search(r"\b(make|create|build|generate|write|prepare|draft)\b", low))
            if make and office and re.search(r"\b(ppt|pptx|powerpoint|slides?|slide deck|deck|presentation)\b", low):
                intent = "make_ppt"
            elif make and office and re.search(r"\b(doc|docx|document|essay|report|worksheet|lesson plan|handout)\b", low):
                intent = "make_doc"
            elif re.search(r"\b(research|latest|news|sources?|find out|look up|search the web)\b", low):
                intent = "research"
            elif re.search(r"\b(code|function|script|python|javascript|bug|refactor|regex|sql)\b", low):
                intent = "code"
            elif re.search(r"\bquiz\b|\btest me\b|\bflashcards?\b", low):
                intent = "quiz"
            elif re.search(r"\bsimpl(er|ify)\b|\beli5\b|easier words", low):
                intent = "simplify"
            elif re.search(r"\b(solve|calculate|compute|how much|how many)\b", low) or re.search(r"\d\s*[-+*/^]\s*\d", low):
                intent = "solve"
            elif words <= 6 and GREETING.match(m):
                intent = "chat"
            else:
                intent = "teach"
        if re.search(r"\b(chart|graph|plot|slider|visuali[sz]e|interactive)\b", low) or intent == "chart":
            needs.append("chart")
        if re.search(r"\b(diagram|flowchart|circuit|draw|water cycle)\b", low):
            needs.append("diagram")
        if intent == "quiz":
            needs.append("quiz")
        if intent == "make_doc" or re.search(r"\b(docu?ment|docuemnt|write[ -]?up|guide|cheat ?sheet|handout|report|"
                                             r"study notes|revision notes|worksheet|lesson plan)\b", low):
            needs.append("doc")
        if intent == "make_ppt" or re.search(r"\b(slides?|deck|presentation|powerpoint|ppt)\b", low):
            needs.append("slides")
        if re.search(r"\bflash ?cards?\b|\bmemori[sz]e\b|\brevision cards?\b", low):
            needs.append("flashcards")
        if re.search(r"\btables?\b|\bcompare .{0,40}\b(and|vs|versus)\b|\bside by side\b", low):
            needs.append("table")
        if "images" in req.tools and re.search(r"\b(pictures?|images?|photos?|illustrations?|draw|drawing|"
                                               r"render|artwork|poster)\b", low):
            needs.append("image")
        if GREETING.match(m) or (words <= 8 and not re.search(r"\d", m) and not needs and intent in ("chat", "teach")):
            complexity = "easy"
        elif words > 60 or HARD_WORDS.search(low) or intent in ("make_ppt", "make_doc"):
            complexity = "hard"
        else:
            complexity = "medium"
        return {"intent": intent, "needs": needs, "complexity": complexity,
                "make_plan": intent in ("make_ppt", "make_doc") or complexity == "hard", "source": "rules"}

    async def route(self, ctx: RunContext) -> dict:
        # Route before reserving money without sending an unheld paid call.
        # Larger workflows run the metered understand/enhance agent after the hold.
        return self.route_rules(ctx.req)

    def choose_mode(self, req: RunRequest, route: dict, plan: str) -> dict:
        wanted = req.mode
        if req.team and wanted == "auto":
            from .team import normalize_team
            team = normalize_team(req.team)
            if wanted == "auto" and team.get("preset") == "fast":
                wanted = "fast"
            elif (team.get("plan_mode") != "off" or team.get("architects") or team.get("researchers", {}).get("count", 0)) \
                    and not (wanted == "auto" and GREETING.match(req.message)):
                if wanted == "auto" and route["intent"] != "research":
                    wanted = "developer" if route["intent"] == "code" else "deep"
        if wanted == "auto":
            intent, cx = route["intent"], route["complexity"]
            wanted = {"easy": "fast", "medium": "normal", "hard": "deep"}[cx]
            if intent == "research":
                wanted = "research"
            elif intent == "code":
                wanted = "developer" if cx == "hard" else "normal"
            elif intent in ("make_ppt", "make_doc"):
                wanted = "deep"
            m = modes_mod.get(self.db, wanted)
            if not m or not modes_mod.allowed(m, plan):
                m = modes_mod.get(self.db, "normal")
            return m
        m = modes_mod.get(self.db, wanted)
        if not m:
            raise UserError(f"Unknown mode {wanted}.")
        if not modes_mod.allowed(m, plan):
            raise UserError(f"{m['name']} is not part of your plan. Try Normal, or upgrade.")
        return m

    @staticmethod
    def _image_model(ctx: RunContext, route: dict) -> dict | None:
        """The image model to budget for, when this ask looks like it wants a drawn picture."""
        if "image" not in route["needs"] or "images" not in ctx.req.tools:
            return None
        from .tools import image as image_tool
        return image_tool.chosen_model(ctx)

    # ---- estimate (shown before the run) ---------------------------------------------
    def make_estimate(self, ctx: RunContext, route: dict) -> dict:
        mode = dict(ctx.mode)
        if route["intent"] in ("make_ppt", "make_doc") and mode["runner"] == "deep":
            mode["runner"] = "create"
        ctx.runner = mode["runner"]
        roles = {r: ctx.brains(r) for r in self._roles(mode)}
        from .team import agent_model, effective_team, team_estimate
        cfg = effective_team(ctx)
        if ctx.runner in ("deep", "create") and cfg["builder"]["enabled"]:
            roles["worker"] = [agent_model(ctx, "builder", "worker")]
        if ctx.runner == "deep" and cfg["checker"]["enabled"]:
            roles["checker"] = [agent_model(ctx, "checker", "checker")]
        if ctx.runner == "research":
            roles["writer"] = [agent_model(ctx, "finisher" if cfg["finisher"]["enabled"] else "builder", "writer")]
        rounds = self._clamp(ctx.req.rounds, mode["params"].get("default_rounds"), 1,
                             min(mode["params"].get("max_rounds", 5), ctx.rules["max_rounds"]))
        tries = self._clamp(ctx.req.tries, mode["params"].get("default_tries"), 1,
                            min(mode["params"].get("max_tries", 5), ctx.rules["max_tries"]))
        ctx.rounds, ctx.tries = rounds, tries
        est = estimate(mode, roles, rounds=rounds, tries=tries, effort=ctx.req.effort,
                       chart="chart" in route["needs"], image_model=self._image_model(ctx, route))
        extra_parts = team_estimate(ctx) if ctx.runner in ("deep", "research", "create") else []
        if ctx.runner in ("deep", "research"):
            replaced = {"plan"} | ({"searches"} if ctx.runner == "research" else set())
            est["parts"] = [part for part in est["parts"] if part["name"] not in replaced]
        if ctx.runner in ("deep", "create") and not cfg["builder"]["enabled"]:
            est["parts"] = []
        if ctx.runner in ("deep", "create") and not cfg["checker"]["enabled"]:
            est["parts"] = [part for part in est["parts"] if part["name"] != "check"]
        if ctx.runner == "deep" and cfg["builder"]["enabled"]:
            final = agent_model(ctx, "finisher", "answer") if cfg["finisher"]["enabled"] else roles["worker"][0]
            extra_parts.append({"name": "finisher", "usd": float(call_cost(final["price_in"], final["price_out"], 8000, mode["max_tokens"].get("answer",2500)))})
            if cfg["checker"]["enabled"]:
                check = roles["checker"][0]
                extra_parts.append({"name": "step checks", "usd": float(call_cost(check["price_in"], check["price_out"], 6000, 600)) * 6})
            if cfg["plan_depth"] != "light":
                repeats = min(6, mode["params"].get("max_steps", 8) - 1) if cfg["plan_depth"] == "deep" else 1
                extra_parts.extend({"name": "replanning " + part["name"], "usd": part["usd"] * repeats}
                                   for part in list(extra_parts) if part["name"] in ("planner", "plan_judge"))
        if ctx.req.teacher_enabled and ctx.req.teacher_model:
            teacher = ctx._pick(ctx.req.teacher_model, "teacher")
            extra_parts.append({"name": "teacher", "usd": float(call_cost(teacher["price_in"], teacher["price_out"], 5000, 2500))})
        if extra_parts or ctx.runner in ("deep", "research", "create"):
            est["parts"].extend(extra_parts)
            est["usd"] = sum(p["usd"] for p in est["parts"])
            est["credits"] = max(1, credits_for_cost(est["usd"]))
        est["rounds"], est["tries"] = rounds, tries
        return est

    @staticmethod
    def _clamp(v, default, lo, hi):
        if default is None:
            return None
        v = default if v is None else v
        return max(lo, min(int(v), hi))

    @staticmethod
    def _roles(mode: dict) -> list[str]:
        return list(mode["slots"].keys())

    # ---- the run ---------------------------------------------------------------------
    async def start(self, user_id: str, req: RunRequest) -> tuple[str, Emitter]:
        """Create the task and start it in the background. The screen reads the emitter."""
        payload = asdict(req)
        payload.pop("request_id", None)
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if req.request_id:
            existing = self.db.one("SELECT * FROM run_requests WHERE user_id=? AND request_id=?", (user_id, req.request_id))
            if existing:
                if existing["payload_hash"] != fingerprint:
                    raise UserError("This request ID was already used for a different message.")
                task = self.db.one("SELECT * FROM tasks WHERE id=? AND user_id=?", (existing["task_id"], user_id))
                if not task:
                    raise UserError("The earlier request is no longer available.")
                req.conversation_id = task["conversation_id"]
                emitter = Emitter(self.db, task["id"])
                self._schedule(self._replay(task["id"], emitter))
                return task["id"], emitter
        if req.approved_plan is not None and not req.continue_task:
            raise UserError("An edited plan must refer to a paused task.")
        if req.continue_task:
            previous = self.db.one("SELECT * FROM tasks WHERE id=? AND user_id=?", (req.continue_task, user_id))
            if not previous or previous["status"] != "paused":
                raise UserError("Only your own paused tasks can be continued.")
            if req.conversation_id and req.conversation_id != previous["conversation_id"]:
                raise UserError("Continue the task in its original conversation.")
            req.conversation_id = previous["conversation_id"]
            saved = jload(previous["config"], {}).get("request", {})
            if saved:
                req.message = saved.get("message", req.message)
                for name in ("mode", "team", "brains", "effort", "tools", "skills", "teacher_enabled", "teacher_model", "private_route", "intent", "uploads"):
                    if name in saved:
                        setattr(req, name, saved[name])
            if req.extra_credits < 1:
                req.extra_credits = req.max_credits or previous["max_credits"] or 20
            state = jload(previous["state"], {})
            if req.approved_plan is not None and state.get("awaiting_plan_approval"):
                remaining = max(0, (previous["max_credits"] or 0) - (previous["credits_used"] or 0))
                if remaining < 1:
                    raise UserError("Planning used the current credit cap. Increase the task budget before approving the plan.")
                req.extra_credits = min(req.extra_credits, remaining)
            claimed = self.db.run("UPDATE tasks SET status='resuming' WHERE id=? AND user_id=? AND status='paused'",
                                  (req.continue_task, user_id))
            if claimed.rowcount != 1:
                raise UserError("This paused task is already being continued.")
        user = self.get_user(user_id)
        task_id = "t_" + uuid.uuid4().hex[:10]
        em = Emitter(self.db, task_id)
        conv_id = req.conversation_id
        conv = self.db.one("SELECT * FROM conversations WHERE id=? AND user_id=?", (conv_id, user_id)) if conv_id else None
        if not conv:
            conv_id = "c_" + uuid.uuid4().hex[:10]
            self.db.run("INSERT INTO conversations(id,user_id,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                        (conv_id, user_id, req.message.strip()[:60] or "New chat", now(), now()))
        req.conversation_id = conv_id
        if not req.continue_task:
            self.db.run("INSERT INTO messages(conversation_id,role,content,meta,task_id,created_at) VALUES(?,?,?,?,?,?)",
                        (conv_id, "user", req.message, "{}", task_id, now()))
        self.db.run("INSERT INTO tasks(id,user_id,conversation_id,mode,intent,status,estimate,max_credits,config,created_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (task_id, user_id, conv_id, req.mode, req.intent or "", "starting", 0, 0,
                     jdump({"mode": req.mode, "effort": req.effort}), now()))
        activity.log(self.db, user_id, "chat_sent", conversation_id=conv_id, task_id=task_id, mode=req.mode,
                     chars=len(req.message), preview=req.message[:160], continued=bool(req.continue_task))
        self.db.run("UPDATE users SET last_seen_at=? WHERE id=?", (now(), user_id))
        if req.request_id:
            self.db.run("INSERT INTO run_requests(user_id,request_id,task_id,payload_hash) VALUES(?,?,?,?)",
                        (user_id, req.request_id, task_id, fingerprint))
        task = asyncio.create_task(self._run(user, task_id, req, em))
        self.background.add(task)
        task.add_done_callback(self.background.discard)
        return task_id, em

    async def _replay(self, task_id: str, emitter: Emitter) -> None:
        after = 0
        try:
            while True:
                rows = self.db.all("SELECT seq,type,data FROM run_events WHERE task_id=? AND seq>? ORDER BY seq", (task_id, after))
                for row in rows:
                    after = row["seq"]
                    event = {"seq": after, "type": row["type"], **jload(row["data"], {})}
                    emitter.queue.put_nowait(event)
                    if event["type"] == "run_done":
                        return
                if not rows:
                    await asyncio.sleep(0.1)
        finally:
            emitter.close()

    async def _run(self, user: dict, task_id: str, req: RunRequest, em: Emitter) -> None:
        ctx: RunContext | None = None
        held = False
        status = "error"
        try:
            # 1-2. receive + wallet check
            if wallet.available(self.db, user["id"]) < 1:
                em.emit("run_start", task_id=task_id, conversation_id=req.conversation_id, mode="", brains={})
                em.emit("ask", kind="topup", text="You are out of credits. Add credits or wait for your plan to refresh.",
                        available=wallet.available(self.db, user["id"]))
                status = "blocked"
                return
            if user.get("status") == "blocked":
                raise UserError("Your account is paused. Please contact support.")
            remaining_limit = self.remaining_limit(user)
            if remaining_limit < 1:
                em.emit("run_start", task_id=task_id, conversation_id=req.conversation_id, mode="", brains={})
                em.emit("ask", kind="limit", text="You reached your credit limit for now. It resets soon, or ask the admin to raise it.")
                status = "blocked"
                return
            # 3-4. desk + route
            route_ctx_mode = modes_mod.get(self.db, "normal")
            task = self.db.one("SELECT * FROM tasks WHERE id=?", (task_id,))
            ctx = RunContext(self, user, task, req, route_ctx_mode, em)
            self.active[task_id] = ctx
            ctx.profile = self.profile(user["id"])
            conv = self.db.one("SELECT * FROM conversations WHERE id=?", (req.conversation_id,))
            ctx.summary = conv["summary"] or ""
            if user.get("memory_enabled", 1) is not None and user.get("memory_enabled", 1):
                cmd = memory.handle_command(self.db, user["id"], req.message, req.conversation_id)
                if cmd:
                    ctx.memory_command = cmd
                    ctx.notices.append(cmd["text"])
                    em.emit("memory", action=cmd["kind"], text=cmd["text"])
                    activity.log(self.db, user["id"], "memory_" + cmd["kind"], text=cmd["text"][:200])
            ctx.memory_block, used_ids = memory.desk_block(self.db, user, conv, req.message)
            if used_ids or ctx.memory_block:
                em.emit("memory", action="recalled", count=len(used_ids),
                        recalled_chats="Related moments" in ctx.memory_block)
            ctx.history = [{"role": m["role"], "content": m["content"]} for m in self.db.all(
                "SELECT role,content FROM messages WHERE conversation_id=? AND task_id!=? ORDER BY id",
                (req.conversation_id, task_id))]
            if req.target_message:
                row = self.db.one("SELECT content FROM messages WHERE id=? AND conversation_id=?",
                                  (req.target_message, req.conversation_id))
                if row:
                    ctx.req.message = f"Explain this again in much simpler words, with an everyday example:\n\n{row['content'][:6000]}"
            self.attach_uploads(user["id"], task_id, req.uploads)
            ctx.file_texts = workspace.read_text_inputs(user["id"], task_id)
            if req.continue_task:
                chain = self.task_chain(user["id"], req.continue_task)
                ctx.artifacts = [artifact for parent in chain for artifact in self.db.all(
                    "SELECT id,kind,data FROM artifacts WHERE task_id=? AND user_id=?", (parent,user["id"]))]
                for artifact in ctx.artifacts:
                    artifact["data"] = jload(artifact["data"], {})
                    ctx.emit("artifact", **artifact)
                ctx.files = [workspace.file_row(self.db,row["id"]) for parent in chain for row in self.db.all(
                    "SELECT id FROM workspace_files WHERE task_id=? AND user_id=? AND path LIKE 'out/%'", (parent,user["id"]))]
                if not ctx.file_texts:
                    for parent in reversed(chain):
                        ctx.file_texts = workspace.read_text_inputs(user["id"], parent)
                        if ctx.file_texts:
                            break
            route = await self.route(ctx)
            ctx.intent, ctx.needs = route["intent"], route["needs"]
            mode = self.choose_mode(req, route, user["plan"])
            ctx.mode = mode
            ctx._brain_cache.clear()
            if mode.get("daily_limit"):
                day = now() - (now() % 86400)
                used = self.db.scalar("SELECT COUNT(*) FROM tasks WHERE user_id=? AND mode=? AND created_at>=? AND status IN ('done','running','paused')",
                                      (user["id"], mode["id"], day))
                if used >= mode["daily_limit"]:
                    raise UserError(f"{mode['name']} is limited to {mode['daily_limit']} runs a day. Try another mode.")
            est = self.make_estimate(ctx, route)
            # A picture the user asked for is paid media, not thinking, so it gets room above the mode's cap.
            ceiling = mode["max_credits"] + est.get("media_credits", 0)
            cap = req.max_credits or min(ceiling, max(user["auto_spend"], est["credits"]))
            cap = max(1, min(cap, ceiling))
            if req.continue_task:
                cap = max(1, min(req.extra_credits, mode["max_credits"]))
            cap = max(1, min(cap, remaining_limit))  # never past the daily or monthly limit
            if ctx.team.get("max_credits"):
                cap = min(cap, ctx.team["max_credits"])
            ctx.task["max_credits"] = cap
            ctx.meter.max_credits = cap
            # Big jobs: show the plan and the estimate, ask once.
            needs_ask = mode["big"] and est["credits"] > user["auto_spend"] and not req.confirm and not req.continue_task
            brains_view = {r: [m["name"] for m in b] for r, b in ((r, ctx.brains(r)) for r in self._roles(mode))}
            em.emit("run_start", task_id=task_id, conversation_id=req.conversation_id, mode=mode["id"],
                    mode_name=mode["name"], runner=ctx.runner, intent=ctx.intent, brains=brains_view,
                    estimate=est["credits"], max=cap, routed_by=route["source"])
            if needs_ask:
                em.emit("ask", kind="confirm", text=f"{mode['name']} will use about {est['credits']} credits, at most {cap}. Continue?",
                        estimate=est["credits"], max=cap)
                status = "awaiting_confirm"
                return
            # Hold the maximum; settle the real cost at the end.
            hold_amount = cap if mode["big"] else min(cap, max(est["credits"] * 2, 5))
            hold_amount = max(hold_amount, ctx.meter.credits + 1)
            try:
                wallet.hold(self.db, user["id"], task_id, hold_amount)
                held = True
            except wallet.InsufficientCredits as e:
                em.emit("ask", kind="topup", text=f"This needs up to {e.need} credits and you have {e.available}. "
                        "Pick a cheaper mode, lower the cost cap, or add credits.", need=e.need, available=e.available)
                status = "blocked"
                return
            ctx.task["max_credits"] = min(cap, hold_amount)
            ctx.meter.max_credits = ctx.task["max_credits"]
            self.db.run("UPDATE tasks SET status='running', mode=?, intent=?, estimate=?, max_credits=?, config=? WHERE id=?",
                        (mode["id"], ctx.intent, est["credits"], ctx.task["max_credits"],
                         jdump({"effort": req.effort, "rounds": ctx.rounds, "tries": ctx.tries, "runner": ctx.runner,
                                "request": asdict(req)}), task_id))
            workspace.task_dir(user["id"], task_id, req.message[:30])
            # 5-8. the mode runs, then check + teacher layer
            from .runners import RUNNERS  # late import: runners use this module
            result = await asyncio.wait_for(RUNNERS[ctx.runner](ctx), timeout=settings.task_time_limit_s + 30)
            status = "paused" if result.paused else "done"
            await self.finish(ctx, result)
        except RunStopped:
            status = "stopped"
            if ctx:
                await self._finish_partial(ctx, "Stopped. I kept what was finished.")
        except LimitReached as e:
            status = "stopped"
            if ctx:
                msg = {"credits": "I stopped at the credit limit.", "time": "I stopped at the time limit.",
                       "steps": "I stopped at the step limit."}[e.kind]
                await self._finish_partial(ctx, msg, ask=True)
        except UserError as e:
            em.emit("error", text=str(e), retry=False)
            status = "error"
        except asyncio.TimeoutError:
            em.emit("error", text="That took too long, so I stopped it.", retry=True)
            status = "error"
        except OpenRouterError as e:
            em.emit("error", text=f"The AI service had a problem ({str(e)[:140]}). Credits for this step are refunded.", retry=True)
            status = "error"
        except Exception as e:  # never leave the screen hanging
            em.emit("error", text=f"Something went wrong on our side ({type(e).__name__}). Credits refunded.", retry=True)
            status = "error"
        finally:
            real = 0
            if ctx is not None:
                real = ctx.meter.credits if (held and status != "error") else 0
                if held:
                    charged = wallet.settle(self.db, user["id"], task_id, real, reason=f"{ctx.mode['id']}")
                    real = charged
                    em.emit("settled", charged=charged, released=max(0, ctx.task["max_credits"] - charged))
                self.active.pop(task_id, None)
                try:
                    workspace.cleanup_work(user["id"], task_id)
                except Exception:
                    pass
            self.db.run("UPDATE tasks SET status=?, finished_at=?, credits_used=? WHERE id=?",
                        (status, now(), real, task_id))
            if req.continue_task:
                self.db.run("UPDATE tasks SET status=? WHERE id=? AND user_id=? AND status='resuming'",
                            ("paused" if status in ("blocked", "error", "awaiting_confirm") else "continued",
                             req.continue_task, user["id"]))
            activity.log(self.db, user["id"], "run_finished", task_id=task_id, status=status, credits=real,
                         mode=ctx.mode["id"] if ctx else req.mode, files=len(ctx.files) if ctx else 0)
            em.emit("run_done", status=status, used=real,
                    max=ctx.task["max_credits"] if ctx else 0)
            em.close()
            if ctx is not None and status == "done":
                self._schedule(self.learn(ctx))

    def _schedule(self, coro) -> None:
        t = asyncio.create_task(coro)
        self.background.add(t)
        t.add_done_callback(self.background.discard)

    async def _finish_partial(self, ctx: RunContext, note: str, ask: bool = False) -> None:
        text = getattr(ctx, "best", "") or ""
        body = (text + "\n\n" if text else "") + f"_{note}_"
        await self.finish(ctx, RunResult(body, extra={"partial": True}), final_check=False)
        if ask:
            ctx.emit("ask", kind="more_credits", text=f"{note} Raise the cost cap and run again to keep going.",
                     used=ctx.meter.credits, max=ctx.task["max_credits"])

    # ---- check + teacher layer ----------------------------------------------------------
    async def finish(self, ctx: RunContext, result: RunResult, final_check: bool = True) -> None:
        from .postprocess import finalize
        separate_teacher = final_check and not result.paused and ctx.req.teacher_enabled and ctx.req.teacher_model
        if separate_teacher and len(result.text) > 16000:
            ctx.notices.append("The answer is too long for a separate teacher pass. The complete original answer is preserved.")
            ctx.emit("notice", text=ctx.notices[-1])
        if separate_teacher and len(result.text) <= 16000:
            model = ctx._pick(ctx.req.teacher_model, "teacher")
            ctx.emit("agent_start", agent="teacher", model=model["name"], effort="off", status="running")
            try:
                taught = await ctx.call("teacher", model, [
                    {"role": "system", "content": ctx.system_prompt() +
                     "\nRewrite the completed answer in the teaching style. Preserve every fact, source URL, "
                     "artifact marker, code block and file reference. Do not invent new evidence or tools."},
                    {"role": "user", "content": f"Question: {ctx.req.message[:3000]}\n\n"
                     f"Completed answer (reference data):\n<work>{result.text[:16000]}</work>"}],
                    max_tokens=2500, agent_id="teacher")
                preserved = re.findall(r"\[\[artifact:[^\]]+\]\]|https?://[^\s<>\)\]]+|```[\s\S]*?```", result.text)
                if taught.finish_reason == "length" or any(value not in taught.text for value in preserved):
                    raise UserError("The teacher pass did not preserve the complete answer and its references.")
                result.text = taught.text
                ctx.emit("agent_done", agent="teacher", status="done", credits=ctx.meter.credits)
            except (LimitReached, OpenRouterError, UserError, asyncio.TimeoutError):
                ctx.notices.append("The teacher pass could not finish within this run's limits. The original answer is preserved.")
                ctx.emit("notice", text=ctx.notices[-1])
                ctx.emit("agent_done", agent="teacher", status="skipped", credits=ctx.meter.credits)
        text, buttons, arts = await finalize(ctx, result.text)
        ctx.emit("text", delta=text, replace=True)  # also swaps streamed raw text for the cleaned version
        ctx.best = text
        mid = self.db.run(
            "INSERT INTO messages(conversation_id,role,content,meta,task_id,created_at) VALUES(?,?,?,?,?,?)",
            (ctx.req.conversation_id, "assistant", text,
             jdump({"artifacts": [a["id"] for a in arts], "files": [f["id"] for f in ctx.files], "buttons": buttons,
                    "mode": ctx.mode["id"], "notices": ctx.notices, "credits": min(ctx.meter.credits, ctx.task["max_credits"])}), ctx.task["id"], now())).lastrowid
        self.db.run("UPDATE conversations SET updated_at=? WHERE id=?", (now(), ctx.req.conversation_id))
        ctx.emit("answer", message_id=mid, buttons=buttons, credits=min(ctx.meter.credits,ctx.task["max_credits"]), notices=ctx.notices)

    # ---- learn (background): summary + profile -------------------------------------------
    async def learn(self, ctx: RunContext) -> None:
        user_id, conv_id = ctx.user["id"], ctx.req.conversation_id
        meter = Meter(self.db, user_id, ctx.task["id"], 10**6)  # platform cost, not billed to the user
        async def learn_call(*args, **kwargs):
            return await asyncio.wait_for(self.llm.chat(*args, **kwargs), timeout=15)
        try:
            q = ctx.quick()
            msgs = self.db.all("SELECT id,role,content FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,))
            conv = self.db.one("SELECT * FROM conversations WHERE id=?", (conv_id,))
            # Compaction: keep the last 6 word for word, summarize older ones every few turns.
            older = [m for m in msgs[:-RECENT_MESSAGES] if m["id"] > conv["summarized_upto"]]
            if len(older) >= 4:
                text = (conv["summary"] and f"Previous summary: {conv['summary']}\n\n" or "") + \
                       "\n".join(f"{m['role']}: {m['content'][:600]}" for m in older)
                res = await learn_call(q["id"], [{"role": "system", "content": prompts.get("summary")},
                                                    {"role": "user", "content": text[:8000]}], max_tokens=300,
                                          private=ctx.private, zdr=ctx.plan == "school",
                                          reasoning=build_reasoning(q, "off", 300),
                                          fallbacks=catalog.fallbacks(self.db, q["id"], private_only=ctx.private,
                                                                      tiers_allowed=ctx.rules["tiers"]))
                await meter.record("summary", q, res, billable=False)
                self.db.run("UPDATE conversations SET summary=?, summarized_upto=? WHERE id=?",
                            (res.text.strip()[:900], older[-1]["id"], conv_id))
            # Profile: every 3rd user turn, a cheap model updates the card.
            if sum(1 for m in msgs if m["role"] == "user") % 3 == 1:
                recent = "\n".join(f"{m['role']}: {m['content'][:500]}" for m in msgs[-4:])
                cur = jdump(ctx.profile) if ctx.profile else "{}"
                res = await learn_call(q["id"], [{"role": "system", "content": prompts.get("profile")},
                                                    {"role": "user", "content": f"Current profile: {cur}\n\nChat:\n{recent}"}],
                                          max_tokens=300, json_mode=True, private=ctx.private, zdr=ctx.plan == "school",
                                          reasoning=build_reasoning(q, "off", 300),
                                          fallbacks=catalog.fallbacks(self.db, q["id"], private_only=ctx.private,
                                                                      tiers_allowed=ctx.rules["tiers"]))
                await meter.record("profile", q, res, billable=False)
                new = parse_json(res.text)
                clean = {k: new[k] for k in ("level", "interests", "language", "likes", "weak_topics", "goal") if k in new}
                if clean:
                    self.db.run("INSERT OR REPLACE INTO profiles(user_id,data,updated_at) VALUES(?,?,?)",
                                (user_id, jdump({**ctx.profile, **clean}), now()))
        except Exception:
            pass  # learning is best effort and never blocks the user
        await self.learn_memory(ctx)

    async def learn_memory(self, ctx: RunContext) -> None:
        """After each answer, a cheap model updates long-term memory and this chat's session notes."""
        user = self.db.one("SELECT * FROM users WHERE id=?", (ctx.user["id"],)) or {}
        if not user.get("memory_enabled", 1):
            return
        conv_id = ctx.req.conversation_id
        try:
            q = ctx.quick()
            last = self.db.all("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 2", (conv_id,))
            exchange = "\n".join(f"{m['role']}: {m['content'][:1500]}" for m in reversed(last))
            saved = memory.listing(self.db, user["id"])[:40]
            conv = self.db.one("SELECT notes FROM conversations WHERE id=?", (conv_id,)) or {}
            prompt = (f"Saved memories:\n" + ("\n".join(f"{m['id']}: [{m['kind']}] {m['content']}" for m in saved) or "(none)") +
                      f"\n\nCurrent session notes:\n{conv.get('notes') or '(none)'}\n\nLatest exchange:\n{exchange}")
            res = await asyncio.wait_for(self.llm.chat(
                q["id"], [{"role": "system", "content": prompts.get("memory")}, {"role": "user", "content": prompt[:9000]}],
                max_tokens=500, json_mode=True, private=ctx.private, zdr=ctx.plan == "school",
                reasoning=build_reasoning(q, "off", 500),
                fallbacks=catalog.fallbacks(self.db, q["id"], private_only=ctx.private, tiers_allowed=ctx.rules["tiers"])), timeout=20)
            await Meter(self.db, user["id"], ctx.task["id"], 10**6).record("memory", q, res, billable=False)
            ops = parse_json(res.text)
            done = memory.apply_ops(self.db, user["id"], ops, conv_id)
            notes = str(ops.get("session_notes") or "").strip()[:1200]
            if notes:
                self.db.run("UPDATE conversations SET notes=? WHERE id=?", (notes, conv_id))
            if any(done.values()):
                activity.log(self.db, user["id"], "memory_learned", **done)
        except Exception:
            pass  # memory is best effort and never blocks the user
