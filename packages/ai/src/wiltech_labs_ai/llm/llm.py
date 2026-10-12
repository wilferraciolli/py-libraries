import logging
from typing import Any, Dict, List, Optional, Protocol

import httpx
from starlette.requests import HTTPConnection

from wiltech_labs_core import NotConfiguredError, UpstreamError, get_config

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60


class ToolLlm(Protocol):
    """
    A chat model that can ask for tools to be run.

    `complete` returns the assistant turn as {"content": str | None,
    "tool_calls": [{"id", "name", "arguments" (a JSON string)}]}.
    """

    async def complete(
        self, model: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]: ...


async def chat_completion(
    api_key: str,
    base_url: str,
    payload: Dict[str, Any],
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Dict[str, Any]:
    """
    POST {base_url}/chat/completions: the OpenAI-compatible API that Groq,
    Ollama and Workers AI (/ai/v1) all speak. Plain httpx instead of the
    `openai` package, which is heavy to load in a Python Worker (about 1.4 s
    of CPU on a cold start) for what is one JSON request. Returns the first
    choice's message.

    Raises UpstreamError (502) on an error status or an empty reply. The
    provider's error body goes to the log, not to the API client.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=transport) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    if response.status_code >= 400:
        logger.warning("chat completion failed (%s): %s", response.status_code, response.text[:300])
        raise UpstreamError(f"The AI provider returned {response.status_code}")
    choices = response.json().get("choices") or []
    if not choices:
        logger.warning("chat completion returned no choices: %s", response.text[:300])
        raise UpstreamError("The AI provider returned no answer")
    return choices[0].get("message") or {}


class OpenAICompatibleLlm:
    """
    Chat-completions with tool calling against any OpenAI-compatible endpoint:
    Groq (https://api.groq.com/openai/v1), Workers AI
    (https://api.cloudflare.com/client/v4/accounts/{id}/ai/v1) and Ollama
    (http://ollama:11434/v1) all speak it, so one client serves every provider.
    """

    def __init__(self, api_key: str, base_url: str, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._transport = transport  # tests pass an httpx.MockTransport

    async def complete(
        self, model: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"model": model, "messages": messages}
        if tools:
            payload.update({"tools": tools, "tool_choice": "auto"})
        message = await chat_completion(self._api_key, self._base_url, payload, self._transport)
        return {
            "content": message.get("content"),
            "tool_calls": [
                {
                    "id": call.get("id"),
                    "name": (call.get("function") or {}).get("name"),
                    "arguments": (call.get("function") or {}).get("arguments") or "{}",
                }
                for call in (message.get("tool_calls") or [])
            ],
        }


def _required(request: HTTPConnection, key: str) -> str:
    value = get_config(request, key)
    if not value:
        raise NotConfiguredError(f"{key} must be configured (see .env.example)")
    return value


def get_tool_llm(request: HTTPConnection, provider: str) -> tuple[ToolLlm, str]:
    """
    (tool-calling client, model name) for a provider, from config:

    - groq: GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL
    - local: LOCAL_LLM_BASE_URL (default Ollama on localhost), LOCAL_LLM_MODEL, optional LOCAL_LLM_API_KEY
    - cloudflare: CF_AI_ACCOUNT_ID, CF_AI_API_TOKEN, CF_AI_MODEL — Workers AI over
      its OpenAI-compatible endpoint (the REST credentials, not the binding)

    Missing settings raise NotConfiguredError, a 503 with the setting's name.
    """
    from wiltech_labs_ai.providers.ai import DEFAULT_LOCAL_API_KEY, DEFAULT_LOCAL_BASE_URL, workers_ai_openai_base_url

    if provider == "groq":
        llm = OpenAICompatibleLlm(_required(request, "GROQ_API_KEY"), _required(request, "GROQ_BASE_URL"))
        return llm, _required(request, "GROQ_MODEL")

    if provider == "local":
        llm = OpenAICompatibleLlm(
            get_config(request, "LOCAL_LLM_API_KEY", DEFAULT_LOCAL_API_KEY) or DEFAULT_LOCAL_API_KEY,
            get_config(request, "LOCAL_LLM_BASE_URL", DEFAULT_LOCAL_BASE_URL) or DEFAULT_LOCAL_BASE_URL,
        )
        return llm, _required(request, "LOCAL_LLM_MODEL")

    if provider == "cloudflare":
        account_id = _required(request, "CF_AI_ACCOUNT_ID")
        llm = OpenAICompatibleLlm(_required(request, "CF_AI_API_TOKEN"), workers_ai_openai_base_url(account_id))
        return llm, _required(request, "CF_AI_MODEL")

    raise ValueError(f"unknown provider: {provider!r}")
