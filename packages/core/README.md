# wiltech-labs-core

The runtime plumbing every Wiltech FastAPI app copies into `core/`: config that reads the
Cloudflare Worker env or `.env`, the portable `Database` protocol (SQLite locally, D1 in a
Worker, D1 over HTTP anywhere else), the `AppError` family, per-request CORS and a health
router. See
[`docs/PYTHON_APP_CONVENTIONS.md`](https://github.com/wilferraciolli/py-libraries/blob/main/docs/PYTHON_APP_CONVENTIONS.md).

Pure Python. `aiosqlite` is an extra, so a Cloudflare Worker (D1 only) installs nothing it
can't load.

## Install

```bash
uv add "wiltech-labs-core[sqlite]"   # apps that run locally / in Docker on SQLite (all of them)
uv add wiltech-labs-core             # a Worker-only service that never touches SQLite
```

## Usage

```python
# main.py
from fastapi import FastAPI

from wiltech_labs_core import EnvCORSMiddleware, database_check, health_router, register_error_handlers

app = FastAPI(title="My API")
register_error_handlers(app)          # AppError subclasses -> {"detail": ...} + status
app.add_middleware(EnvCORSMiddleware) # CORS_ORIGINS read per request (works in Workers)
app.include_router(health_router({"db": database_check}), prefix="/api")
```

```python
# todos/todo_router.py
from fastapi import Depends, Request

from wiltech_labs_core import Database, get_database


def get_todo_service(request: Request) -> TodoService:
    return TodoService(TodoRepository(get_database(request)))
```

```python
# todos/todo_service.py
from wiltech_labs_core import NotFoundError


async def get(self, todo_id: str) -> TodoDTO:
    todo = await self.repository.find(todo_id)
    if todo is None:
        raise NotFoundError("Todo not found")      # -> 404 {"detail": "Todo not found"}
```

```python
# a write that must change two tables together (D1 has no interactive transactions)
await db.batch([
    ("UPDATE users SET role_ids = ? WHERE id = ?", (roles, user_id)),
    ("INSERT INTO audit_events (id, action, resource_id) VALUES (?, ?, ?)", (event_id, "user.roles", user_id)),
])
```

## Configuration

| Variable | Used by | Default |
|---|---|---|
| `DATABASE_MODE` | `get_database` | `d1_binding` if `env.DB` exists, else `sqlite` |
| `DATABASE_PATH` | sqlite | `./local.db` |
| `MIGRATIONS_DIR` | sqlite migrations | `./migrations` (relative to the working directory) |
| `CF_ACCOUNT_ID`, `CF_D1_DATABASE_ID`, `CF_D1_API_TOKEN` | d1_http | — |
| `CORS_ORIGINS` | `EnvCORSMiddleware` | none (comma-separated) |

Values come from the Worker env (`wrangler.jsonc` vars and secrets) first, then the process
environment. `.env` in the working directory is loaded into the process environment on
import, without overriding anything already set.

## Public API

| Name | What it is |
|---|---|
| `get_config(request, key, default=None)` | Config from the Worker env, else `os.environ` |
| `get_binding(request, name)` | A Cloudflare binding (`env.DB`, `env.AI`, `env.BUCKET`…) or `None` outside a Worker |
| `load_dotenv(path=None)` | Load `.env` (runs once on import) |
| `Database` | Protocol: `fetch_all`, `fetch_one`, `execute`, `execute_returning`, `batch` |
| `SQLiteDatabase`, `D1BindingDatabase`, `D1HttpDatabase` | The three adapters (SQLite turns on foreign keys; D1 binds `None` as `null` and returns rows as dicts) |
| `UniqueConstraintError` | Raised by every adapter when a UNIQUE constraint or index fails; repositories turn it into their own `ConflictError` |
| `get_database(request)` | Chooses an adapter from `DATABASE_MODE` / bindings |
| `Statement` | `tuple[str, tuple]`, one item of `batch` |
| `migrations_dir()` | The migrations folder, or a `RuntimeError` if it's missing |
| `AppError`, `NotFoundError` (404), `ForbiddenError` (403), `ConflictError` (409), `InvalidInputError` (422), `TooManyRequestsError` (429 + `Retry-After`), `UpstreamError` (502), `NotConfiguredError` (503) | Business errors services raise |
| `register_error_handlers(app)` | Maps `AppError` to its status code |
| `EnvCORSMiddleware(app, default_origins="")`, `allowed_origins(scope, default="")` | CORS with origins read per request (fallback `default_origins`); unhandled errors still get CORS headers |
| `health_router(checks=None, prefix="/health")`, `HealthCheck`, `database_check` | `GET /health`; 503 if any check fails |

### Guarded writes with `execute_returning`

D1 has no interactive transactions, so a state change that must not race is one statement, and
whether a row comes back says whether it won:

```python
row = await db.execute_returning(
    "UPDATE time_entries SET clock_out_at = ? WHERE id = ? AND clock_out_at IS NULL RETURNING id",
    (now, entry_id),
)
if row is None:
    raise ConflictError("You're not clocked in")
```

Each migration runs in one transaction with its `schema_migrations` row, so a migration that fails
half-way leaves nothing behind.

### `batch` atomicity

| Adapter | Atomic? |
|---|---|
| `SQLiteDatabase` | Yes, one transaction |
| `D1BindingDatabase` | Yes, D1 `batch()` |
| `D1HttpDatabase` | **No**: one request per statement, in order |

## Development

```bash
uv run --package wiltech-labs-core pytest packages/core
```

## Publishing

Publish **before** `wiltech-labs-auth` and `wiltech-labs-ai`, which depend on it.

```bash
cd packages/core

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
git commit -am "wiltech-labs-core <version>"
git tag core-v<version> && git push && git push --tags
```

A version number can only be uploaded once to each site. To retry after a fix, bump the
version and rebuild.
