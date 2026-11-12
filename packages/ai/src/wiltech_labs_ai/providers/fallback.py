import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence, get_args

from starlette.requests import HTTPConnection

from wiltech_labs_core import NotConfiguredError, UpstreamError, get_config

from wiltech_labs_ai.providers.ai import AI, ChatProvider, get_ai

logger = logging.getLogger(__name__)

# The model each provider answers with, read by chat_model().
MODEL_CONFIG_KEYS: dict[str, str] = {
    "groq": "GROQ_MODEL",
    "cloudflare": "CF_AI_MODEL",
    "local": "LOCAL_LLM_MODEL",
}

# Comma-separated provider order, e.g. "groq,cloudflare". Overrides the app's default order.
PROVIDERS_CONFIG_KEY = "AI_PROVIDERS"


@dataclass(frozen=True)
class AiCandidate:
    """One provider to try: which one, the model it runs, and its client."""

    provider: ChatProvider
    model: str
    ai: AI


@dataclass(frozen=True)
class FallbackReply:
    """
    What FallbackAI.run returns: the provider and model that answered (store
    them with the content, so you know which wrote it), the provider's raw
    result ({"response": text} for chat), and the providers that failed first.
    """

    provider: ChatProvider
    model: str
    result: dict[str, Any]
    failed: tuple[ChatProvider, ...] = field(default_factory=tuple)

    @property
    def text(self) -> str:
        """
        The answer as text. Workers AI parses an answer that is JSON itself and returns it as an
        object under `response`, so that comes back as JSON text again.
        """
        response = self.result.get("response")
        if isinstance(response, str):
            return response
        if isinstance(response, (dict, list)):
            return json.dumps(response, ensure_ascii=False)
        return str(self.result)

    @property
    def fell_back(self) -> bool:
        return bool(self.failed)


class FallbackAI:
    """
    Ask providers in order until one answers: e.g. Groq first (fast, generous
    free tier), then Workers AI when Groq rate-limits, times out or is down.

    Any failure moves on to the next provider: a 429, a 5xx, a timeout, a
    Worker binding error. A blank text reply counts as a failure too. The
    reason goes to the log, not the client. When every provider fails, the
    client gets one UpstreamError (502).
    """

    def __init__(self, candidates: Sequence[AiCandidate]) -> None:
        if not candidates:
            raise NotConfiguredError("No AI provider is configured")
        self.candidates = tuple(candidates)

    @property
    def providers(self) -> tuple[ChatProvider, ...]:
        return tuple(candidate.provider for candidate in self.candidates)

    async def run(self, inputs: dict[str, Any]) -> FallbackReply:
        failed: list[ChatProvider] = []

        for candidate in self.candidates:
            try:
                result = await candidate.ai.run(candidate.model, inputs)
            except Exception as exc:  # any provider failure means "try the next one"
                logger.warning("AI provider %s (%s) failed, trying the next one: %r", candidate.provider, candidate.model, exc)
                failed.append(candidate.provider)
                continue

            response = result.get("response") if isinstance(result, dict) else None
            if isinstance(response, str) and not response.strip():
                logger.warning("AI provider %s (%s) returned a blank answer, trying the next one", candidate.provider, candidate.model)
                failed.append(candidate.provider)
                continue

            return FallbackReply(candidate.provider, candidate.model, result, tuple(failed))

        raise UpstreamError("The AI providers are unavailable at the moment. Try again shortly.")


def chat_model(request: HTTPConnection, provider: ChatProvider) -> str:
    """The model configured for a provider (GROQ_MODEL, CF_AI_MODEL, LOCAL_LLM_MODEL); 503 if unset."""
    key = MODEL_CONFIG_KEYS[provider]
    model = get_config(request, key)
    if not model:
        raise NotConfiguredError(f"{key} must be configured (see .env.example)")
    return model


def provider_order(request: HTTPConnection, default: Sequence[ChatProvider]) -> tuple[ChatProvider, ...]:
    """AI_PROVIDERS ("groq,cloudflare") if set, otherwise the app's default order."""
    configured: Optional[str] = get_config(request, PROVIDERS_CONFIG_KEY)
    if not configured:
        return tuple(default)

    known = set(get_args(ChatProvider))
    order = tuple(dict.fromkeys(name.strip() for name in configured.split(",") if name.strip()))
    unknown = [name for name in order if name not in known]
    if unknown:
        raise RuntimeError(f"{PROVIDERS_CONFIG_KEY} has unknown providers {unknown}; use {sorted(known)}")
    return order  # type: ignore[return-value]


def get_fallback_ai(request: HTTPConnection, default_providers: Sequence[ChatProvider]) -> FallbackAI:
    """
    A FallbackAI over every configured provider, in AI_PROVIDERS order (or
    `default_providers`). A provider whose key or model isn't set is skipped,
    so a deployment can run with Groq alone, Workers AI alone, or both. 503
    NotConfiguredError when none is configured.
    """
    candidates: list[AiCandidate] = []
    skipped: list[str] = []

    for provider in provider_order(request, default_providers):
        try:
            candidates.append(AiCandidate(provider, chat_model(request, provider), get_ai(request, provider)))
        except NotConfiguredError as exc:
            skipped.append(f"{provider}: {exc.detail}")

    if skipped:
        logger.info("AI providers skipped as not configured: %s", "; ".join(skipped))
    if not candidates:
        raise NotConfiguredError("No AI provider is configured (see .env.example)")

    return FallbackAI(candidates)
