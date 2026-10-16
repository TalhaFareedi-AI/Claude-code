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
import math
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import httpx

from .config import settings
from .pricing import EFFORT_API, EFFORT_SHARE


class OpenRouterError(Exception):
    def __init__(self, message: str, status: int = 0, body: str = "", *, usage=None,
                 partial_text: str = ""):
        super().__init__(_clean_error(message))
        self.status, self.body = status, _clean_error(body)
        self.usage, self.partial_text = usage, partial_text


@dataclass
class Usage:
    prompt: int = 0          # new (non-cached) input tokens
    cached: int = 0
    completion: int = 0      # includes reasoning tokens
    reasoning: int = 0
    cost: float | None = None  # dollars, from usage.cost
    searches: int | None = None  # None means the provider did not report search usage


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

    def _safe_error(self, error: OpenRouterError) -> OpenRouterError:
        if self.api_key:
            error.args = (str(error).replace(self.api_key, "[redacted]"),)
            error.body = error.body.replace(self.api_key, "[redacted]")
        return error

    def _headers(self) -> dict:
        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY is not set")
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                "HTTP-Referer": "https://localhost/study-harness", "X-Title": settings.app_title}

    def _body(self, model: str, messages: list, *, max_tokens: int, reasoning: dict | None = None,
              fallbacks: list[str] | None = None, json_mode: bool = False, private: bool = False,
              zdr: bool = False, plugins: list | None = None, modalities: list | None = None,
              temperature: float | None = None, stream: bool = False,
              tools: list[dict] | None = None, max_tool_calls: int | None = None,
              stop_server_tools_when: list[dict] | None = None) -> dict:
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            raise ValueError("max_tokens must be a positive integer")
        if max_tool_calls is not None and (isinstance(max_tool_calls, bool)
                or not isinstance(max_tool_calls, int) or not 1 <= max_tool_calls <= 30):
            raise ValueError("max_tool_calls must be an integer from 1 to 30")
        if stop_server_tools_when is not None:
            _validate_server_tool_stops(stop_server_tools_when)
        body: dict = {"model": model, "messages": mark_cacheable(model, messages), "max_tokens": max_tokens,
                      "usage": {"include": True}}
        if fallbacks:
            body["models"] = [model] + [m for m in fallbacks if m != model]
        if reasoning:
            body["reasoning"] = reasoning
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if plugins:
            body["plugins"] = plugins
        if tools:
            body["tools"] = tools
        if max_tool_calls is not None:
            body["max_tool_calls"] = max_tool_calls
        if stop_server_tools_when is not None:
            # These OR conditions override max_tool_calls. The caller must include
            # step_count_is as well as max_cost to retain its search-count budget.
            # max_cost is a soft threshold: pending tools and one final inference
            # may still run after it fires; reserve that cost before the request.
            body["stop_server_tools_when"] = stop_server_tools_when
        if modalities:
            body["modalities"] = modalities
        if temperature is not None:
            body["temperature"] = temperature
        provider: dict = {"data_collection": "deny"}  # plan: on every request
        if json_mode or reasoning or tools:
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
                last = self._safe_error(OpenRouterError(f"network error: {e}"))
                if attempt < retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                last = self._safe_error(OpenRouterError(f"upstream {r.status_code}", r.status_code, r.text[:300]))
                await asyncio.sleep(0.8 * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise self._safe_error(OpenRouterError(_err_text(r), r.status_code, r.text[:500]))
            try:
                data = r.json()
            except ValueError as e:
                raise OpenRouterError("invalid JSON response from model", r.status_code) from e
            try:
                return self._parse(data, model)
            except OpenRouterError as e:
                raise self._safe_error(e)
        raise last or OpenRouterError("request failed")

    async def chat_stream(self, model: str, messages: list, *, max_tokens: int = 1000, on_delta=None, **kw) -> LLMResult:
        """Stream the answer. `on_delta(text)` is awaited for each piece."""
        body = self._body(model, messages, max_tokens=max_tokens, stream=True, **kw)
        text, reasoning, usage_data, finish, used_model = [], [], {}, "", model
        sources, images = [], []
        received_choice, done = False, False
        try:
            async with self._client.stream("POST", f"{self.base_url}/chat/completions",
                                           headers=self._headers(), json=body) as r:
                if r.status_code >= 400:
                    raw = (await r.aread()).decode("utf-8", "ignore")
                    raise OpenRouterError(f"upstream {r.status_code}: {raw[:200]}", r.status_code, raw[:500])
                async for data in _sse_data(r.aiter_lines()):
                    if data.strip() == "[DONE]":
                        done = True
                        break
                    try:
                        chunk = json.loads(data)
                    except ValueError as e:
                        raise OpenRouterError("invalid JSON in model stream") from e
                    if not isinstance(chunk, dict):
                        raise OpenRouterError("invalid response in model stream")
                    if isinstance(chunk.get("usage"), dict):
                        _merge(usage_data, chunk["usage"])
                    _raise_error(chunk.get("error"))
                    used_model = chunk.get("model") or used_model
                    sources.extend(_sources(chunk))
                    for ch in chunk.get("choices") or []:
                        if not isinstance(ch, dict):
                            raise OpenRouterError("invalid choice in model stream")
                        # This gateway requests one answer. Never interleave alternate choices.
                        if ch.get("index", 0) != 0:
                            continue
                        received_choice = True
                        _raise_error(ch.get("error"))
                        d = ch.get("delta") or ch.get("message") or {}
                        if not isinstance(d, dict):
                            raise OpenRouterError("invalid message in model stream")
                        content = _content(d.get("content"))
                        if content:
                            text.append(content)
                            if on_delta:
                                await on_delta(content)
                        reason = _reasoning(d)
                        if reason:
                            reasoning.append(reason)
                        sources.extend(_sources(d))
                        for img in d.get("images") or []:
                            if img not in images:
                                images.append(img)
                        if ch.get("finish_reason") or ch.get("native_finish_reason"):
                            finish = ch.get("finish_reason") or ch["native_finish_reason"]
                            if finish == "error":
                                raise OpenRouterError("model stream ended with an error")
                if not received_choice:
                    raise OpenRouterError("empty response from model stream")
                if not done and not finish:
                    raise OpenRouterError("model stream ended before completion")
        except (OpenRouterError, httpx.HTTPError) as e:
            error = e if isinstance(e, OpenRouterError) else OpenRouterError(f"network error: {e}")
            error.usage = _usage(usage_data) if usage_data else None
            error.partial_text = "".join(text)
            raise self._safe_error(error) from (e if error is not e else None)
        return LLMResult("".join(text), used_model, _usage(usage_data), finish,
                         "".join(reasoning), images, _dedupe_sources(sources))

    @staticmethod
    def _parse(data: dict, model: str) -> LLMResult:
        if not isinstance(data, dict):
            raise OpenRouterError("invalid response from model")
        usage = _usage(data.get("usage") or {})
        error_usage = usage if data.get("usage") else None
        _raise_error(data.get("error"), usage=error_usage)
        choices = data.get("choices") or []
        if not choices or not isinstance(choices, list) or not isinstance(choices[0], dict):
            raise OpenRouterError("empty response from model", usage=error_usage)
        ch = choices[0]
        msg = ch.get("message") or {}
        if not isinstance(msg, dict):
            raise OpenRouterError("invalid message from model", usage=error_usage)
        _raise_error(ch.get("error"), usage=error_usage)
        if ch.get("finish_reason") == "error":
            raise OpenRouterError("model ended with an error", usage=error_usage)
        sources = _dedupe_sources(_sources(msg) + _sources(data))
        return LLMResult(_content(msg.get("content")), data.get("model") or model, usage,
                         ch.get("finish_reason") or ch.get("native_finish_reason") or "",
                         _reasoning(msg), msg.get("images") or [], sources)

    async def list_models(self) -> list[dict]:
        r = await self._client.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})
        if r.status_code >= 400:
            raise self._safe_error(OpenRouterError(_err_text(r), r.status_code))
        return r.json().get("data", [])

    async def key_info(self) -> dict:
        r = await self._client.get(f"{self.base_url}/auth/key", headers=self._headers())
        if r.status_code >= 400:
            raise self._safe_error(OpenRouterError(_err_text(r), r.status_code))
        return r.json().get("data", {})


# Anthropic models only cache a prefix when it is marked; DeepSeek, OpenAI, Gemini, Grok and Moonshot cache on their own.
CACHE_MARK_PREFIXES = ("anthropic/",)
CACHE_MIN_CHARS = 2000  # roughly 1,000 tokens: below the provider minimum a mark just wastes a write


def mark_cacheable(model: str, messages: list) -> list:
    """Mark the stable system prefix so a repeat within the cache window is billed at a fraction of the price.

    Only the system message is marked: it is identical across turns, while the user turn never repeats.
    """
    if not model.startswith(CACHE_MARK_PREFIXES) or not messages:
        return messages
    first = messages[0]
    if first.get("role") != "system" or not isinstance(first.get("content"), str):
        return messages
    if len(first["content"]) < CACHE_MIN_CHARS:
        return messages
    marked = {**first, "content": [{"type": "text", "text": first["content"],
                                    "cache_control": {"type": "ephemeral"}}]}
    return [marked, *messages[1:]]


def _usage(u: dict) -> Usage:
    if not isinstance(u, dict):
        raise OpenRouterError("invalid usage from model")
    details = u.get("prompt_tokens_details") or u.get("input_tokens_details") or {}
    comp_details = u.get("completion_tokens_details") or u.get("output_tokens_details") or {}
    server = u.get("server_tool_use_details") or u.get("server_tool_use") or {}
    if not all(isinstance(part, dict) for part in (details, comp_details, server)):
        raise OpenRouterError("invalid usage details from model")
    cached = _count(details.get("cached_tokens"))
    prompt_total = _count(u.get("prompt_tokens", u.get("input_tokens")))
    searches = server.get("web_search_requests")
    if searches is None:
        searches = (u.get("server_tool_use") or {}).get("web_search_requests")
    cost = u.get("cost")
    if cost is not None:
        try:
            cost = float(cost)
        except (ValueError, TypeError) as e:
            raise OpenRouterError("invalid cost in model usage") from e
        if not math.isfinite(cost) or cost < 0:
            raise OpenRouterError("invalid cost in model usage")
    return Usage(prompt=max(0, prompt_total - cached), cached=cached,
                 completion=_count(u.get("completion_tokens", u.get("output_tokens"))),
                 reasoning=_count(comp_details.get("reasoning_tokens")), cost=cost,
                 searches=_count(searches) if searches is not None else None)


def _count(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError) as e:
        raise OpenRouterError("invalid token or search count in model usage") from e


def _validate_server_tool_stops(conditions) -> None:
    if not isinstance(conditions, list) or not conditions:
        raise ValueError("stop_server_tools_when must be a nonempty list")
    for condition in conditions:
        if not isinstance(condition, dict):
            raise ValueError("server-tool stop conditions must be objects")
        kind = condition.get("type")
        if kind == "step_count_is":
            steps = condition.get("step_count")
            if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 30:
                raise ValueError("step_count must be an integer from 1 to 30")
            allowed = {"type", "step_count"}
        elif kind == "max_cost":
            cost = condition.get("max_cost_in_dollars")
            if (isinstance(cost, bool) or not isinstance(cost, (float, int))
                    or not math.isfinite(cost) or cost <= 0):
                raise ValueError("max_cost_in_dollars must be a positive finite number")
            allowed = {"type", "max_cost_in_dollars"}
        else:
            raise ValueError("unsupported server-tool stop condition")
        if set(condition) != allowed:
            raise ValueError("unexpected fields in server-tool stop condition")


def _content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p["text"] for p in content if isinstance(p, dict) and isinstance(p.get("text"), str))
    return ""


def _reasoning(message: dict) -> str:
    text = message.get("reasoning") or message.get("reasoning_content")
    if isinstance(text, str):
        return text
    return "".join(d["text"] for d in message.get("reasoning_details") or []
                   if isinstance(d, dict) and d.get("type") == "reasoning.text" and isinstance(d.get("text"), str))


def _sources(message: dict) -> list[dict]:
    citations = [a.get("url_citation") for a in message.get("annotations") or [] if isinstance(a, dict)]
    # Some search-native models still return their citations as a URL array.
    citations.extend({"url": u} if isinstance(u, str) else u for u in message.get("citations") or [])
    content = message.get("content")
    for part in content if isinstance(content, list) else []:
        if isinstance(part, dict):
            citations.extend(a.get("url_citation") for a in part.get("annotations") or [] if isinstance(a, dict))
    return [c for c in citations if isinstance(c, dict)]


def _dedupe_sources(sources: list[dict]) -> list[dict]:
    out, seen = [], set()
    for source in sources:
        url = source.get("url")
        if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
            continue
        try:
            parts = urlsplit(url)
            if parts.scheme.lower() not in ("http", "https") or not parts.hostname or parts.username or parts.password:
                continue
            parts.port  # Reject malformed ports too.
            key = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))
        except ValueError:
            continue
        if key not in seen:
            seen.add(key)
            out.append({"url": url, "title": str(source.get("title") or "")[:120]})
    return out


def _raise_error(error, *, usage=None) -> None:
    if error:
        message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        status = error.get("code", 0) if isinstance(error, dict) else 0
        raise OpenRouterError(str(message)[:500], status if isinstance(status, int) else 0, usage=usage)


def _clean_error(text: str) -> str:
    text = re.sub(r"sk-or-v\d+-[A-Za-z0-9_-]+", "[redacted]", str(text))
    return re.sub(r"(?i)Bearer\s+[^\s\"',}]+", "Bearer [redacted]", text)


def _merge(target: dict, update: dict) -> None:
    """Usage chunks contain cumulative totals, sometimes split over several events."""
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        elif value is not None:
            target[key] = value


async def _sse_data(lines):
    pending = []
    async for line in lines:
        if not line:
            if pending:
                yield "\n".join(pending)
                pending.clear()
        elif line.startswith("data:"):
            pending.append(line[5:].lstrip(" "))
        # SSE comments/keepalives and fields such as event/id do not contain model data.
    if pending:
        yield "\n".join(pending)


def _err_text(r: httpx.Response) -> str:
    try:
        e = r.json().get("error", {})
        return f"{r.status_code}: {e.get('message', r.text[:200])}"
    except Exception:
        return f"{r.status_code}: {r.text[:200]}"
