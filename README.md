# py-libraries

Wiltech's shared Python libraries for FastAPI apps, published to PyPI.

| Package | Import | Needs | What it is |
|---|---|---|---|
| [`wiltech-labs-rest`](packages/rest) | `wiltech_labs_rest` | — | Response envelope, links, field metadata, UTC dates |
| [`wiltech-labs-core`](packages/core) | `wiltech_labs_core` | — | Config (Worker env / `.env`), `Database` (SQLite / D1 binding / D1 HTTP + migrations + `batch`), `AppError` family, per-request CORS, health router, file storage (folder / R2) |
| [`wiltech-labs-auth`](packages/auth) | `wiltech_labs_auth` | core, rest | Clerk JWT, `Caller` with saved roles, `require_admin` / `require_owner`, pluggable caller lookup, service API keys, Clerk webhook verification, Clerk invitations |
| [`wiltech-labs-ai`](packages/ai) | `wiltech_labs_ai` | core | Workers AI / Groq / Ollama providers, tool-calling LLM, embeddings, `VectorStore` (database / Vectorize / Qdrant), RRF hybrid search, `ToolAgent` |
| [`wiltech-labs-holidays`](packages/holidays) | `wiltech_labs_holidays` | rest | A locale (`el-CY`) in, public holidays out in the shape `@wiltech-labs/ngx-calendar` shows; optional `holidays_router()` |

All apps follow [`docs/PYTHON_APP_CONVENTIONS.md`](docs/PYTHON_APP_CONVENTIONS.md).

## Development

A [uv](https://docs.astral.sh/uv/) workspace, so one `uv sync` at the root installs every package:

```bash
uv sync
uv run --package wiltech-labs-rest     pytest packages/rest
uv run --package wiltech-labs-core     pytest packages/core
uv run --package wiltech-labs-auth     pytest packages/auth
uv run --package wiltech-labs-ai       pytest packages/ai
uv run --package wiltech-labs-holidays pytest packages/holidays
```

## Publishing

Each package is released on its own, by hand, from its folder. Replace `<name>` with the
folder (`rest`, `core`, `auth`, `ai`, `holidays`):

```bash
cd packages/<name>

# 1. Test, bump, build
uv run pytest
uv version --bump patch                 # patch = fix, minor = new feature, major = breaking change
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
git commit -am "wiltech-labs-<name> <version>"
git tag <name>-v<version> && git push && git push --tags
```

- **Order matters.** A package's dependencies (the **Needs** column) must already be on PyPI:
  `rest` and `core` first, then `auth`, `ai` and `holidays`.
- **Versions are permanent.** A version number can only be uploaded once to each site. To retry
  after a fix, bump the version and rebuild.
- Apps depend on the published version only (`uv add wiltech-labs-<name>`), never a path or git
  source.

One-time setup (accounts and tokens), checking a TestPyPI release, fixing upload errors and using
a package in an app (Docker, Cloudflare): [`docs/PUBLISHING.md`](docs/PUBLISHING.md).
