import json
from types import SimpleNamespace

import httpx
import pytest

from wiltech_labs_ai import (
    AiBindingAdapter,
    AiHttpAdapter,
    OpenAICompatibleChatAdapter,
    OpenAICompatibleLlm,
    embed,
    embed_openai_compatible,
    get_ai,
    get_tool_llm,
)
from wiltech_labs_core import NotConfiguredError, UpstreamError

TOOLS = [{"type": "function", "function": {"name": "count_todos", "parameters": {"type": "object"}}}]


def request_with(env=None):
    return SimpleNamespace(scope={"env": env} if env is not None else {})


def replying(message, status=200, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json={"choices": [{"message": message}]} if status < 400 else {"error": "no"})

    return httpx.MockTransport(handler)


async def test_sends_an_openai_style_request_and_parses_tool_calls():
    seen = []
    tool_call = {"id": "call_1", "type": "function", "function": {"name": "count_todos", "arguments": '{"state": "NEW"}'}}
    llm = OpenAICompatibleLlm(
        "key", "https://api.groq.com/openai/v1/", replying({"content": None, "tool_calls": [tool_call]}, seen=seen)
    )

    turn = await llm.complete("model-x", [{"role": "user", "content": "hi"}], TOOLS)

    assert turn == {"content": None, "tool_calls": [{"id": "call_1", "name": "count_todos", "arguments": '{"state": "NEW"}'}]}
    request = seen[0]
    assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer key"
    body = json.loads(request.content)
    assert body["model"] == "model-x" and body["tools"] == TOOLS and body["tool_choice"] == "auto"


async def test_no_tools_means_no_tools_field():
    seen = []
    await OpenAICompatibleLlm("k", "https://x/v1", replying({"content": "hi"}, seen=seen)).complete("m", [], [])
    assert "tools" not in json.loads(seen[0].content)


async def test_provider_errors_are_502s_without_the_provider_body():
    llm = OpenAICompatibleLlm("key", "https://x/v1", replying({}, status=429))
    with pytest.raises(UpstreamError, match="429") as raised:
        await llm.complete("m", [], TOOLS)
    assert raised.value.status_code == 502 and "no" not in raised.value.detail.split()


async def test_chat_adapter_speaks_the_ai_protocol():
    adapter = OpenAICompatibleChatAdapter("k", "https://x/v1", replying({"content": "hello back"}))
    assert await adapter.run("m", {"messages": [{"role": "user", "content": "hello"}]}) == {"response": "hello back"}


async def test_workers_ai_rest_adapter():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"success": True, "result": {"response": "ok"}})

    adapter = AiHttpAdapter("acc", "tok", transport=httpx.MockTransport(handler))
    assert await adapter.run("@cf/meta/llama", {"prompt": "x"}) == {"response": "ok"}
    assert str(seen[0].url) == "https://api.cloudflare.com/client/v4/accounts/acc/ai/run/@cf/meta/llama"


def test_get_ai_prefers_the_binding_in_a_worker(monkeypatch):
    monkeypatch.delenv("AI_MODE", raising=False)
    assert isinstance(get_ai(request_with(SimpleNamespace(AI=object()))), AiBindingAdapter)

    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://ollama:11434/v1")
    assert isinstance(get_ai(request_with(), "local"), OpenAICompatibleChatAdapter)


def test_get_tool_llm_reads_provider_config(monkeypatch):
    monkeypatch.setenv("CF_AI_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_AI_API_TOKEN", "tok")
    monkeypatch.setenv("CF_AI_MODEL", "@cf/meta/llama-4-scout-17b-16e-instruct")
    llm, model = get_tool_llm(request_with(), "cloudflare")
    assert model == "@cf/meta/llama-4-scout-17b-16e-instruct"
    assert llm._base_url == "https://api.cloudflare.com/client/v4/accounts/acc/ai/v1"

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(NotConfiguredError, match="GROQ_API_KEY"):
        get_tool_llm(request_with(), "groq")


async def test_workers_ai_embeddings_are_batched_and_truncated():
    calls = []

    class FakeAI:
        async def run(self, model, inputs):
            calls.append(inputs["text"])
            return {"data": [[1.0, 0.0] for _ in inputs["text"]]}

    vectors = await embed(FakeAI(), "@cf/baai/bge-base-en-v1.5", ["x" * 5000] + ["y"] * 59)
    assert len(vectors) == 60 and [len(batch) for batch in calls] == [50, 10]
    assert len(calls[0][0]) == 2000


async def test_openai_compatible_embeddings_keep_input_order():
    def handler(request):
        body = json.loads(request.content)
        assert body == {"model": "bge-m3", "input": ["a", "b"]}
        return httpx.Response(200, json={"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]})

    vectors = await embed_openai_compatible("k", "http://ollama:11434/v1", "bge-m3", ["a", "b"], httpx.MockTransport(handler))
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
