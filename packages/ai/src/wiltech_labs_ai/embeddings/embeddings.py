from typing import Awaitable, Callable, Optional

import httpx
from starlette.requests import HTTPConnection

from wiltech_labs_ai.providers.ai import AI, DEFAULT_LOCAL_API_KEY, DEFAULT_LOCAL_BASE_URL, get_ai
from wiltech_labs_core import UpstreamError, get_config

# English only, 768 dimensions. For Greek / Portuguese text use a multilingual
# model such as @cf/baai/bge-m3 (1024 dimensions) — and reindex, since
# vectors from different models can't be compared.
DEFAULT_EMBEDDING_MODEL = "@cf/baai/bge-base-en-v1.5"
DEFAULT_LOCAL_EMBEDDING_MODEL = "bge-m3"

# bge models read ~512 tokens; longer text is truncated. Split long documents
# into chunks before embedding them.
MAX_EMBED_CHARS = 2000

BATCH_SIZE = 50

EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]


async def embed(ai: AI, model: str, texts: list[str]) -> list[list[float]]:
    """Embed texts with a Workers AI embedding model; returns one vector per text, in order."""
    vectors: list[list[float]] = []

    for start in range(0, len(texts), BATCH_SIZE):
        batch = [text[:MAX_EMBED_CHARS] for text in texts[start : start + BATCH_SIZE]]
        result = await ai.run(model, {"text": batch})
        data = result.get("data")
        if not isinstance(data, list) or len(data) != len(batch):
            raise RuntimeError(f"unexpected embedding response shape: {str(result)[:200]}")
        vectors.extend([[float(value) for value in vector] for vector in data])

    return vectors


async def embed_openai_compatible(
    api_key: str,
    base_url: str,
    model: str,
    texts: list[str],
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> list[list[float]]:
    """
    Embed texts through POST {base_url}/embeddings, the OpenAI-compatible API
    Ollama (and Workers AI's /ai/v1) speak. One vector per text, in order.
    """
    vectors: list[list[float]] = []

    async with httpx.AsyncClient(timeout=60, transport=transport) as client:
        for start in range(0, len(texts), BATCH_SIZE):
            batch = [text[:MAX_EMBED_CHARS] for text in texts[start : start + BATCH_SIZE]]
            response = await client.post(
                f"{base_url.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "input": batch},
            )
            if response.status_code >= 400:
                raise UpstreamError(f"The embedding provider returned {response.status_code}")
            data = sorted(response.json().get("data") or [], key=lambda item: item.get("index", 0))
            if len(data) != len(batch):
                raise RuntimeError(f"unexpected embedding response shape: {response.text[:200]}")
            vectors.extend([[float(value) for value in item["embedding"]] for item in data])

    return vectors


def get_embedder(request: HTTPConnection) -> tuple[EmbedFn, str]:
    """
    (embed function, model name). EMBEDDING_PROVIDER picks the backend:

    - cloudflare (default): Workers AI, model CF_EMBEDDING_MODEL, whichever provider chats
    - local: OpenAI-compatible server (Ollama) at LOCAL_LLM_BASE_URL, model LOCAL_EMBEDDING_MODEL
    """
    provider = get_config(request, "EMBEDDING_PROVIDER", "cloudflare") or "cloudflare"

    if provider == "local":
        model = get_config(request, "LOCAL_EMBEDDING_MODEL", DEFAULT_LOCAL_EMBEDDING_MODEL) or DEFAULT_LOCAL_EMBEDDING_MODEL
        api_key = get_config(request, "LOCAL_LLM_API_KEY", DEFAULT_LOCAL_API_KEY) or DEFAULT_LOCAL_API_KEY
        base_url = get_config(request, "LOCAL_LLM_BASE_URL", DEFAULT_LOCAL_BASE_URL) or DEFAULT_LOCAL_BASE_URL

        async def embed_local(texts: list[str]) -> list[list[float]]:
            return await embed_openai_compatible(api_key, base_url, model, texts)

        return embed_local, model

    model = get_config(request, "CF_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL) or DEFAULT_EMBEDDING_MODEL

    async def embed_texts(texts: list[str]) -> list[list[float]]:
        # Built on first use, so routes that never embed (todo CRUD without
        # Workers AI credentials) don't fail just for constructing the service.
        return await embed(get_ai(request, "cloudflare"), model, texts)

    return embed_texts, model
