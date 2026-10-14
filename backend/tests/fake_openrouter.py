"""A local stand-in for OpenRouter, used ONLY by tests. It follows the real request/response shape
(chat/completions with usage.cost, streaming, models list) and records every request so tests can
check the safety rails (max_tokens, provider.data_collection, reasoning, fallbacks)."""
import json

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.catalog import SEED

PRICES = {m[0]: (m[5], m[6]) for m in SEED}

RECIPE = {"chart": "line", "title": "How savings grow",
          "inputs": [{"id": "P", "label": "Start money", "type": "number", "value": 1000},
                     {"id": "r", "label": "Interest %", "type": "slider", "min": 0, "max": 20, "step": 0.5, "value": 5}],
          "x": {"label": "Year", "from": 0, "to": 10}, "lines": [{"name": "Money", "formula": "P*(1+r/100)^x"}]}
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 360"><rect x="10" y="10" width="100" height="50" fill="none" stroke="black"/><text x="20" y="40">Sun</text><script>alert(1)</script></svg>'


class FakeOpenRouter:
    def __init__(self):
        self.requests: list[dict] = []
        self.fail: dict[str, int] = {}          # model -> times to answer 500
        self.empty_length: dict[str, int] = {}  # model -> times to return empty text + finish length
        self.critic_scores = [5, 9]
        self.critic_calls = 0
        self.cost_mult = 1.0                    # make calls cost more, to hit the credit caps
        self.no_cost = False                    # drop usage.cost to test the table fallback
        self.app = self._build()

    def transport(self) -> httpx.ASGITransport:
        return httpx.ASGITransport(app=self.app)

    # ---- helpers for tests ------------------------------------------------------------------------
    def calls(self, contains: str = "") -> list[dict]:
        return [r for r in self.requests if contains in json.dumps(r["messages"])]

    # ---- content by role (decided from the system prompt) -------------------------------------------------
    def _reply(self, body: dict) -> str:
        msgs = body["messages"]
        sys = msgs[0]["content"] if msgs and msgs[0]["role"] == "system" else ""
        user = msgs[-1]["content"] if msgs else ""
        everything = " ".join(m["content"] for m in msgs if isinstance(m["content"], str))
        if "You route messages" in sys:
            return json.dumps({"intent": "teach", "needs": [], "complexity": "medium", "make_plan": False})
        if "You are the planner" in sys:
            return json.dumps({"steps": [
                {"title": "Work out the numbers", "kind": "calculate", "detail": "compute"},
                {"title": "Draw a chart", "kind": "chart", "detail": "chart"},
                {"title": "Write the answer", "kind": "answer", "detail": "final"}]})
        if "List the calculations" in sys:
            return json.dumps({"calcs": [{"label": "Money after 2 years", "expr": "1000*(1+5/100)^2"}]})
        if "Reply with the JSON recipe only" in sys:
            return json.dumps(RECIPE)
        if "Reply with the SVG only" in sys:
            return SVG
        if "strict checker" in sys:
            return json.dumps({"ok": True, "problem": "", "fix": ""})
        if "You mark answers" in sys:
            s = self.critic_scores[min(self.critic_calls, len(self.critic_scores) - 1)]
            self.critic_calls += 1
            return json.dumps({"score": s, "problems": ["Too long", "Add an example"] if s < 8 else []})
        if "Rewrite the answer so it fixes" in sys:
            return "Simple idea (rewritten): a seed grows into a plant.\n\n[[next: Explain simpler | Quiz me]]"
        if "the thinking half" in sys:
            return json.dumps({"plan": "p", "facts": ["f"], "steps": ["s"], "result": "42", "doubts": []})
        if "You are the judge" in sys:
            return "Both answers agree.\n\nWhere they agreed and disagreed: they agree.\n\n[[next: Explain simpler | Quiz me | Show a graph]]"
        if "Notes from" in sys:
            return "Final answer from the notes: 42.\n\n[[next: Explain simpler | Quiz me]]"
        if "web search questions" in sys:
            return json.dumps({"queries": ["what is x", "history of x"]})
        if "Search the web" in sys:
            return "Fact one (example.com). Fact two."
        if "Write the answer from the findings" in sys:
            return "Answer with a [link](https://example.com).\n\n[[next: Explain simpler | Quiz me]]"
        if "Summarize this chat" in sys:
            return "The user studied seeds."
        if "Update the user's learning profile" in sys:
            return json.dumps({"level": "beginner", "interests": ["cricket"], "language": "English", "likes": "short", "weak_topics": [], "goal": "pass"})
        if "outline for a slide deck" in sys:
            return json.dumps({"title": "How plants make food", "slides": [{"title": f"Slide {i}", "idea": "idea"} for i in range(1, 9)]})
        if "Write slide" in sys:
            n = int(sys.split("Write slide ")[1].split(" ")[0])
            bullets = ["Leaves catch sunlight and turn it into food for the whole plant every day"] * 7
            slide = {"title": f"Slide {n}", "bullets": bullets, "visual": {"type": "none", "prompt": ""}, "notes": "Ask a question."}
            if n == 2:
                slide["chart"] = RECIPE
            if n == 3:
                slide["bullets"] = []  # empty slide: the checker must catch it and fix it
            return json.dumps(slide)
        if "outline for a document" in sys:
            return json.dumps({"title": "Water Cycle", "sections": [{"heading": f"Part {i}", "goal": "g"} for i in range(1, 6)]})
        if "Write one section" in sys:
            return json.dumps({"heading": "Part", "paragraphs": ["Water goes up and comes down."], "bullets": ["rain"]})
        if "Pick the skill" in sys:
            return json.dumps({"skill": "none"})
        if "Fix this" in sys:
            if "chart" in sys:
                return json.dumps(RECIPE)
            if "svg" in sys:
                return SVG.replace("<script>alert(1)</script>", "")
            return json.dumps({"questions": [{"q": "Q?", "options": ["a", "b"], "answer": 0, "why": "w"}]})
        # default: the tutor answer
        text = "Simple idea: a plant makes food from sunlight, like a solar-powered kitchen.\n\n"
        low = user.lower() if isinstance(user, str) else ""
        if "calc" in low or "interest" in low:
            text += "After 2 years you have {{calc: 1000*(1+5/100)^2}} dollars.\n\n"
        if "bad chart" in low:
            text += '```chart\n{"chart":"line","title":"bad","x":{"from":0,"to":1},"lines":[{"name":"a","formula":"zzz+1"}]}\n```\n\n'
        elif "chart" in low and "chart recipe" in sys:
            text += "```chart\n" + json.dumps(RECIPE) + "\n```\n\n"
        if "quiz" in low and "quiz" in sys:
            text += '```quiz\n{"questions":[{"q":"What do plants eat?","options":["Light","Rocks"],"answer":0,"why":"They use sunlight."}]}\n```\n\n'
        if "diagram" in low and "svg" in sys:
            text += "```svg\n" + SVG + "\n```\n\n"
        text += "Check question: where does a plant get its energy?\n\n[[next: Explain simpler | Quiz me | Show a graph]]"
        return text

    def _build(self) -> FastAPI:
        app = FastAPI()

        @app.get("/models")
        def models():
            data = []
            for mid, (pin, pout) in PRICES.items():
                if mid in ("anthropic/claude-fable-5.1",):
                    continue  # one catalog model "disappears" from the live list
                data.append({"id": mid, "name": mid, "context_length": 128000,
                             "pricing": {"prompt": str(pin / 1e6), "completion": str(pout / 1e6)},
                             "supported_parameters": ["reasoning", "max_tokens"]})
            data.append({"id": "newlab/new-model", "name": "New Model", "context_length": 32000,
                         "pricing": {"prompt": "0.0000005", "completion": "0.000002"}, "supported_parameters": ["reasoning"]})
            return {"data": data}

        @app.post("/chat/completions")
        async def chat(request: Request):
            body = await request.json()
            self.requests.append(body)
            model = body["model"]
            if self.fail.get(model, 0) > 0:
                self.fail[model] -= 1
                return JSONResponse({"error": {"message": "upstream down", "code": 500}}, status_code=500)
            empty = self.empty_length.get(model, 0) > 0
            if empty:
                self.empty_length[model] -= 1
            text = "" if empty else self._reply(body)
            tin = sum(len(m["content"]) for m in body["messages"] if isinstance(m["content"], str)) // 4 + 10
            reasoning = 0
            if body.get("reasoning") and body["reasoning"].get("effort") != "none":
                reasoning = 300
            tout = len(text) // 4 + 5 + reasoning
            pin, pout = PRICES.get(model, (1.0, 1.0))
            usage = {"prompt_tokens": tin, "completion_tokens": tout, "total_tokens": tin + tout,
                     "completion_tokens_details": {"reasoning_tokens": reasoning}, "prompt_tokens_details": {"cached_tokens": 0}}
            if not self.no_cost:
                usage["cost"] = (tin * pin + tout * pout) / 1e6 * self.cost_mult
            finish = "length" if empty else "stop"
            if body.get("stream"):
                def gen():
                    for i in range(0, len(text), 40):
                        yield "data: " + json.dumps({"model": model, "choices": [{"delta": {"content": text[i:i + 40]}}]}) + "\n\n"
                    yield "data: " + json.dumps({"model": model, "choices": [{"delta": {}, "finish_reason": finish}], "usage": usage}) + "\n\n"
                    yield "data: [DONE]\n\n"
                return StreamingResponse(gen(), media_type="text/event-stream")
            return {"model": model, "choices": [{"message": {"role": "assistant", "content": text, "reasoning": "thinking..." if reasoning else None},
                                                 "finish_reason": finish}], "usage": usage}

        return app
