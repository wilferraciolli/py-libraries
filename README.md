# py-libraries

Wiltech's shared Python libraries for FastAPI apps, published to PyPI.

| Package | Import | What it is |
|---|---|---|
| [`wiltech-labs-rest`](packages/rest) | `wiltech_labs_rest` | Response envelope, links, field metadata, UTC dates |
| [`wiltech-labs-core`](packages/core) | `wiltech_labs_core` | Config (Worker env / `.env`), `Database` (SQLite / D1 binding / D1 HTTP + migrations + `batch`), `AppError` family, per-request CORS, health router |
| [`wiltech-labs-auth`](packages/auth) | `wiltech_labs_auth` | Clerk JWT, `Caller` with saved roles, `require_admin` / `require_owner`, pluggable caller lookup, service API keys, Clerk webhook verification |
| [`wiltech-labs-ai`](packages/ai) | `wiltech_labs_ai` | Workers AI / Groq / Ollama providers, tool-calling LLM, embeddings, `VectorStore` (database / Vectorize / Qdrant), RRF hybrid search, `ToolAgent` |

All apps follow [`docs/PYTHON_APP_CONVENTIONS.md`](docs/PYTHON_APP_CONVENTIONS.md).

## Development

A [uv](https://docs.astral.sh/uv/) workspace, so one `uv sync` at the root installs every package:

```bash
uv sync
uv run --package wiltech-labs-rest pytest packages/rest
uv run --package wiltech-labs-core pytest packages/core
uv run --package wiltech-labs-auth pytest packages/auth
uv run --package wiltech-labs-ai   pytest packages/ai
```

Building, releasing to PyPI and using a package in an app: [`docs/PUBLISHING.md`](docs/PUBLISHING.md).
