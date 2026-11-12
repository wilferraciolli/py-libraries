import json
from types import SimpleNamespace

import httpx
import pytest

from wiltech_labs_ai import (
    AiCandidate,
    AiHttpAdapter,
    FallbackAI,
    OpenAICompatibleChatAdapter,
    chat_model,
    get_ai,
    get_fallback_ai,
    provider_order,
)
from wiltech_labs_core import NotConfiguredError, UpstreamError

MESSAGES = {"messages": [{"role": "user", "content": "Write a post"}]}


def request_with(env=None):
    return SimpleNamespace(scope={"env": env} if env is not None else {})


class FakeAI:
    def __init__(self, reply=None, error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    async def run(self, model, inputs):
        self.calls.append((model, inputs))
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture(autouse=True)
def no_ai_config(monkeypatch):
    for key in ("AI_PROVIDERS", "AI_MODE", "GROQ_API_KEY", "GROQ_BASE_URL", "GROQ_MODEL",
                "CF_AI_ACCOUNT_ID", "CF_AI_API_TOKEN", "CF_AI_MODEL", "LOCAL_LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)


async def test_the_first_provider_answers():
    groq, cloudflare = FakeAI({"response": "from groq"}), FakeAI({"response": "from cf"})
    reply = await FallbackAI([AiCandidate("groq", "g", groq), AiCandidate("cloudflare", "c", cloudflare)]).run(MESSAGES)

    assert (reply.provider, reply.model, reply.text, reply.failed, reply.fell_back) == ("groq", "g", "from groq", (), False)
    assert groq.calls == [("g", MESSAGES)] and cloudflare.calls == []


@pytest.mark.parametrize("error", [UpstreamError("Groq returned 429"), httpx.ReadTimeout("slow"), RuntimeError("binding")])
async def test_any_failure_falls_back_to_the_next_provider(error):
    cloudflare = FakeAI({"response": "from cf"})
    reply = await FallbackAI(
        [AiCandidate("groq", "g", FakeAI(error=error)), AiCandidate("cloudflare", "c", cloudflare)]
    ).run(MESSAGES)

    assert (reply.provider, reply.model, reply.text, reply.failed) == ("cloudflare", "c", "from cf", ("groq",))
    assert reply.fell_back


async def test_an_answer_workers_ai_parsed_as_json_is_text_again():
    parsed = {"title": None, "body": "Καλημέρα"}
    reply = await FallbackAI([AiCandidate("cloudflare", "c", FakeAI({"response": parsed}))]).run(MESSAGES)
    assert json.loads(reply.text) == parsed and "Καλημέρα" in reply.text


async def test_a_blank_answer_falls_back():
    reply = await FallbackAI(
        [AiCandidate("groq", "g", FakeAI({"response": "  "})), AiCandidate("cloudflare", "c", FakeAI({"response": "ok"}))]
    ).run(MESSAGES)
    assert reply.provider == "cloudflare"


async def test_every_provider_failing_is_one_502():
    ai = FallbackAI([AiCandidate("groq", "g", FakeAI(error=UpstreamError("429"))),
                     AiCandidate("cloudflare", "c", FakeAI(error=UpstreamError("500")))])
    with pytest.raises(UpstreamError) as raised:
        await ai.run(MESSAGES)
    assert raised.value.status_code == 502 and "429" not in raised.value.detail


def test_no_candidates_is_not_configured():
    with pytest.raises(NotConfiguredError):
        FallbackAI([])


def test_get_ai_reports_missing_keys_as_not_configured():
    with pytest.raises(NotConfiguredError):
        get_ai(request_with(), "groq")
    with pytest.raises(NotConfiguredError):
        get_ai(request_with(), "cloudflare")  # http mode outside a Worker


def test_chat_model_reads_each_providers_model():
    request = request_with(SimpleNamespace(GROQ_MODEL="openai/gpt-oss-20b"))
    assert chat_model(request, "groq") == "openai/gpt-oss-20b"
    with pytest.raises(NotConfiguredError, match="CF_AI_MODEL"):
        chat_model(request, "cloudflare")


def test_provider_order_defaults_to_the_apps_order_and_ai_providers_overrides_it():
    assert provider_order(request_with(), ("groq", "cloudflare")) == ("groq", "cloudflare")
    request = request_with(SimpleNamespace(AI_PROVIDERS=" cloudflare , groq,cloudflare"))
    assert provider_order(request, ("groq", "cloudflare")) == ("cloudflare", "groq")
    with pytest.raises(RuntimeError, match="openai"):
        provider_order(request_with(SimpleNamespace(AI_PROVIDERS="groq,openai")), ("groq",))


def test_get_fallback_ai_skips_unconfigured_providers():
    groq_only = SimpleNamespace(GROQ_API_KEY="k", GROQ_BASE_URL="https://api.groq.com/openai/v1", GROQ_MODEL="g")
    assert get_fallback_ai(request_with(groq_only), ("groq", "cloudflare")).providers == ("groq",)

    both = SimpleNamespace(**vars(groq_only), CF_AI_ACCOUNT_ID="acc", CF_AI_API_TOKEN="tok", CF_AI_MODEL="@cf/m")
    assert get_fallback_ai(request_with(both), ("groq", "cloudflare")).providers == ("groq", "cloudflare")


def test_get_fallback_ai_with_nothing_configured_is_a_503():
    with pytest.raises(NotConfiguredError):
        get_fallback_ai(request_with(), ("groq", "cloudflare"))


async def test_chat_adapter_passes_generation_options_on():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    adapter = OpenAICompatibleChatAdapter("k", "https://x/v1", httpx.MockTransport(handler))
    await adapter.run("m", {**MESSAGES, "max_tokens": 900, "temperature": 0.8, "seed": 1})

    assert seen[0]["max_tokens"] == 900 and seen[0]["temperature"] == 0.8 and "seed" not in seen[0]


async def test_workers_ai_rest_errors_are_502s():
    failing = AiHttpAdapter("acc", "tok", transport=httpx.MockTransport(lambda r: httpx.Response(429, text="slow down")))
    with pytest.raises(UpstreamError, match="429"):
        await failing.run("@cf/m", MESSAGES)

    unsuccessful = AiHttpAdapter(
        "acc", "tok", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"success": False, "errors": ["x"]}))
    )
    with pytest.raises(UpstreamError):
        await unsuccessful.run("@cf/m", MESSAGES)
