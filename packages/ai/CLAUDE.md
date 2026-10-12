# wiltech-labs-ai

AI building blocks. See root `../../CLAUDE.md` for repo-wide conventions. The template has
no AI code, so everything here comes from `fastapi-ai` (`../PythonTutorials/Tutorials/fastapi-ai`):

| Here | Origin |
|---|---|
| `providers/ai.py` | `src/core/ai/ai.py`. `GroqAdapter` generalised to `OpenAICompatibleChatAdapter` (alias kept); new `local` provider (Ollama) |
| `llm/llm.py` | `src/core/ai/llm.py`. Errors are now `UpstreamError` (502) with the provider body logged, not returned (was `RuntimeError` with the body in the message); `tools` is omitted when empty. `get_tool_llm` is lifted from `assistant/assistant_router.py` |
| `embeddings/embeddings.py` | `src/core/ai/embeddings.py`, plus `embed_openai_compatible` and `EMBEDDING_PROVIDER=local` |
| `vectors/` | `src/core/ai/resource_vector_store.py` generalised: `VectorRecord` / `VectorMatch`, scopes as a list, `existing_ids` instead of `indexed_ids` (works on Vectorize too), chunked for D1's 100-parameter limit. Same `resource_embeddings` table. Vectorize and Qdrant adapters are new |
| `search/rrf.py` | The RRF loop repeated in `chats/`, `todos/` and `posts/` search services |
| `agents/` | `assistant/tools/tool.py` + the loop from `assistant/assistant_service.py`, without the app's DTOs or system prompt |

`fastapi-ai`'s chat-only `VectorStore` (`message_embeddings`, keyed by `chat_id`) isn't
ported. Chats can move to `DatabaseVectorStore(db, "chat_message")`, with a backfill.

## Rules

- No `openai` / vendor SDKs: plain `httpx`, with an injectable `transport` for tests.
- Every vector query filters by scope. Never add a query method without it.
- Tool handlers get `user_id` from the server. The agent never passes model-supplied ids
  through as identity.
- The Vectorize and Qdrant adapters are tested against the documented REST shapes with
  `httpx.MockTransport`, not live services. Smoke-test against a real index before relying
  on them.
