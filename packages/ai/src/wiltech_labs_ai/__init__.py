"""
wiltech-labs-ai: AI building blocks shared by Wiltech's FastAPI apps.

Workers AI / Groq / Ollama behind one protocol, OpenAI-compatible tool
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
    AiBindingAdapter,
    AiHttpAdapter,
    ChatProvider,
    GroqAdapter,
    OpenAICompatibleChatAdapter,
    get_ai,
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
    "DEFAULT_EMBEDDING_MODEL",
    "MAX_EMBED_CHARS",
    "RESOURCE_EMBEDDINGS_TABLE_SQL",
    "RRF_K",
    "STEP_LIMIT_ANSWER",
    "TOOL_RESULTS_ARE_DATA",
    "AgentResult",
    "AiBindingAdapter",
    "AiHttpAdapter",
    "ChatProvider",
    "DatabaseVectorStore",
    "EmbedFn",
    "GroqAdapter",
    "OpenAICompatibleChatAdapter",
    "OpenAICompatibleLlm",
    "QdrantVectorStore",
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
    "embed",
    "embed_openai_compatible",
    "get_ai",
    "get_embedder",
    "get_tool_llm",
    "normalise",
    "reciprocal_rank_fusion",
    "workers_ai_openai_base_url",
]
