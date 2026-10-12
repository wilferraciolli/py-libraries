# wiltech-labs-ai

AI building blocks for Wiltech FastAPI apps:

- **Providers**: Workers AI (binding or REST), Groq and **Ollama/any OpenAI-compatible
  server** behind one `AI` protocol.
- **Tool calling**: `OpenAICompatibleLlm` over plain `httpx` (no `openai` package, which costs
  about 1.4 s of CPU on a Python Worker cold start).
- **Embeddings**: Workers AI or Ollama.
- **Vector stores**: one `VectorStore` protocol with three adapters: the app's own database,
  Cloudflare Vectorize, Qdrant.
- **Hybrid search**: `reciprocal_rank_fusion` to merge vector and keyword rankings.
- **Agent loop**: `ToolAgent` runs tools as the server-supplied user and returns the answer
  with a trace.

Builds on [`wiltech-labs-core`](../core) (`get_config`, `Database`, errors). Pure Python
(`httpx`), so it runs in Cloudflare Workers.

## Install

```bash
uv add wiltech-labs-ai
```

## Usage

### Plain chat

```python
from wiltech_labs_ai import get_ai

ai = get_ai(request, provider)              # "cloudflare" | "groq" | "local"
reply = await ai.run(model, {"messages": [{"role": "user", "content": "Hello"}]})
reply["response"]
```

### "Ask your data": tools + agent

```python
from wiltech_labs_ai import TOOL_RESULTS_ARE_DATA, Tool, ToolAgent, get_tool_llm


async def count_todos(user_id: str, args: dict) -> dict:
    # user_id comes from the server (require_owner), never from the model
    return {"count": await todo_repository.count(user_id, state=args.get("state"))}


tools = [Tool("count_todos", "Count the user's todos, optionally by state.",
              {"type": "object", "properties": {"state": {"type": "string", "enum": ["NEW", "DONE"]}}},
              count_todos)]

llm, model = get_tool_llm(request, provider)      # 503 NotConfiguredError if a key is missing
result = await ToolAgent(llm, model, tools).run(user_id, [
    {"role": "system", "content": f"Answer questions about the user's data. {TOOL_RESULTS_ARE_DATA}"},
    {"role": "user", "content": question},
])
result.answer, result.tool_calls, result.completed
```

### Embeddings + vector store + hybrid search

```python
from wiltech_labs_ai import DatabaseVectorStore, VectorRecord, get_embedder, reciprocal_rank_fusion
from wiltech_labs_core import get_database

embed, model = get_embedder(request)
store = DatabaseVectorStore(get_database(request), namespace="todo")

# write path
[vector] = await embed([f"{todo.title}\n{todo.description or ''}"])
await store.upsert([VectorRecord(todo.id, scope=todo.user_id, vector=vector, model=model)])

# query path: meaning + exact words, fused
[query_vector] = await embed([q])
vector_hits = await store.query([user_id], query_vector, limit=30)
keyword_hits = await todo_repository.search_by_keyword(user_id, q, limit=30)
ranked = reciprocal_rank_fusion([m.id for m in vector_hits], [t.id for t in keyword_hits])

# backfill: embed only what's missing
missing = set(all_ids) - await store.existing_ids(all_ids)
```

`scope` is the tenancy boundary: the owner's user id for private data, or a group id for
group data (query with every group the caller can see). Every `query` filters by it.

#### Choosing a store

| Store | Where | Good for | Setup |
|---|---|---|---|
| `DatabaseVectorStore(db, namespace)` | SQLite / D1 | Thousands of vectors per scope; no extra infra | `RESOURCE_EMBEDDINGS_TABLE_SQL` migration (the same table as `fastapi-ai` migration 007) |
| `VectorizeVectorStore(account, token, index, namespace)` | Cloudflare (free: ~5M stored dimensions, about 6.5k vectors at 768 dims) | Larger data on Cloudflare | `wrangler vectorize create <index> --dimensions=768 --metric=cosine` **and** `wrangler vectorize create-metadata-index <index> --propertyName=scope --type=string` |
| `QdrantVectorStore(url, collection, namespace, api_key)` | Home server (`qdrant/qdrant`) | No practical limit, private | `await store.ensure_collection(768)` once |

All three are interchangeable behind `VectorStore`. Switching store means re-embedding
(run your backfill against the new store).

## Configuration

| Variable | Used by | Default |
|---|---|---|
| `AI_MODE` | `get_ai("cloudflare")` | `binding` if `env.AI` exists, else `http` |
| `CF_AI_ACCOUNT_ID`, `CF_AI_API_TOKEN` | Workers AI REST, `get_tool_llm("cloudflare")` | — |
| `CF_AI_MODEL` | `get_tool_llm("cloudflare")` | — |
| `GROQ_API_KEY`, `GROQ_BASE_URL`, `GROQ_MODEL` | Groq | — |
| `LOCAL_LLM_BASE_URL` | Ollama / local | `http://localhost:11434/v1` (in Docker: `http://ollama:11434/v1`) |
| `LOCAL_LLM_API_KEY` | local | `ollama` |
| `LOCAL_LLM_MODEL` | `get_tool_llm("local")` | — (e.g. `qwen3:8b`) |
| `EMBEDDING_PROVIDER` | `get_embedder` | `cloudflare` (or `local`) |
| `CF_EMBEDDING_MODEL` | `get_embedder` | `@cf/baai/bge-base-en-v1.5` (English only; `@cf/baai/bge-m3` for Greek/Portuguese) |
| `LOCAL_EMBEDDING_MODEL` | `get_embedder` (local) | `bge-m3` |

## Public API

| Name | What it is |
|---|---|
| `AI`, `get_ai(request, provider)`, `ChatProvider` | Run a model: `run(model, inputs) -> dict` |
| `AiBindingAdapter`, `AiHttpAdapter`, `OpenAICompatibleChatAdapter` (alias `GroqAdapter`) | The adapters |
| `workers_ai_openai_base_url(account_id)` | `…/accounts/{id}/ai/v1` |
| `ToolLlm`, `OpenAICompatibleLlm`, `chat_completion`, `get_tool_llm(request, provider)` | Tool-calling chat completions; errors are `UpstreamError` (502), with the provider's body logged, not returned |
| `embed`, `embed_openai_compatible`, `get_embedder`, `EmbedFn`, `DEFAULT_EMBEDDING_MODEL`, `MAX_EMBED_CHARS` | Embeddings (batched by 50, truncated to 2,000 chars) |
| `VectorStore`, `VectorRecord`, `VectorMatch`, `normalise` | The vector protocol |
| `DatabaseVectorStore`, `RESOURCE_EMBEDDINGS_TABLE_SQL`, `VectorizeVectorStore`, `QdrantVectorStore` | The stores |
| `reciprocal_rank_fusion(*rankings, k=60)`, `RRF_K` | Hybrid-search fusion |
| `Tool`, `ToolHandler`, `ToolAgent`, `AgentResult`, `ToolCallRecord`, `STEP_LIMIT_ANSWER`, `TOOL_RESULTS_ARE_DATA` | The agent loop |

## Development

```bash
uv run --package wiltech-labs-ai pytest packages/ai
```

## Publishing

Publish `wiltech-labs-core` first; this package depends on it.

```bash
cd packages/ai

# 1. Test, bump, build
uv run pytest
uv version --bump patch                 # or minor / major; skip for the first 0.1.0
rm -rf ../../dist && uv build           # -> ../../dist/

# 2. TestPyPI (optional rehearsal), using a token from test.pypi.org
read -rsp "TestPyPI token: " UV_PUBLISH_TOKEN && export UV_PUBLISH_TOKEN && echo
uv publish --index testpypi ../../dist/*
unset UV_PUBLISH_TOKEN

# 3. PyPI (the real thing), using a token from pypi.org
read -rsp "PyPI token: " UV_PUBLISH_TOKEN && export UV_PUBLISH_TOKEN && echo
uv publish ../../dist/*
unset UV_PUBLISH_TOKEN

# 4. Commit and tag
git commit -am "wiltech-labs-ai <version>"
git tag ai-v<version> && git push && git push --tags
```

A version number can only be uploaded once to each site. To retry after a fix, bump the
version and rebuild.
