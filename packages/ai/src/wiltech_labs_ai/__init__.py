"""
wiltech-labs-ai: AI building blocks shared by Wiltech's FastAPI apps.

Workers AI / Groq / Ollama behind one protocol, with fallback between them, OpenAI-compatible tool
calling over plain httpx, embeddings, portable vector stores (database,
Vectorize, Qdrant), reciprocal rank fusion for hybrid search, and a
tool-calling agent loop.

This module is the entire public surface — import from `wiltech_labs_ai`,
not from its sub-packages.
"""
from wiltech_labs_ai.agents import (
    STEP_LIMIT_ANSWER,
    TOOL_RESULTS_ARE_DATA,
    AgentResult,
    Tool,
    ToolAgent,
    ToolCallRecord,
    ToolHandler,
)
from wiltech_labs_ai.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    MAX_EMBED_CHARS,
    EmbedFn,
    embed,
    embed_openai_compatible,
    get_embedder,
)
from wiltech_labs_ai.llm import OpenAICompatibleLlm, ToolLlm, chat_completion, get_tool_llm
from wiltech_labs_ai.providers import (
    AI,
    CHAT_OPTIONS,
    MODEL_CONFIG_KEYS,
    PROVIDERS_CONFIG_KEY,
    AiBindingAdapter,
    AiCandidate,
    AiHttpAdapter,
    ChatProvider,
    FallbackAI,
    FallbackReply,
    GroqAdapter,
    OpenAICompatibleChatAdapter,
    chat_model,
    get_ai,
    get_fallback_ai,
    provider_order,
    workers_ai_openai_base_url,
)
from wiltech_labs_ai.search import RRF_K, reciprocal_rank_fusion
from wiltech_labs_ai.vectors import (
    RESOURCE_EMBEDDINGS_TABLE_SQL,
    DatabaseVectorStore,
    QdrantVectorStore,
    VectorizeVectorStore,
    VectorMatch,
    VectorRecord,
    VectorStore,
    normalise,
)

__all__ = [
    "AI",
    "AgentResult",
    "AiBindingAdapter",
    "AiCandidate",
    "AiHttpAdapter",
    "CHAT_OPTIONS",
    "ChatProvider",
    "DEFAULT_EMBEDDING_MODEL",
    "DatabaseVectorStore",
    "EmbedFn",
    "FallbackAI",
    "FallbackReply",
    "GroqAdapter",
    "MAX_EMBED_CHARS",
    "MODEL_CONFIG_KEYS",
    "OpenAICompatibleChatAdapter",
    "OpenAICompatibleLlm",
    "PROVIDERS_CONFIG_KEY",
    "QdrantVectorStore",
    "RESOURCE_EMBEDDINGS_TABLE_SQL",
    "RRF_K",
    "STEP_LIMIT_ANSWER",
    "TOOL_RESULTS_ARE_DATA",
    "Tool",
    "ToolAgent",
    "ToolCallRecord",
    "ToolHandler",
    "ToolLlm",
    "VectorMatch",
    "VectorRecord",
    "VectorStore",
    "VectorizeVectorStore",
    "chat_completion",
    "chat_model",
    "embed",
    "embed_openai_compatible",
    "get_ai",
    "get_embedder",
    "get_fallback_ai",
    "get_tool_llm",
    "normalise",
    "provider_order",
    "reciprocal_rank_fusion",
    "workers_ai_openai_base_url",
]
