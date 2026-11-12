import logging
from typing import Any, Literal, Optional, Protocol

import httpx
from starlette.requests import HTTPConnection

from wiltech_labs_core import NotConfiguredError, UpstreamError, get_config

logger = logging.getLogger(__name__)

# The LLM providers an app can talk to. "local" is any OpenAI-compatible
# server you run yourself — Ollama on the home server by default.
ChatProvider = Literal["cloudflare", "groq", "local"]

DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"  # Ollama's OpenAI-compatible API
DEFAULT_LOCAL_API_KEY = "ollama"  # Ollama ignores it, but the header must be present

# Generation options OpenAICompatibleChatAdapter passes on from `inputs`, besides the messages.
# Workers AI takes the same names, so one `inputs` dict works for every provider.
CHAT_OPTIONS = ("max_tokens", "temperature", "top_p", "response_format")


class AI(Protocol):
    async def run(self, model: str, inputs: dict[str, Any]) -> dict[str, Any]: ...


class AiBindingAdapter:
    """Cloudflare Worker native binding adapter for env.AI."""

    def __init__(self, ai: Any) -> None:
        self._ai = ai

    async def run(self, model: str, inputs: dict[str, Any]) -> dict[str, Any]:
        result = await self._ai.run(model, inputs)
        return result if isinstance(result, dict) else dict(result)


class AiHttpAdapter:
    """
    Cloudflare Workers AI over the REST API.

    Prefer this over AiBindingAdapter for portability: it works the same from
    local uvicorn/Docker, another host, or a Cloudflare Worker, the same way
    D1HttpDatabase lets any of those runtimes reach D1. Needs CF_AI_ACCOUNT_ID
    and CF_AI_API_TOKEN (a Cloudflare API token scoped to Workers AI).
    """

    def __init__(self, account_id: str, api_token: str, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self._base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run"
        self._headers = {"Authorization": f"Bearer {api_token}"}
        self._transport = transport  # tests pass an httpx.MockTransport

    async def run(self, model: str, inputs: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30, transport=self._transport) as client:
            response = await client.post(
                f"{self._base_url}/{model}",
                headers=self._headers,
                json=inputs,
            )

        # Same as chat_completion: the provider's body goes to the log, not the client.
        if response.status_code >= 400:
            logger.warning("Workers AI request failed (%s): %s", response.status_code, response.text[:300])
            raise UpstreamError(f"Workers AI returned {response.status_code}")

        body = response.json()
        if not body.get("success"):
            logger.warning("Workers AI request failed: %s", str(body.get("errors"))[:300])
            raise UpstreamError("Workers AI could not answer")

        return body["result"]


class OpenAICompatibleChatAdapter:
    """
    Plain chat (no tools) through any OpenAI-compatible chat-completions API:
    Groq, Ollama, or Workers AI's /ai/v1. Speaks the AI protocol, returning
    {"response": text} like Workers AI text models do. `inputs` keys in
    CHAT_OPTIONS (max_tokens, temperature, ...) are passed on; others are not.
    """

    def __init__(self, api_key: str, base_url: str, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._transport = transport

    async def run(self, model: str, inputs: dict[str, Any]) -> dict[str, Any]:
        from wiltech_labs_ai.llm.llm import chat_completion

        payload: dict[str, Any] = {"model": model, "messages": inputs["messages"]}
        payload.update({key: inputs[key] for key in CHAT_OPTIONS if inputs.get(key) is not None})
        message = await chat_completion(self._api_key, self._base_url, payload, self._transport)
        return {"response": message.get("content") or ""}


# The name fastapi-ai used before Ollama shared the adapter.
GroqAdapter = OpenAICompatibleChatAdapter


def workers_ai_openai_base_url(account_id: str) -> str:
    """Workers AI's OpenAI-compatible endpoint (chat completions with tools, embeddings)."""
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"


def get_ai(request: HTTPConnection, provider: ChatProvider = "cloudflare") -> AI:
    """
    Select the AI backend for the current runtime and provider.

    - groq: GROQ_API_KEY + GROQ_BASE_URL
    - local: LOCAL_LLM_BASE_URL (default Ollama on localhost) + optional LOCAL_LLM_API_KEY
    - cloudflare, by AI_MODE:
      - http: REST API call to Cloudflare — portable, works everywhere
      - binding: Cloudflare Workers env.AI binding — no network hop, Workers-only

    If AI_MODE is omitted and env.AI exists, binding is used (same
    "prefer the native binding inside Workers" rule get_database follows for
    D1) — otherwise http, so local uvicorn/Docker and any non-Worker host
    work without extra configuration beyond an API token.

    A missing key raises NotConfiguredError (503), so get_fallback_ai can
    skip a provider that isn't set up.
    """
    if provider == "groq":
        api_key = get_config(request, "GROQ_API_KEY")
        base_url = get_config(request, "GROQ_BASE_URL")
        if not api_key or not base_url:
            raise NotConfiguredError("Groq requires GROQ_API_KEY and GROQ_BASE_URL")
        return OpenAICompatibleChatAdapter(api_key, base_url)

    if provider == "local":
        return OpenAICompatibleChatAdapter(
            get_config(request, "LOCAL_LLM_API_KEY", DEFAULT_LOCAL_API_KEY) or DEFAULT_LOCAL_API_KEY,
            get_config(request, "LOCAL_LLM_BASE_URL", DEFAULT_LOCAL_BASE_URL) or DEFAULT_LOCAL_BASE_URL,
        )

    env = request.scope.get("env")
    has_ai_binding = env is not None and hasattr(env, "AI")
    mode = get_config(request, "AI_MODE", "binding" if has_ai_binding else "http")

    if mode == "binding":
        if not has_ai_binding:
            raise NotConfiguredError("AI_MODE='binding' requires a Cloudflare Workers env.AI binding")
        return AiBindingAdapter(env.AI)

    if mode == "http":
        account_id = get_config(request, "CF_AI_ACCOUNT_ID")
        api_token = get_config(request, "CF_AI_API_TOKEN")
        if not account_id or not api_token:
            raise NotConfiguredError("AI_MODE='http' requires CF_AI_ACCOUNT_ID and CF_AI_API_TOKEN")
        return AiHttpAdapter(account_id, api_token)

    raise RuntimeError(f"unknown AI_MODE: {mode!r}")
