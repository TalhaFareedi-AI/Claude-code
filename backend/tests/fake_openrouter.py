"""A local stand-in for OpenRouter, used ONLY by tests. It follows the real request/response shape
(chat/completions with usage.cost, streaming, models list) and records every request so tests can
check the safety rails (max_tokens, provider.data_collection, reasoning, fallbacks)."""
import asyncio
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
CNN_SPEC = {
    "title": "Small CNN for handwritten digits",
    "nodes": [
        {"id": "in", "label": "Input image", "input": "a photo of one digit", "process": "turn pixels into numbers", "output": "1 x 28 x 28"},
        {"id": "c1", "label": "Conv 3x3, 16 filters, ReLU", "input": "1 x 28 x 28", "process": "find edges and strokes", "output": "16 x 28 x 28"},
        {"id": "p1", "label": "Max pool 2x2", "input": "16 x 28 x 28", "process": "keep strongest value in each 2x2 square", "output": "16 x 14 x 14"},
        {"id": "c2", "label": "Conv 3x3, 32 filters, ReLU", "input": "16 x 14 x 14", "process": "find shapes like loops and lines", "output": "32 x 14 x 14"},
        {"id": "p2", "label": "Max pool 2x2", "input": "32 x 14 x 14", "process": "shrink again", "output": "32 x 7 x 7"},
        {"id": "fc", "label": "Flatten + Dense", "input": "32 x 7 x 7 = 1,568 numbers", "process": "weigh all the features", "output": "10 scores"},
        {"id": "out", "label": "Softmax", "input": "10 scores", "process": "turn scores into chances", "output": "chance of each digit, 0 to 9"},
    ],
    "edges": [["in", "c1"], ["c1", "p1"], ["p1", "c2"], ["c2", "p2"], ["p2", "fc"], ["fc", "out"]],
    "explanation": "Each convolution layer finds features and each pooling layer halves the width and height.",
    "options": [{"name": "2-Layer CNN", "cost": "Low", "risk": "Low", "why": "Fast and accurate on 28x28 digits."}],
}


def as_text(content) -> str:
    """A cached system prompt arrives as a list of blocks, so flatten it before matching."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


class FakeOpenRouter:
    def __init__(self):
        self.requests: list[dict] = []
        self.fail: dict[str, int] = {}          # model -> times to answer 500
        self.empty_length: dict[str, int] = {}  # model -> times to return empty text + finish length
        self.critic_scores = [5, 9]
        self.critic_calls = 0
        self.cost_mult = 1.0                    # make calls cost more, to hit the credit caps
        self.delay = 0.0                        # seconds per call, to watch animations
        self.image_block = False                # answer asks for a generated picture
        self.returns_image = False              # the image model returns a real PNG
        self.doc_block = False                  # answer with a saved document
        self.slides_block = False               # answer with a saved deck
        self.force_length_once = False          # first reply is cut off, to test the continuation
        self.extra_blocks = False               # emit flashcard and table blocks in the default answer
        self.memory_add = False                 # let the memory model propose a new memory
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
        sys = as_text(msgs[0]["content"]) if msgs and msgs[0]["role"] == "system" else ""
        user = as_text(msgs[-1]["content"]) if msgs else ""
        everything = " ".join(as_text(m["content"]) for m in msgs)
        if "task router" in sys:
            return json.dumps({"intent": "teach", "needs": [], "complexity": "medium", "make_plan": False})
        if "Restate a user's task precisely" in sys:
            needs_arch = any(w in user.lower() for w in ("cnn", "transformer", "mamba", "d3 diagram", "architecture"))
            return json.dumps({"goal": user[:400], "enhanced_prompt": user[:1000], "teach_level": "light",
                               "needs_architecture": needs_arch, "constraints": [],
                               "missing": [], "research": False, "files": False, "queries": []})
        if "Rewrite the user's task into a clear" in sys:
            return json.dumps({"enhanced_prompt": user[:1000], "next_buttons": ["Show a graph", "Quiz me", "Explain simpler"]})
        if "Architecture agent (section 16)" in sys:
            return json.dumps(CNN_SPEC)
        if "critic sub-agent (section 16)" in sys:
            return json.dumps({"role": "math", "verdict": "pass", "confidence": "high",
                               "finding": "All calculations and steps verified.", "evidence": "28 / 2 = 14", "fix": ""})
        if "harness editor in the Recursive Harness" in sys:
            return json.dumps({"scope": "general", "observation": "Re-verify section numbers and table outputs.",
                               "edits": {"system_rule": "Include at least one verified number per section.",
                                         "guardrail": "Re-open and verify generated tables."}})
        if "Composer agent in the Recursive Harness" in sys:
            return json.dumps({"decision": "merge", "observation": "Both general and topic probe runs improved accuracy.",
                               "system_rule": "Include at least one verified number per section.",
                               "guardrail": "Re-open and verify generated tables.",
                               "tool_guidance": "Use calculator for numbers over 3 digits.",
                               "summary": "Merged general verification rule with topic rule into H1."})
        if "Reflector agent in the Recursive Harness" in sys:
            return json.dumps({"write_lesson": True, "topic": "reports",
                               "text": "Every section needs at least one verified number with a source.",
                               "evidence": "Probe run passed all checks.", "scope": "personal"})
        if "shortest plan" in sys or "bounded agent team" in sys:   # the mode planner and the team planner
            return json.dumps({"steps": [
                {"title": "Work out the numbers", "kind": "calculate", "detail": "compute"},
                {"title": "Draw a chart", "kind": "chart", "detail": "chart"},
                {"title": "Write the answer", "kind": "answer", "detail": "final"}]})
        if "List every calculation" in sys:
            return json.dumps({"calcs": [{"label": "Money after 2 years", "expr": "1000*(1+5/100)^2"}]})
        if "Reply with the JSON recipe only" in sys:
            return json.dumps(RECIPE)
        if "Reply with the SVG only" in sys:
            return SVG
        if "check an answer before the user sees it" in sys or "strict checker for one step" in sys:
            return json.dumps({"ok": True, "problem": "", "fix": ""})
        if "Score an answer" in sys:
            s = self.critic_scores[min(self.critic_calls, len(self.critic_scores) - 1)]
            self.critic_calls += 1
            return json.dumps({"score": s, "problems": ["Too long", "Add an example"] if s < 8 else []})
        if "Rewrite the answer so it fixes" in sys:
            return "Simple idea (rewritten): a seed grows into a plant.\n\n[[next: Explain simpler | Quiz me]]"
        if "the thinking half" in sys:
            return json.dumps({"plan": "p", "facts": ["f"], "steps": ["s"], "result": "42", "doubts": []})
        if "independent answers to the same question" in sys:
            return "Both answers agree.\n\nWhere they agreed and disagreed: they agree.\n\n[[next: Explain simpler | Quiz me | Show a graph]]"
        if "Notes from" in sys:
            return "Final answer from the notes: 42.\n\n[[next: Explain simpler | Quiz me]]"
        if "web search questions" in sys:
            return json.dumps({"queries": ["what is x", "history of x"]})
        if "Search the web" in sys:
            return "Fact one (example.com). Fact two."
        if "Write the answer from the findings" in sys:
            return "Answer with a [link](https://example.com).\n\n[[next: Explain simpler | Quiz me]]"
        if "long-term memory of a study assistant" in sys:
            add = [{"kind": "preference", "content": "Likes cricket examples", "importance": 4}] if self.memory_add else []
            return json.dumps({"add": add, "update": [], "forget": [], "session_notes": "Studied seeds. Open question: roots."})
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
        if "d3_diagram" in low or "cnn" in low:
            text += "```d3_diagram\n" + json.dumps(CNN_SPEC) + "\n```\n\n"
        if "waveform" in low or "science_plot" in low:
            text += '```science_plot\n{"kind":"waveform","title":"5 Hz Sine Wave and FFT Spectrum","freq":5,"amp":1,"duration":1}\n```\n\n'
        if self.image_block or ("write ONE fenced block tagged image" in sys and "draw" in low):
            text += "```image\nA labelled cross-section of a leaf, flat vector style, white background\n```\n\n"
        if self.doc_block or ("ONE fenced block tagged doc" in sys and "document" in low):
            text += ('```doc title="AI Learning Guide"\n# AI Learning Guide\n\n## The core idea\n'
                     'A model learns patterns from examples instead of hand written rules.\n\n'
                     '## Why it matters\nIt generalises to data it has never seen.\n```\n\n')
        if self.slides_block or ("ONE fenced block tagged slides" in sys and "deck" in low):
            text += ('```slides title="Water"\n# Water\nA short deck\n\n---\n\n## It falls\n- Rain\n\n---\n\n'
                     '## It rises\n- Evaporation\n```\n\n')
        if self.extra_blocks:
            text += '```flashcards\n{"title":"Deck","cards":[{"front":"Q1","back":"A1"},{"front":"Q2","back":"A2"},{"front":"Q3","back":"A3"}]}\n```\n\n'
            text += '```table\n{"title":"Compare","columns":[{"key":"n","label":"Name"},{"key":"v","label":"Value","type":"number"}],"rows":[{"n":"a","v":1},{"n":"b","v":2}]}\n```\n\n'
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
            for mid, name, pin, pout in [("google/gemini-3.1-flash-image", "Nano Banana 2", "0.0000005", "0.000003"),
                                         ("google/gemini-3-pro-image", "Nano Banana Pro", "0.000002", "0.000012")]:
                data.append({"id": mid, "name": name, "context_length": 32000,
                             "pricing": {"prompt": pin, "completion": pout}, "supported_parameters": [],
                             "architecture": {"output_modalities": ["image", "text"]}})
            return {"data": data}

        @app.post("/chat/completions")
        async def chat(request: Request):
            body = await request.json()
            self.requests.append(body)
            if self.delay:
                await asyncio.sleep(self.delay)
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
            searched = any(tool.get("type") == "openrouter:web_search" for tool in body.get("tools", []))
            if searched:
                usage["server_tool_use"] = {"web_search_requests": 1}
            if not self.no_cost:
                usage["cost"] = (tin * pin + tout * pout) / 1e6 * self.cost_mult
            finish = "length" if empty else "stop"
            if self.force_length_once and not empty:
                self.force_length_once = False
                finish = "length"
            if body.get("modalities"):  # an image model always answers with a picture
                import base64 as _b64
                png = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes" * 8
                data = "data:image/png;base64," + _b64.b64encode(png).decode()
                return {"model": model, "choices": [{"message": {"role": "assistant", "content": "Here is the image.",
                        "images": [{"image_url": {"url": data}}]}, "finish_reason": "stop"}], "usage": usage}
            if body.get("stream"):
                def gen():
                    for i in range(0, len(text), 40):
                        yield "data: " + json.dumps({"model": model, "choices": [{"delta": {"content": text[i:i + 40]}}]}) + "\n\n"
                    if searched:
                        yield "data: " + json.dumps({"model": model, "choices": [{"delta": {"annotations": [
                            {"type": "url_citation", "url_citation": {"url": "https://example.com", "title": "Example source"}}]}}]}) + "\n\n"
                    yield "data: " + json.dumps({"model": model, "choices": [{"delta": {}, "finish_reason": finish}], "usage": usage}) + "\n\n"
                    yield "data: [DONE]\n\n"
                return StreamingResponse(gen(), media_type="text/event-stream")
            return {"model": model, "choices": [{"message": {"role": "assistant", "content": text, "reasoning": "thinking..." if reasoning else None,
                        "annotations": [{"type": "url_citation", "url_citation": {"url": "https://example.com", "title": "Example source"}}] if searched else []},
                                                 "finish_reason": finish}], "usage": usage}

        return app
