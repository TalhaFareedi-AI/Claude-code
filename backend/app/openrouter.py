"""The one door for every AI call (section 10). Thin wrapper over OpenRouter's chat API.

Every setting here is either a safety rail or a bill counter:
  max_tokens         hard cap on the reply, thinking included
  usage.include      asks OpenRouter for the real cost (usage.cost)
  reasoning          effort OR max_tokens (never both), only for models that think
  models             backup models, used only if the first one fails
  provider           privacy: data_collection=deny, zdr, require_parameters
"""
import asyncio
import json
from dataclasses import dataclass, field

import httpx

from .config import settings
from .pricing import EFFORT_API, EFFORT_SHARE


class OpenRouterError(Exception):
    def __init__(self, message: str, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status, self.body = status, body


@dataclass
class Usage:
    prompt: int = 0          # new (non-cached) input tokens
    cached: int = 0
    completion: int = 0      # includes reasoning tokens
    reasoning: int = 0
    cost: float | None = None  # dollars, from usage.cost


@dataclass
class LLMResult:
    text: str
    model: str
    usage: Usage
    finish_reason: str = ""
    reasoning_text: str = ""
    images: list = field(default_factory=list)
    sources: list = field(default_factory=list)  # web-search citations: {url, title}


def build_reasoning(model: dict | None, effort: str, max_tokens: int) -> dict | None:
    """Return the `reasoning` object for this model, or None.

    Only send it to models that think. Models that take a level get `effort`.
    Models that take a budget (Claude, Gemini, some Qwen) get `max_tokens`. Never both.
    """
    if not model or not model.get("thinks") or effort in (None, "auto"):
        return None
    if effort == "off":
        return {"effort": "none"} if model.get("reasoning_style") == "effort" else {"enabled": False}
    if model.get("reasoning_style") == "budget":
        budget = int(max_tokens * EFFORT_SHARE.get(effort, 0.5))
        # Providers want at least 1024 and room left for the answer.
        budget = max(1024, min(budget, max_tokens - 256))
        if max_tokens < 1280:
            return None
        return {"max_tokens": budget}
    return {"effort": EFFORT_API.get(effort, "medium")}


class OpenRouter:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None, timeout: float = 120.0):
        self.api_key = api_key if api_key is not None else settings.openrouter_api_key
        self.base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict:
        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY is not set")
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                "HTTP-Referer": "https://localhost/study-harness", "X-Title": settings.app_title}

    def _body(self, model: str, messages: list, *, max_tokens: int, reasoning: dict | None = None,
              fallbacks: list[str] | None = None, json_mode: bool = False, private: bool = False,
              zdr: bool = False, plugins: list | None = None, modalities: list | None = None,
              temperature: float | None = None, stream: bool = False) -> dict:
        body: dict = {"model": model, "messages": messages, "max_tokens": max_tokens,
                      "usage": {"include": True}}
        if fallbacks:
            body["models"] = [model] + [m for m in fallbacks if m != model]
        if reasoning:
            body["reasoning"] = reasoning
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if plugins:
            body["plugins"] = plugins
        if modalities:
            body["modalities"] = modalities
        if temperature is not None:
            body["temperature"] = temperature
        provider: dict = {"data_collection": "deny"}  # plan: on every request
        if json_mode or reasoning:
            provider["require_parameters"] = True
        if zdr or private:
            provider["zdr"] = True
        body["provider"] = provider
        if stream:
            body["stream"] = True
        return body

    async def chat(self, model: str, messages: list, *, max_tokens: int = 1000, retries: int = 2, **kw) -> LLMResult:
        body = self._body(model, messages, max_tokens=max_tokens, **kw)
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                r = await self._client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=body)
            except httpx.HTTPError as e:
                last = OpenRouterError(f"network error: {e}")
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                last = OpenRouterError(f"upstream {r.status_code}", r.status_code, r.text[:300])
                await asyncio.sleep(0.8 * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise OpenRouterError(_err_text(r), r.status_code, r.text[:500])
            return self._parse(r.json(), model)
        raise last or OpenRouterError("request failed")

    async def chat_stream(self, model: str, messages: list, *, max_tokens: int = 1000, on_delta=None, **kw) -> LLMResult:
        """Stream the answer. `on_delta(text)` is awaited for each piece."""
        body = self._body(model, messages, max_tokens=max_tokens, stream=True, **kw)
        text, reasoning, usage, finish, used_model = [], [], Usage(), "", model
        async with self._client.stream("POST", f"{self.base_url}/chat/completions",
                                       headers=self._headers(), json=body) as r:
            if r.status_code >= 400:
                raw = (await r.aread()).decode("utf-8", "ignore")
                raise OpenRouterError(f"upstream {r.status_code}: {raw[:200]}", r.status_code, raw[:500])
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                if chunk.get("error"):
                    raise OpenRouterError(str(chunk["error"])[:200])
                used_model = chunk.get("model") or used_model
                if chunk.get("usage"):
                    usage = _usage(chunk["usage"])
                for ch in chunk.get("choices") or []:
                    d = ch.get("delta") or {}
                    if d.get("content"):
                        text.append(d["content"])
                        if on_delta:
                            await on_delta(d["content"])
                    if d.get("reasoning"):
                        reasoning.append(d["reasoning"])
                    if ch.get("finish_reason"):
                        finish = ch["finish_reason"]
        return LLMResult("".join(text), used_model, usage, finish, "".join(reasoning))

    @staticmethod
    def _parse(data: dict, model: str) -> LLMResult:
        if data.get("error"):
            e = data["error"]
            raise OpenRouterError(e.get("message", str(e)) if isinstance(e, dict) else str(e),
                                  e.get("code", 0) if isinstance(e, dict) and isinstance(e.get("code"), int) else 0)
        choices = data.get("choices") or []
        if not choices:
            raise OpenRouterError("empty response from model")
        ch = choices[0]
        msg = ch.get("message") or {}
        content = msg.get("content") or ""
        if isinstance(content, list):  # some hosts return parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        sources = []
        for a in msg.get("annotations") or []:
            c = a.get("url_citation") if isinstance(a, dict) else None
            if c and c.get("url", "").startswith(("http://", "https://")):
                sources.append({"url": c["url"], "title": str(c.get("title", ""))[:120]})
        return LLMResult(content, data.get("model") or model, _usage(data.get("usage") or {}),
                         ch.get("finish_reason") or ch.get("native_finish_reason") or "",
                         msg.get("reasoning") or "", msg.get("images") or [], sources)

    async def list_models(self) -> list[dict]:
        r = await self._client.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})
        if r.status_code >= 400:
            raise OpenRouterError(_err_text(r), r.status_code)
        return r.json().get("data", [])

    async def key_info(self) -> dict:
        r = await self._client.get(f"{self.base_url}/auth/key", headers=self._headers())
        if r.status_code >= 400:
            raise OpenRouterError(_err_text(r), r.status_code)
        return r.json().get("data", {})


def _usage(u: dict) -> Usage:
    details = u.get("prompt_tokens_details") or {}
    cached = int(details.get("cached_tokens") or 0)
    comp_details = u.get("completion_tokens_details") or {}
    prompt_total = int(u.get("prompt_tokens") or 0)
    return Usage(prompt=max(0, prompt_total - cached), cached=cached,
                 completion=int(u.get("completion_tokens") or 0),
                 reasoning=int(comp_details.get("reasoning_tokens") or 0),
                 cost=float(u["cost"]) if u.get("cost") is not None else None)


def _err_text(r: httpx.Response) -> str:
    try:
        e = r.json().get("error", {})
        return f"{r.status_code}: {e.get('message', r.text[:200])}"
    except Exception:
        return f"{r.status_code}: {r.text[:200]}"
