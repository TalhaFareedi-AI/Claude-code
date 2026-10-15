"""Protocol tests for the real gateway, without paid or nondeterministic model calls."""
import json

import httpx
import pytest

from app.openrouter import OpenRouter, OpenRouterError, _usage


SEARCH = [{"type": "openrouter:web_search", "parameters": {
    "engine": "exa", "max_uses": 2, "max_results": 3, "max_total_results": 6,
}}]
MESSAGES = [{"role": "user", "content": "Find current sources"}]


def response(content="Answer", **extra):
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}], **extra}


def sse(*chunks, done=True):
    content = ": keepalive\n\n" + "".join("data: " + json.dumps(c) + "\n\n" for c in chunks)
    return httpx.Response(200, content=content + ("data: [DONE]\n\n" if done else ""),
                          headers={"Content-Type": "text/event-stream"})


async def test_search_request_uses_supported_server_tool_shape():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=response(usage={"cost": 0.015,
            "server_tool_use_details": {"web_search_requests": 2}}))

    gateway = OpenRouter(api_key="test-key", transport=httpx.MockTransport(handler))
    try:
        result = await gateway.chat("test/model", MESSAGES, tools=SEARCH, max_tool_calls=2,
                                    private=True, reasoning={"effort": "low"})
    finally:
        await gateway.aclose()
    body = requests[0]
    assert body["tools"] == SEARCH
    assert body["max_tool_calls"] == 2
    assert "plugins" not in body
    assert body["provider"] == {"data_collection": "deny", "zdr": True, "require_parameters": True}
    assert body["usage"] == {"include": True}
    assert result.usage.searches == 2
    assert result.usage.cost == 0.015


@pytest.mark.parametrize("limit", [0, 31, -1, 1.5, True])
async def test_invalid_tool_limit_does_not_send_request(limit):
    def handler(request):
        pytest.fail("invalid bounds must fail before making a paid request")

    gateway = OpenRouter(api_key="test-key", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="max_tool_calls"):
            await gateway.chat("test/model", MESSAGES, tools=SEARCH, max_tool_calls=limit)
    finally:
        await gateway.aclose()


@pytest.mark.parametrize("stream", [False, True])
async def test_server_tool_stop_conditions_use_top_level_supported_shape(stream):
    requests = []
    stops = [{"type": "step_count_is", "step_count": 2},
             {"type": "max_cost", "max_cost_in_dollars": 0.03}]

    def handler(request):
        requests.append(json.loads(request.content))
        return sse({"choices": [{"delta": {"content": "Done"}, "finish_reason": "stop"}]}) if stream else httpx.Response(200, json=response())

    gateway = OpenRouter(api_key="test-key", transport=httpx.MockTransport(handler))
    try:
        call = gateway.chat_stream if stream else gateway.chat
        await call("test/model", MESSAGES, tools=SEARCH, max_tool_calls=2, stop_server_tools_when=stops)
    finally:
        await gateway.aclose()
    assert requests[0]["stop_server_tools_when"] == stops
    assert "stop_server_tools_when" not in requests[0]["tools"][0]["parameters"]


@pytest.mark.parametrize("stops", [
    [], {}, [None], [{"type": "unknown"}],
    [{"type": "step_count_is", "step_count": 0}],
    [{"type": "step_count_is", "step_count": 31}],
    [{"type": "step_count_is", "step_count": True}],
    [{"type": "max_cost", "max_cost_in_dollars": 0}],
    [{"type": "max_cost", "max_cost_in_dollars": -1}],
    [{"type": "max_cost", "max_cost_in_dollars": float("nan")}],
    [{"type": "max_cost", "max_cost_in_dollars": float("inf")}],
    [{"type": "max_cost", "max_cost_in_dollars": True}],
    [{"type": "max_cost", "max_cost_in_dollars": "0.03"}],
    [{"type": "step_count_is", "step_count": 2, "unexpected": 1}],
])
async def test_invalid_server_tool_stop_conditions_fail_before_paid_request(stops):
    def handler(request):
        pytest.fail("invalid stops must fail before making a paid request")

    gateway = OpenRouter(api_key="test-key", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError):
            await gateway.chat("test/model", MESSAGES, tools=SEARCH, stop_server_tools_when=stops)
    finally:
        await gateway.aclose()


def test_citations_are_safe_deduplicated_and_keep_provider_titles():
    annotations = [{"type": "url_citation", "url_citation": {"url": url, "title": "x" * 200}}
                   for url in ["https://example.com/report#one", "https://EXAMPLE.com/report#two",
                               "javascript:alert(1)", "data:text/html,bad", "https:///missing-host",
                               "https://user:pass@example.com", "https://example.com\n/unsafe",
                               "https://example.com:bad/port"]]
    data = response([{"type": "text", "text": "Grounded answer", "annotations": annotations}],
                    citations=["https://example.org/source"])
    result = OpenRouter._parse(data, "test/model")
    assert result.text == "Grounded answer"
    assert result.sources == [{"url": "https://example.com/report#one", "title": "x" * 120},
                              {"url": "https://example.org/source", "title": ""}]


@pytest.mark.parametrize("field", ["server_tool_use", "server_tool_use_details"])
def test_usage_aliases_and_missing_search_count_are_distinct(field):
    usage = _usage({"input_tokens": 100, "output_tokens": 50,
                    "input_tokens_details": {"cached_tokens": 30},
                    "output_tokens_details": {"reasoning_tokens": 20},
                    field: {"web_search_requests": 0}, "cost": "0"})
    assert (usage.prompt, usage.cached, usage.completion, usage.reasoning, usage.cost, usage.searches) == (70, 30, 50, 20, 0, 0)
    assert _usage({}).searches is None


def test_search_usage_falls_back_without_summing_duplicate_tool_details():
    assert _usage({"server_tool_use_details": {"tool_calls_executed": 2},
                   "server_tool_use": {"web_search_requests": 1}}).searches == 1
    assert _usage({"server_tool_use_details": {"web_search_requests": 2},
                   "server_tool_use": {"web_search_requests": 2}}).searches == 2


async def test_stream_retains_search_citations_images_reasoning_and_split_usage():
    citation = {"type": "url_citation", "url_citation": {"url": "https://example.com", "title": "Source"}}
    image = {"image_url": {"url": "data:image/png;base64,example"}}
    chunks = [
        {"model": "fallback/model", "choices": [{"index": 0, "delta": {
            "content": [{"type": "text", "text": "Grounded "}], "annotations": [citation],
            "images": [image], "reasoning_details": [{"type": "reasoning.text", "text": "Consider sources"}]}}],
         "usage": {"prompt_tokens": 100, "prompt_tokens_details": {"cached_tokens": 10}}},
        {"choices": [{"index": 0, "delta": {"content": "answer", "annotations": [citation], "images": [image]}},
                     {"index": 1, "delta": {"content": "Ignored alternate answer"}}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
         "usage": {"completion_tokens": 20, "completion_tokens_details": {"reasoning_tokens": 5},
                   "cost": 0.01, "server_tool_use": {"web_search_requests": 1}}},
    ]
    requests, deltas = [], []

    def handler(request):
        requests.append(json.loads(request.content))
        return sse(*chunks)

    async def on_delta(text):
        deltas.append(text)

    gateway = OpenRouter(api_key="test-key", transport=httpx.MockTransport(handler))
    try:
        result = await gateway.chat_stream("test/model", MESSAGES, tools=SEARCH, max_tool_calls=2,
                                           on_delta=on_delta)
    finally:
        await gateway.aclose()
    assert requests[0]["stream"] is True
    assert requests[0]["tools"] == SEARCH
    assert requests[0]["max_tool_calls"] == 2
    assert "".join(deltas) == result.text == "Grounded answer"
    assert result.model == "fallback/model"
    assert result.reasoning_text == "Consider sources"
    assert result.sources == [{"url": "https://example.com", "title": "Source"}]
    assert result.images == [image]
    assert (result.usage.prompt, result.usage.cached, result.usage.completion,
            result.usage.reasoning, result.usage.searches, result.usage.cost) == (90, 10, 20, 5, 1, 0.01)


@pytest.mark.parametrize("failure, expected", [
    ({"error": {"message": "Search failed", "code": 502}}, "Search failed"),
    ({"choices": [{"delta": {}, "finish_reason": "error"}]}, "ended with an error"),
])
async def test_stream_errors_do_not_become_success_and_keep_accounting(failure, expected):
    first = {"choices": [{"delta": {"content": "Partial answer"}}], "usage": {"cost": 0.004}}
    gateway = OpenRouter(api_key="test-key", transport=httpx.MockTransport(lambda _: sse(first, failure)))
    try:
        with pytest.raises(OpenRouterError, match=expected) as caught:
            await gateway.chat_stream("test/model", MESSAGES)
    finally:
        await gateway.aclose()
    assert caught.value.partial_text == "Partial answer"
    assert caught.value.usage.cost == 0.004


@pytest.mark.parametrize("content, expected", [
    ('data: {broken}\n\ndata: [DONE]\n\n', "invalid JSON"),
    ('data: {"choices":[{"delta":{"content":"Partial"}}]}\n\n', "before completion"),
    ('data: [DONE]\n\n', "empty response"),
])
async def test_stream_rejects_malformed_empty_and_truncated_responses(content, expected):
    gateway = OpenRouter(api_key="test-key", transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=content)))
    try:
        with pytest.raises(OpenRouterError, match=expected):
            await gateway.chat_stream("test/model", MESSAGES)
    finally:
        await gateway.aclose()


async def test_stream_accepts_multiline_sse_data_and_a_final_usage_frame():
    content = 'data: {"choices":\ndata: [{"delta":{"content":"Done"},"finish_reason":"stop"}]}\n\n'
    content += 'data: {"usage":{"cost":0.001}}\n\ndata: [DONE]\n\n'
    gateway = OpenRouter(api_key="test-key", transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=content)))
    try:
        result = await gateway.chat_stream("test/model", MESSAGES)
    finally:
        await gateway.aclose()
    assert result.text == "Done"
    assert result.usage.cost == 0.001


async def test_empty_length_result_preserves_bill_for_budgeted_caller_retry():
    gateway = OpenRouter(api_key="test-key", transport=httpx.MockTransport(lambda _: sse({
        "choices": [{"delta": {}, "finish_reason": "length"}],
        "usage": {"completion_tokens": 1000, "completion_tokens_details": {"reasoning_tokens": 1000}, "cost": 0.003},
    })))
    try:
        result = await gateway.chat_stream("test/model", MESSAGES)
    finally:
        await gateway.aclose()
    assert result.text == ""
    assert result.finish_reason == "length"
    assert result.usage.cost == 0.003
    assert result.usage.reasoning == 1000


async def test_transient_http_errors_retry_but_authorization_errors_do_not(monkeypatch):
    calls, waits = [], []

    async def sleep(delay):
        waits.append(delay)

    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={"error": {"message": "Busy"}}) if len(calls) < 3 else httpx.Response(200, json=response())

    monkeypatch.setattr("app.openrouter.asyncio.sleep", sleep)
    gateway = OpenRouter(api_key="test-key", transport=httpx.MockTransport(handler))
    try:
        assert (await gateway.chat("test/model", MESSAGES)).text == "Answer"
    finally:
        await gateway.aclose()
    assert len(calls) == 3
    assert waits == [0.8, 1.6]

    calls.clear()
    waits.clear()

    def unauthorized(request):
        calls.append(request)
        return httpx.Response(401, json={"error": {"message": "Unauthorized Bearer test-key"}})

    gateway = OpenRouter(api_key="test-key", transport=httpx.MockTransport(unauthorized))
    try:
        with pytest.raises(OpenRouterError) as caught:
            await gateway.chat("test/model", MESSAGES)
    finally:
        await gateway.aclose()
    assert caught.value.status == 401
    assert "test-key" not in str(caught.value) + caught.value.body
    assert len(calls) == 1 and not waits


async def test_network_failure_is_normalized_and_does_not_sleep_after_final_attempt(monkeypatch):
    waits = []

    async def sleep(delay):
        waits.append(delay)

    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    monkeypatch.setattr("app.openrouter.asyncio.sleep", sleep)
    gateway = OpenRouter(api_key="test-key", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(OpenRouterError, match="network error"):
            await gateway.chat("test/model", MESSAGES, retries=0)
    finally:
        await gateway.aclose()
    assert waits == []


@pytest.mark.parametrize("data, expected", [
    ([], "invalid response"),
    ({"choices": []}, "empty response"),
    (response(usage={"cost": "NaN"}), "invalid cost"),
    (response(usage={"cost": -1}), "invalid cost"),
    ({"error": {"message": "failed", "code": 503}}, "failed"),
])
def test_invalid_nonstreaming_responses_are_rejected(data, expected):
    with pytest.raises(OpenRouterError, match=expected):
        OpenRouter._parse(data, "test/model")


async def test_malformed_json_http_response_is_a_gateway_error():
    gateway = OpenRouter(api_key="test-key", transport=httpx.MockTransport(lambda _: httpx.Response(200, text="not-json")))
    try:
        with pytest.raises(OpenRouterError, match="invalid JSON"):
            await gateway.chat("test/model", MESSAGES)
    finally:
        await gateway.aclose()


def test_nonstream_error_preserves_reported_cost():
    with pytest.raises(OpenRouterError) as caught:
        OpenRouter._parse({"error": {"message": "failed", "code": 502}, "usage": {"cost": 0.002}}, "test/model")
    assert caught.value.status == 502
    assert caught.value.usage.cost == 0.002
