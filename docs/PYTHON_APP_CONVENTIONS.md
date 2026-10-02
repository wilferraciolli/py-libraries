# Python FastAPI application conventions

These conventions are intended for AI agents and developers creating new Python
FastAPI applications. Read this file before generating or modifying a Python
API project.

The default target is a **portable local-development-first FastAPI app**:

- Runs locally with `uvicorn` and SQLite.
- Runs in Docker with the same SQLite behavior.
- Can be deployed to Cloudflare Workers with D1.
- Keeps business logic independent from the hosting provider.
- Uses a consistent response envelope for all non-delete API responses.

## Core principles

1. Keep the application portable.
2. Prefer local development that works without cloud login.
3. Do not couple repositories or services directly to Cloudflare, Wrangler, or
   any other hosting-specific SDK.
4. Build metadata, links, permissions, and the typed `ApiResponse` envelope
   in the application service layer per request.
5. Use UUIDs for public resource identifiers.
6. Use UTC date-times in API responses.
7. Keep delete endpoints simple: `204 No Content`, no response body.
8. Use small, explicit layers: router -> application service -> repository ->
   database adapter.
9. Avoid hidden magic and framework-specific shortcuts that make the code hard
   to move to another host.
10. Make the local setup easy enough that a new developer can run the app in
    minutes.
11. Every project runs locally on the **same port, `8001`** — never invent a
    per-project port. The `showcase` Angular app's API base URL
    (`environment.apiUrl` / `API_ORIGIN`) is a single fixed value, not one
    per backend, so only one Python service is ever meant to be running
    locally at a time. Switch which project is running (stop one, start the
    next) instead of giving each project its own port.

## Recommended project structure
Organize by domain, not by file type. One package per bounded context.
Use this structure for new FastAPI APIs:

```text
my-python-api/
├── src/
│   ├── main.py                    # Plain FastAPI app for uvicorn/Docker; registers routers
│   ├── entry.py                   # Optional Cloudflare Worker ASGI entrypoint
│   ├── core/                      # Cross-cutting code. Never imports a domain package.
│   │   ├── common/
│   │   │   ├── api_response.py    # ApiResponse envelope + API_PREFIX
│   │   │   ├── base_dto.py        # Link, LinkedResource, EmbeddedRef, FieldMetadata, Message
│   │   │   └── serializers.py     # UTC date formatting
│   │   ├── config/
│   │   │   ├── config.py          # Runtime config from env / .env / Worker env
│   │   │   └── database.py        # Database protocol, adapters, migration runner
│   │   └── security/
│   │       ├── auth.py            # Token verification -> AuthenticatedUser
│   │       ├── authorization.py   # Caller, get_caller, require_admin
│   │       └── roles.py           # UserRole, role labels/options
│   ├── shared/                    # Data owned by several domains (e.g. settings)
│   └── {domain}/                  # e.g. users/, todos/ — one package per bounded context
│       ├── {domain}_router.py     # HTTP only
│       ├── {domain}_service.py    # Business rules, links, metadata, envelope
│       ├── {domain}_repository.py # SQL -> {Name}Model
│       ├── models.py              # Database row models: {Name}Model
│       ├── schemas.py             # Request, DTO, Metadata classes + Response aliases
│       ├── constants.py           # `_data` key names, link names
│       ├── exceptions.py          # Domain exceptions the router maps to HTTP errors
│       ├── enums.py               # Domain enums, when there are any
│       └── {sub_resource}/        # Same layout, e.g. users/settings/
├── migrations/
│   └── 001_create_tables.sql      # Applied automatically to local SQLite
├── schema.sql                     # Snapshot of all migrations, for Cloudflare D1
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
└── README.md
```

Rules:

- `core/` holds only cross-cutting code and never imports a domain package.
  When `core/` needs domain data (e.g. the caller's roles), read it through a
  database view (see "Database views").
- `models.py` is only for database row models (`{Name}Model`). Request, DTO
  and Metadata classes, and the `{Name}Response` aliases, go in `schemas.py`
  (see "Model, Request, DTO and Response conventions").
- A sub-resource (`/users/{id}/settings`) gets its own sub-package with the
  same layout.

Choose one structure and stay consistent.

## Runtime targets

Every app should be designed around these runtime targets unless the user says
otherwise.

### 1. Local uvicorn + SQLite

This is the default local developer workflow.

Use it when:

- Developing on Windows, macOS, or Linux.
- Running without Cloudflare login.
- Running without Docker.
- Teaching or learning Python/FastAPI.
- Quickly testing endpoints and response shapes.

Expected command:

```powershell
uv sync
uv run uvicorn main:app --app-dir src --host 127.0.0.1 --port 8001 --reload
```

Recommended `fastapi-cloudflare-d1/.env` values:

```env
DATABASE_MODE=sqlite
DATABASE_PATH=./local.db
MIGRATIONS_DIR=./migrations
```

### 2. Docker + SQLite

Docker should behave like local uvicorn, but with the SQLite database stored in
a named Docker volume.

Use it when:

- A developer wants reproducible local setup.
- The team uses Docker Compose.
- The app may later move to another container host.

Recommended `../fastapi-cloudflare-d1/docker-compose.yml` pattern:

```yaml
services:
  api:
    build: ../fastapi-cloudflare-d1
    ports:
      - "8001:8001"
    env_file:
      - path: fastapi-cloudflare-d1/.env
        required: false
    environment:
      DATABASE_MODE: sqlite
      DATABASE_PATH: /data/local.db
      MIGRATIONS_DIR: /app/migrations
    volumes:
      - ./src:/app/src
      - ./migrations:/app/migrations
      - sqlite-data:/data
    command:
            [
              "uv",
              "run",
              "uvicorn",
              "main:app",
              "--app-dir",
              "src",
              "--host",
              "0.0.0.0",
              "--port",
              "8001",
              "--reload",
            ]

volumes:
  sqlite-data:
```

This avoids a fragile host-path database file and behaves consistently on
Windows, macOS, and Linux.

### 3. Cloudflare Workers + D1

Cloudflare is an optional deployment target, not something the whole app should
depend on.

Use it when:

- The user explicitly wants Cloudflare Workers.
- The app already has `wrangler.jsonc`.
- The app uses Cloudflare D1.

Cloudflare-specific code should be limited to:

- `entry.py`
- `wrangler.jsonc`
- D1 database adapter implementation
- Cloudflare deployment docs

Do not put Cloudflare-specific APIs in routers, services, or repositories.

The Worker entrypoint should wrap the same `app` from `main.py`:

```python
from workers import asgi

from main import app

fetch = asgi.fetch(app)
```

The app should prefer the native D1 binding inside Cloudflare Workers:

```env
DATABASE_MODE=d1_binding
```

If `DATABASE_MODE` is omitted and `env.DB` exists, the app may default to
`d1_binding`.

### 4. Cloudflare D1 over HTTP

D1 HTTP is optional. It exists for non-Worker runtimes that still want to use
Cloudflare D1.

Use it when:

- Hosting on Render, Railway, Azure, or another platform.
- The database remains Cloudflare D1.
- The runtime cannot access `env.DB`.

Recommended config:

```env
DATABASE_MODE=d1_http
CF_ACCOUNT_ID=...
CF_D1_DATABASE_ID=...
CF_D1_API_TOKEN=...
```

Do not use D1 HTTP from inside Cloudflare Workers if the native binding is
available.

## Dependency and tooling conventions

Use `uv` for Python dependency and virtual environment management.

Recommended `pyproject.toml` baseline:

```toml
[project]
name = "my-python-api"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "aiosqlite",
    "fastapi",
    "httpx",
    "uvicorn",
]

[dependency-groups]
dev = []
```

If deploying to Cloudflare Python Workers, add:

```toml
[dependency-groups]
dev = [
    "workers-py",
    "workers-runtime-sdk",
]
```

Commit both:

- `pyproject.toml`
- `uv.lock`

Do not commit:

- `.venv/`
- `.env`
- SQLite local database files
- Wrangler generated state

Recommended `.gitignore` entries:

```gitignore
.env
.dev.vars
.venv/
.venv-workers/
.wrangler/
python_modules/
__pycache__/
*.pyc
local.db
*.db
```

## Configuration conventions

The app should read configuration from:

1. Cloudflare Worker request env, when running inside Workers.
2. Process environment variables.
3. A local `.env` file for uvicorn/Docker development.

Use `.env.example` for safe committed defaults:

```env
# Local uvicorn/Docker mode
DATABASE_MODE=sqlite
DATABASE_PATH=./local.db

# Cloudflare Worker native D1 binding
# DATABASE_MODE=d1_binding

# Optional non-Worker D1 HTTP mode
# DATABASE_MODE=d1_http
# CF_ACCOUNT_ID=...
# CF_D1_DATABASE_ID=...
# CF_D1_API_TOKEN=...
```

Only one `DATABASE_MODE` should be active at a time. Do not keep multiple
active `DATABASE_MODE=` lines in the same `.env`; the last one may win.

## Database abstraction convention

Repositories should depend on a protocol, not a concrete database client.

Recommended protocol:

```python
from typing import Any, Optional, Protocol


class Database(Protocol):
    async def fetch_all(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]: ...

    async def fetch_one(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> Optional[dict[str, Any]]: ...

    async def execute(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> None: ...
```

Repositories should only call this protocol:

```python
class TodoRepository:
    def __init__(self, db: Database):
        self.db = db

    async def get_by_id(self, todo_id: str) -> dict[str, Any] | None:
        return await self.db.fetch_one(
            "SELECT * FROM todos WHERE id = ?",
            (todo_id,),
        )
```

Avoid this in repositories:

```python
# Do not do this in repositories.
request.scope["env"].DB.prepare(...)
```

Cloudflare, SQLite, PostgreSQL, D1 HTTP, or any other storage technology should
be hidden behind adapters.

## Migration conventions

For portable local development, put SQLite-compatible migrations in:

```text
migrations/
```

Each migration should be named with a sortable prefix:

```text
002_create_tables.sql
002_add_user_roles.sql
003_add_indexes.sql
```

The SQLite adapter should apply each migration once and track applied files in
a `schema_migrations` table:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY
);
```

For Cloudflare D1, keep `schema.sql` when useful for Wrangler:

```powershell
npx wrangler d1 execute todo-db --local --file=./schema.sql
npx wrangler d1 execute todo-db --remote --file=./schema.sql
```

Where possible, keep `schema.sql` and `migrations/` compatible. If they drift,
document why.

Rules:

- The migrations folder comes from the `MIGRATIONS_DIR` environment variable,
  defaulting to `./migrations` relative to the working directory. Do not
  compute it from `__file__` (`parents[3]`): that breaks whenever files move.
  Docker sets `MIGRATIONS_DIR=/app/migrations` in both the `Dockerfile` and
  `docker-compose.yml`.
- Fail at startup if the folder does not exist. A missing folder must never
  silently mean "no migrations to run".
- `schema.sql` is a snapshot of every migration in order, with a header naming
  the migrations it covers. Update it in the same change as a new migration.
- Seed rows in `schema.sql` use `INSERT OR IGNORE`, so re-running the file
  against D1 does not fail. Migrations themselves use plain `INSERT`; each
  runs once.
- Local SQLite applies new migrations automatically. D1 does not: apply each
  new migration file with `wrangler d1 execute --file=...`.

## Identifier conventions

Use UUID strings for public resource IDs.

Do this:

```python
from uuid import uuid4

todo_id = str(uuid4())
```

Database columns should be text:

```sql
id TEXT PRIMARY KEY
resource_id TEXT NOT NULL
```

Avoid integer autoincrement IDs for public APIs unless there is a strong reason.

Reasons:

- UUIDs are portable across SQLite, D1, PostgreSQL, and other databases.
- UUIDs avoid dependency on database-specific `last_insert_id` behavior.
- UUIDs do not leak creation volume or ordering.
- UUIDs work well when resources may later be created in distributed systems.

## Date and time conventions

All API date-times should be UTC and formatted with second precision:

```text
YYYY-MM-DDTHH:MM:SSZ
```

Example:

```json
"created_date": "2026-09-21T13:47:02Z"
```

Do not return:

```text
2026-09-21T13:47:02.123456+00:00
2026-09-21 13:47:02
09/21/2026
```

Recommended serializer helper:

```python
from datetime import datetime, timezone


def format_utc_datetime(value: datetime | str) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
```

When storing dates in SQLite/D1, store ISO-compatible UTC strings. When
returning dates, serialize them through the same formatting helper.

## Layering conventions

### Router layer

Routers should:

- Define HTTP paths and methods.
- Parse route/query/body inputs.
- Call the application service.
- Convert known service failures into HTTP errors.
- Return the service's response (`service.build_response(...)`).

Routers should not:

- Contain business rules.
- Build metadata.
- Build links.
- Open database connections directly.
- Know whether the database is SQLite or D1.

Example:

```python
from fastapi import APIRouter, Depends, HTTPException, Request

from core.config.database import get_database
from todos.schemas import TodoResponse
from todos.todo_repository import TodoRepository
from todos.todo_service import TodoService

router = APIRouter(prefix="/todos", tags=["todos"])


def get_todo_service(request: Request) -> TodoService:
    db = get_database(request)
    return TodoService(TodoRepository(db))


@router.get("/{todo_id}")
async def get_todo(
    todo_id: str,
    service: TodoService = Depends(get_todo_service),
) -> TodoResponse:
    todo = await service.get_by_id(todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return service.build_response(todo)
```

### Application service layer

Application services should:

- Own business rules.
- Generate UUIDs.
- Apply state transitions.
- Turn the repository's `Model` into a `DTO`.
- Build the `ApiResponse` envelope (`build_response`), passing the DTO into
  `build_metadata` so metadata can depend on the resource's current state.
- Build resource links.
- Build metadata per request.
- Build meta links per request.
- Add optional messages when useful.
- Coordinate multiple repositories when one business operation affects more
  than one resource.

Application services should not:

- Depend on FastAPI `Request` unless request context is genuinely needed.
- Return raw database rows directly without DTO shaping.
- Contain host-specific code.

Helpers that don't use instance state are `@staticmethod` and take no
`self`. Do not combine the two: `@staticmethod def build_links(self, id)`
makes `self.build_links(id)` fail with a missing-argument `TypeError`.

This is the correct place for dynamic rules such as:

- Remove `NEW` from available state values once a todo is already started.
- Hide `deleteTodo` link if the user does not have permission.
- Add an `overdue` tag if `complete_by` is before today.
- Add a `not-started` tag if `complete_by` is in the future and state is
  `NEW`.
- Omit metadata for optional fields that have no client rule.

### Repository layer

Repositories should:

- Contain SQL.
- Accept a `Database` protocol implementation.
- Return typed `Model` objects (one per table row), not raw dictionaries.
- Convert rows in one private helper, `_to_model(row)`, returning None for no
  row.
- Take explicit, optional arguments for partial updates
  (`update(user_id, name=None, email=None, role_ids=None)`), not `**fields`.
- Read through a view when one model spans several tables (e.g. a user plus
  their roles), rather than one extra query per row.
- Use parameterized SQL only.

Repositories should not:

- Build response envelopes.
- Know about HTTP.
- Know about Cloudflare.
- Know about FastAPI.
- Generate UUIDs unless explicitly agreed.
- Decide permissions.
- Decide UI metadata.

### Database adapter layer

Database adapters should:

- Translate the common `Database` protocol into a concrete backend.
- Own backend-specific details.
- Normalize rows into `dict[str, Any]` where possible.

Examples:

- `SQLiteDatabase`
- `D1BindingDatabase`
- `D1HttpDatabase`
- `PostgresDatabase`

Keep optional backend imports lazy if they may not work in every runtime. For
example, import `aiosqlite` only inside the SQLite adapter methods if the app is
also packaged for Cloudflare Workers.

## Response envelope convention

All successful non-delete API responses should use this envelope:

```json
{
  "_data": {},
  "_metadata": {},
  "_metaLinks": {},
  "_messages": []
}
```

Rules:

- `_data` is required.
- `_metadata` is required, but may be an empty object.
- `_metaLinks` is required, but may be an empty object.
- `_messages` is required, but may be an empty array.
- Delete endpoints return `204 No Content` and no response body.
- The health check (`/health`) is the one exception: it is an
  infrastructure probe, not a resource, and returns a plain JSON object.

### Typed envelope: `ApiResponse`

Build the envelope with the one generic class in
`core/common/api_response.py`. Do not write per-resource `...Data` or
`...Response` envelope classes, and do not return hand-built dicts.

```python
from typing import Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from core.common.base_dto import Link

DataT = TypeVar("DataT")
MetadataT = TypeVar("MetadataT")


class ApiResponse(BaseModel, Generic[DataT, MetadataT]):
    model_config = ConfigDict(populate_by_name=True)

    data: Dict[str, DataT] = Field(alias="_data")
    metadata: MetadataT = Field(alias="_metadata")
    meta_links: Dict[str, Link] = Field(default_factory=dict, alias="_metaLinks")
    messages: List[Dict[str, str]] = Field(default_factory=list, alias="_messages")

    @classmethod
    def of(
            cls,
            data_name: str,
            data: DataT,
            metadata: MetadataT,
            meta_links: Optional[Dict[str, Link]] = None,
            messages: Optional[List[Dict[str, str]]] = None,
    ) -> "ApiResponse[DataT, MetadataT]":
        return cls(
            data={data_name: data},
            metadata=metadata,
            meta_links=meta_links or {},
            messages=messages or [],
        )
```

Each domain names its concrete response type once in `schemas.py`. The
service builds it; the router uses it as the endpoint's return type, so the
OpenAPI schema is fully typed:

```python
# schemas.py
UserSettingsResponse = ApiResponse[UserSettingsDTO, UserSettingsMetadata]


# user_settings_service.py
def build_metadata(self, user_settings: UserSettingsDTO) -> UserSettingsMetadata:
    # Rules can depend on the resource's current state.
    ...

def build_response(self, user_settings: UserSettingsDTO) -> UserSettingsResponse:
    return UserSettingsResponse.of(
        USER_SETTINGS_DATA_NAME,
        user_settings,
        self.build_metadata(user_settings),
    )


# user_settings_router.py
@router.get("")
async def get_user_settings(...) -> UserSettingsResponse:
    ...
    return service.build_response(user_settings)
```

Rules:

- The `_data` key name is a constant in the domain's `constants.py` (e.g.
  `USER_SETTINGS_DATA_NAME = "userSettings"`), next to the link names. Never
  inline the string.
- Use a camelCase resource name for the key: `userSettings`, not `settings`
  or `user_settings`.
- `_messages` is always present; it is an empty array when there is nothing
  to say.
- `FieldMetadata` drops its own unset flags. Do not add
  `response_model_exclude_none=True` to routes; it would also strip `None`
  fields out of the DTO, and a client expects an optional field to be present
  as `null`.
- Do not put a return type annotation on that `model_serializer` method.
  Pydantic uses it for the OpenAPI schema, so `-> Dict[str, Any]` would turn
  the documented response into a bare `object`.
- `_data` is typed `Dict[str, DataT]`, so OpenAPI shows the key as "any
  string". That is the accepted trade-off for not writing one envelope class
  per resource.

### Single resource response

For one resource, `_data` should contain a named object:

```json
{
  "_data": {
    "todo": {
      "id": "32fe8c7a-3f19-4f83-9104-23d1e59e4b9f",
      "title": "Learn FastAPI",
      "description": "Build a portable API",
      "complete_by": "2026-12-31T23:59:59Z",
      "state": "NEW",
      "created_date": "2026-09-21T13:47:02Z",
      "links": {
        "self": {
          "href": "/todos/32fe8c7a-3f19-4f83-9104-23d1e59e4b9f",
          "method": "GET"
        },
        "update": {
          "href": "/todos/32fe8c7a-3f19-4f83-9104-23d1e59e4b9f",
          "method": "PUT"
        },
        "delete": {
          "href": "/todos/32fe8c7a-3f19-4f83-9104-23d1e59e4b9f",
          "method": "DELETE"
        }
      }
    }
  },
  "_metadata": {
    "id": {
      "readOnly": true,
      "hidden": true
    },
    "title": {
      "mandatory": true
    },
    "complete_by": {
      "mandatory": true
    },
    "state": {
      "mandatory": true,
      "values": [
        {
          "id": "NEW",
          "value": "New"
        },
        {
          "id": "ACTIVE",
          "value": "Active"
        },
        {
          "id": "CLOSED",
          "value": "Closed"
        }
      ]
    },
    "created_date": {
      "readOnly": true
    }
  },
  "_metaLinks": {
    "createTodo": {
      "href": "/todos",
      "method": "POST"
    }
  }
}
```

### Collection response

For arrays, keep the same named resource key and make its value an array.
Type it as `ApiResponse[list[{Name}DTO], {Name}Metadata]`
(`UserListResponse`), with the plural key from `constants.py`
(`USERS_DATA_NAME = "users"`):

```json
{
  "_data": {
    "todos": [
      {
        "id": "32fe8c7a-3f19-4f83-9104-23d1e59e4b9f",
        "title": "Learn FastAPI",
        "complete_by": "2026-12-31T23:59:59Z",
        "state": "NEW",
        "created_date": "2026-09-21T13:47:02Z",
        "links": {
          "self": {
            "href": "/todos/32fe8c7a-3f19-4f83-9104-23d1e59e4b9f",
            "method": "GET"
          }
        }
      }
    ]
  },
  "_metadata": {
    "id": {
      "readOnly": true,
      "hidden": true
    },
    "title": {
      "mandatory": true
    },
    "complete_by": {
      "mandatory": true
    },
    "state": {
      "mandatory": true,
      "values": [
        {
          "id": "NEW",
          "value": "New"
        },
        {
          "id": "ACTIVE",
          "value": "Active"
        },
        {
          "id": "CLOSED",
          "value": "Closed"
        }
      ]
    }
  },
  "_metaLinks": {
    "createTodo": {
      "href": "/todos",
      "method": "POST"
    }
  }
}
```

### Template response

Template endpoints should return the shape needed to create a new resource.

The template's `_data` is the `{Name}CreateRequest` itself, filled with
defaults, so the form starts from exactly the shape it will POST:

```python
UserTemplateResponse = ApiResponse[UserCreateRequest, UserTemplateMetadata]

UserTemplateResponse.of(USER_DATA_NAME, UserCreateRequest(name="", email=""), ...)
```

Do not include server-generated or persisted-only fields:

- No fake UUID.
- No `id`.
- No `created_date`.
- No resource-level `links`.

Example:

```json
{
  "_data": {
    "todo": {
      "title": "",
      "description": "",
      "complete_by": "2026-09-21T13:47:02Z",
      "state": "NEW"
    }
  },
  "_metadata": {
    "title": {
      "mandatory": true
    },
    "complete_by": {
      "mandatory": true
    },
    "state": {
      "mandatory": true,
      "values": [
        {
          "id": "NEW",
          "value": "New"
        },
        {
          "id": "ACTIVE",
          "value": "Active"
        },
        {
          "id": "CLOSED",
          "value": "Closed"
        }
      ]
    }
  },
  "_metaLinks": {
    "createTodo": {
      "href": "/todos",
      "method": "POST"
    }
  }
}
```

Templates are especially useful for create-only helper resources such as tags:

```json
{
  "_data": {
    "tag": {
      "resource_id": "",
      "tag": ""
    }
  },
  "_metadata": {
    "resource_id": {
      "mandatory": true
    },
    "tag": {
      "mandatory": true
    }
  },
  "_metaLinks": {
    "createTag": {
      "href": "/tags",
      "method": "POST"
    }
  }
}
```

## Metadata conventions

Metadata is not a full schema dump. It exists to tell the client about dynamic
UI/business rules.

Use metadata for:

- Required fields.
- Read-only fields.
- Hidden fields.
- Disabled fields.
- Available enum/select values.
- Business-rule-driven choices.

Do not add metadata for every field automatically.

If a field is optional and has no rule, omit it from `_metadata`.

Good metadata:

```json
{
  "title": {
    "mandatory": true
  },
  "state": {
    "mandatory": true,
    "values": [
      {
        "id": "ACTIVE",
        "value": "Active"
      },
      {
        "id": "CLOSED",
        "value": "Closed"
      }
    ]
  }
}
```

Unhelpful metadata:

```json
{
  "description": {}
}
```

Option lists used by several resources are built in one place. For example,
`role_options()` in `core/security/roles.py` builds the `roleIds` values with
their display labels. Do not copy the labels into each service.

Type metadata with a per-resource `{Resource}Metadata` class whose fields are
the shared `FieldMetadata` from `core/common/base_dto.py`. Use `EmbeddedRef`
(`{id, value}`) for each option in `values`:

```python
class FieldMetadata(BaseModel):
    readOnly: Optional[bool] = None
    hidden: Optional[bool] = None
    mandatory: Optional[bool] = None
    values: Optional[list[EmbeddedRef]] = None

    @model_serializer(mode="wrap")
    def _omit_unset_flags(self, handler: SerializerFunctionWrapHandler):
        # Only the flags that were set appear in the response.
        return {key: value for key, value in handler(self).items() if value is not None}


class TodoMetadata(BaseModel):
    title: FieldMetadata
    state: FieldMetadata
```

Metadata should be built in the application service layer because it may depend
on:

- Current resource state.
- Current user.
- Roles/permissions.
- Feature flags.
- Business date/time.
- Tenant or organisation settings.

Example rule:

If a todo has already moved from `NEW` to `ACTIVE`, then `NEW` should no longer
appear as an available state value.

## Link conventions

There are two kinds of links.

### Resource links

Resource links live inside each returned resource:

```json
{
  "id": "32fe8c7a-3f19-4f83-9104-23d1e59e4b9f",
  "title": "Learn FastAPI",
  "links": {
    "self": {
      "href": "/todos/32fe8c7a-3f19-4f83-9104-23d1e59e4b9f",
      "method": "GET"
    },
    "update": {
      "href": "/todos/32fe8c7a-3f19-4f83-9104-23d1e59e4b9f",
      "method": "PUT"
    },
    "delete": {
      "href": "/todos/32fe8c7a-3f19-4f83-9104-23d1e59e4b9f",
      "method": "DELETE"
    },
    "tags": {
      "href": "/tags?resource_id=32fe8c7a-3f19-4f83-9104-23d1e59e4b9f",
      "method": "GET"
    }
  }
}
```

Resource links should be dynamic. For example, do not include a `delete` link
if the current user cannot delete the resource.

Pass the `Caller` (see "Authentication and authorization conventions") into
the service so links match what the API will actually allow:

```python
@staticmethod
def build_links(user_id: str, caller: Caller) -> dict[str, Link]:
    url = f"{API_PREFIX}/users/{user_id}"
    links = {LINK_SELF: Link(href=url, method="GET")}

    if caller.is_admin:
        links[LINK_UPDATE_USER] = Link(href=url, method="PUT")
        # The API refuses deleting yourself, so don't offer it.
        if user_id != caller.user_id:
            links[LINK_DELETE_USER] = Link(href=url, method="DELETE")

    return links
```

The same applies to meta links: `createUser` and `userTemplate` are only
offered to callers who may create users.

Link names are constants in the domain's `constants.py` (`LINK_SELF`,
`LINK_UPDATE_USER`, ...), never inline strings.

### Meta links

Meta links live at the envelope level:

```json
{
  "_metaLinks": {
    "createTodo": {
      "href": "/todos",
      "method": "POST"
    },
    "todoTemplate": {
      "href": "/todos/template",
      "method": "GET"
    }
  }
}
```

Use meta links for actions that apply to the page, collection, or resource type
rather than one specific row.

Examples:

- `createTodo`
- `todoTemplate`
- `createTag`
- `tagTemplate`
- `searchTags`

Like metadata, links should be built in the application service layer per
request.

## Message conventions

`_messages` is always present. It is an empty array when there are no
messages:

```json
{
  "_data": {},
  "_metadata": {},
  "_metaLinks": {},
  "_messages": []
}
```

Add entries only when there is something useful for the client/user:

```json
{
  "_messages": [
    {
      "type": "INFO",
      "value": "Your settings apply from your next sign-in."
    }
  ]
}
```

Messages are typed: `Message(type=MessageType.INFO, value="...")` from
`core/common/base_dto.py`. `MessageType` is one of:

- `INFO`
- `WARNING`
- `ERROR`
- `SUCCESS`

Do not use `_messages` for validation errors if the API already returns proper
HTTP validation responses.

## Delete endpoint convention

Delete endpoints should return:

```text
204 No Content
```

Rules:

- No response envelope.
- No response body.
- No `_messages`.
- Return `404` if the resource does not exist.

Example:

```python
from fastapi import Response


@router.delete("/{todo_id}", status_code=204)
async def delete_todo(todo_id: str, service: TodoService = Depends(get_todo_service)):
    deleted = await service.delete(todo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Todo not found")
    return Response(status_code=204)
```

## Model, Request, DTO and Response conventions

Use typed Pydantic classes at every layer, one class per layer, with the layer
as the class-name suffix. Do not pass `dict[str, Any]` between layers.

| Layer | Suffix | Lives in | Built by | Holds |
|---|---|---|---|---|
| Database row (entity) | `Model` | `models.py` | repository | exactly the table's columns |
| Request body | `Request` | `schemas.py` | client; FastAPI validates it | only the fields the client may send |
| Service result | `DTO` | `schemas.py` | application service | the resource plus its `links` |
| Field rules | `Metadata` | `schemas.py` | application service | one `FieldMetadata` per field with a rule |
| HTTP response | `Response` | `schemas.py` | application service | `ApiResponse[{Name}DTO, {Name}Metadata]` |

How a `PUT` flows through them:

```text
client JSON ──► TodoUpdateRequest   router: FastAPI validates the body
                  ▼
              service.update_todo() ─► repository writes, reads back
                  ▼
              TodoModel              the database row
                  ▼  service adds links
              TodoDTO
                  ▼  service.build_response() adds metadata
              TodoResponse           {"_data": {"todo": ...}, "_metadata": ..., "_metaLinks": ...}
```

Rules:

- The layers do not inherit from each other, even when their fields match
  today. They diverge as soon as a column is hidden, a field is renamed, or a
  computed value is added. Keeping them separate makes that a one-place
  change.
- The repository converts rows to `Model` in one private helper
  (`_to_model`). The service converts `Model` to `DTO` in one method
  (`to_dto`), which is where links are added.
- Put reusable building blocks in `core/common/base_dto.py`, not in a domain:
  `Link`, `LinkedResource`, `EmbeddedRef`, `FieldMetadata`.

```python
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_serializer

from core.common.base_dto import FieldMetadata, LinkedResource


class TodoState(str, Enum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


# models.py
class TodoModel(BaseModel):
    """A `todos` database row."""
    id: str
    title: str
    description: Optional[str] = None
    complete_by: datetime
    state: TodoState
    created_date: datetime


# schemas.py — Request
class TodoCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    complete_by: datetime
    state: TodoState = TodoState.NEW


class TodoUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    complete_by: Optional[datetime] = None
    state: Optional[TodoState] = None


# schemas.py — DTO
class TodoDTO(LinkedResource):
    id: str
    title: str
    description: Optional[str] = None
    complete_by: datetime
    state: TodoState
    created_date: datetime

    @field_serializer("complete_by", "created_date")
    def serialize_datetime(self, value: datetime) -> str:
        return format_utc_datetime(value)


class TodoMetadata(BaseModel):
    title: FieldMetadata
    state: FieldMetadata
```

Do not force Request classes to contain fields generated by the server:

- `id`
- `created_date`
- `updated_date`
- resource `links`

## Relationship and metadata conventions

For simple metadata resources like tags:

- Tags belong to a resource through `resource_id`.
- `resource_id` should be a UUID string.
- Tag creation should be explicit through `POST /tags`.
- Tag deletion should be explicit through `DELETE /tags/{id}`.
- Resource deletion should delete related tags when that is the business rule.

Example table:

```sql
CREATE TABLE IF NOT EXISTS tags (
    id TEXT PRIMARY KEY,
    resource_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_date TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_resource_tag
ON tags(resource_id, tag);
```

Automatic metadata/tagging rules belong in the owning resource service.

Example:

- When a todo is created/updated/patched:
  - If `complete_by` is before today, add `overdue`.
  - If `complete_by` is in the future and state is `NEW`, add `not-started`.
  - Keep `overdue` and `not-started` mutually exclusive.
- When a todo is deleted:
  - Delete all tags where `resource_id` is the todo ID.

## Error handling conventions

Services raise domain exceptions, defined in the domain's `exceptions.py`, for
business-rule failures. The router catches them and maps them to HTTP errors.
Services never raise `HTTPException`:

```python
# users/exceptions.py
class SelfLockoutError(Exception):
    """An admin tried to remove their own ADMIN role or delete themselves."""


# users/user_router.py
try:
    updated = await service.update_user(user_id, request, caller)
except SelfLockoutError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
```

"Not found" is not an exception: services return `None` (or `False` for
delete) and the router returns `404`. A missing row that the migrations seed,
like the SYSTEM settings row, is a server error (`RuntimeError`, so `500`),
not a `404`.

Use proper HTTP status codes:

- `400 Bad Request` for invalid business input.
- `404 Not Found` when a requested resource does not exist.
- `409 Conflict` for duplicate or conflicting state.
- `422 Unprocessable Entity` for FastAPI/Pydantic validation errors.
- `500 Internal Server Error` for unexpected failures.

Do not return success-shaped responses for errors.

Avoid this:

```json
{
  "_data": null,
  "_messages": [
    {
      "type": "ERROR",
      "value": "Todo not found"
    }
  ]
}
```

Prefer this:

```json
{
  "detail": "Todo not found"
}
```

with HTTP status `404`.

## SQL conventions

Use parameterized SQL only.

Do this:

```python
await db.fetch_one(
    "SELECT * FROM todos WHERE id = ?",
    (todo_id,),
)
```

Do not do this:

```python
await db.fetch_one(f"SELECT * FROM todos WHERE id = '{todo_id}'")
```

Keep SQL simple and portable where possible:

- Prefer `TEXT` for UUID and ISO date strings.
- Prefer `?` parameters for SQLite/D1 compatibility.
- Avoid database-specific syntax unless the adapter owns it.
- Add indexes for lookup paths.
- Use unique indexes for business uniqueness rules.
- Use `INSERT OR IGNORE` for idempotent inserts (e.g. adding a role the user
  may already have). SQLite and D1 both support it.

### Database views

Use a view when:

- one model spans several tables, so reads stay one query per request, not
  one per row; or
- `core/` needs domain data without importing the domain package. The view is
  the contract between them.

```sql
-- migrations/003_user_detail_view.sql
CREATE VIEW IF NOT EXISTS user_detail_view AS
SELECT
    u.id, u.external_user_id, u.name, u.email, u.created_date,
    GROUP_CONCAT(r.role_id) AS role_ids
FROM users u
LEFT JOIN user_roles r ON r.user_id = u.id
GROUP BY u.id;
```

- Name views `{name}_view`, and add them through a migration like any table.
- D1 is SQLite underneath, so `CREATE VIEW` and `GROUP_CONCAT` work in every
  runtime.
- `GROUP_CONCAT` returns a comma-separated string, or `NULL` when there are no
  rows, in no guaranteed order. Split and sort it in one helper
  (`parse_role_ids`), never inline.
- Views are read-only: writes still go to the underlying tables.

## Local development checklist

A new app should support:

1. `uv sync`
2. `uv run uvicorn main:app --app-dir src --host 127.0.0.1 --port 8001 --reload`
3. `GET /health`
4. `GET /docs`
5. Automatic local SQLite migration
6. Docker Compose startup
7. A committed `.env.example`
8. No committed `.env`
9. No committed local database file
10. Response envelope on successful non-delete responses
11. `204 No Content` on delete
12. UUID IDs
13. UTC second-precision date formatting

## Cloudflare checklist

If Cloudflare is required, the app should support:

1. `wrangler.jsonc`
2. D1 binding named `DB`
3. `src/entry.py` wrapping `main.app`
4. `DATABASE_MODE=d1_binding`, or default to D1 binding when `env.DB` exists
5. `schema.sql` for D1 setup
6. `npx wrangler d1 execute todo-db --local --file=./schema.sql`
7. `uv run pywrangler dev`
8. `npx wrangler deploy`

Do not make Cloudflare mandatory for normal local development unless the user
explicitly asks for a Cloudflare-only app.

## README conventions

The project README should explain:

- What the app does.
- How to run locally with uvicorn + SQLite.
- How to run with Docker.
- How to run with Cloudflare D1 emulation, if supported.
- How to deploy to Cloudflare, if supported.
- Database modes.
- API endpoints.
- Important response envelope rules.

Keep reusable architectural conventions in this file or a central conventions
repo, not scattered across many project-specific docs.

## AI agent instructions

When an AI agent creates a new Python FastAPI app using these conventions, it
must:

1. Start with local uvicorn + SQLite unless the user asks otherwise.
2. Use `uv` and `pyproject.toml`.
3. Create `src/main.py`.
4. Create a database protocol before writing repositories.
5. Keep repositories backend-agnostic.
6. Put business rules in services.
7. Build links, metadata, meta links and the generic `ApiResponse` envelope
   (`ApiResponse[{Name}DTO, {Name}Metadata].of(...)`) in the service layer.
8. Use one typed class per layer — `{Name}Model`, `{Name}...Request`,
   `{Name}DTO`, `{Name}Metadata` — never `dict[str, Any]` between layers.
9. Return `204 No Content` for delete endpoints.
10. Use UUID strings for IDs.
11. Format dates as UTC `YYYY-MM-DDTHH:MM:SSZ`.
12. Include template endpoints for create forms when useful.
13. Add `.env.example`.
14. Add Docker support when requested or when useful for local reproducibility.
15. Add Cloudflare support only as an adapter/entrypoint, not as a dependency
    throughout the app.
16. Put authentication and authorization in `core/security/`; guard write
    endpoints with `require_admin` and build links from the `Caller`.
17. Keep `core/` free of domain imports; use a database view when `core/`
    needs domain data.
18. Raise domain exceptions from services and map them to HTTP errors in the
    router.
19. Validate the app with at least compile/import checks and a local smoke test.

If the user asks for a quick prototype, the agent may simplify, but it should
not violate the core boundaries:

```text
router -> service -> repository -> database adapter
```

## Default endpoint patterns

For a resource called `todos`, use:

```text
GET    /todos
GET    /todos/template
GET    /todos/{id}
POST   /todos
PUT    /todos/{id}
PATCH  /todos/{id}
DELETE /todos/{id}
```

For state transitions, use explicit routes only when they represent a real
business action:

```text
PATCH /todos/{id}/state/{state}
```

For metadata resources like tags:

```text
GET    /tags
GET    /tags/template
GET    /tags?resource_id={resource_id}
GET    /tags?term={search_term}
POST   /tags
DELETE /tags/{id}
```

Avoid route collisions such as:

```text
GET /tags/{resource_id}
GET /tags/{id}
```

Use query parameters when the lookup is not the primary resource ID.

## Naming conventions

Python files:

```text
snake_case.py
```

Classes:

```text
TodoService
TodoRepository
SQLiteDatabase
```

Data classes carry their layer as a suffix (see "Model, Request, DTO and
Response conventions"):

```text
TodoModel            # database row, models.py
TodoCreateRequest    # POST body, schemas.py
TodoUpdateRequest    # PUT body, schemas.py
TodoDTO              # service result, schemas.py
TodoMetadata         # field rules, schemas.py
TodoResponse         # = ApiResponse[TodoDTO, TodoMetadata], schemas.py
TodoListResponse     # = ApiResponse[list[TodoDTO], TodoMetadata], schemas.py
TodoTemplateResponse # = ApiResponse[TodoCreateRequest, TodoTemplateMetadata], schemas.py
```

Per-domain constants (the `_data` key name and link names) live in the
domain's `constants.py`:

```python
TODO_DATA_NAME = "todo"
LINK_SELF = "self"
LINK_UPDATE_TODO = "updateTodo"
```

Functions and variables:

```text
snake_case
get_database
created_date
resource_id
```

Enum values exposed through the API may use uppercase strings:

```python
class TodoState(str, Enum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
```

JSON fields should stay consistent with Python field names unless the API has a
reason to use another naming standard:

```json
{
  "complete_by": "2026-12-31T23:59:59Z",
  "created_date": "2026-09-21T13:47:02Z"
}
```

## Authentication and authorization conventions

Authentication (who is calling) and authorization (what they may do) live in
`core/security/`:

| Piece | File | What it does |
|---|---|---|
| `get_authenticated_user` | `auth.py` | Verifies the Clerk token and returns `AuthenticatedUser`. `401` if missing or invalid. |
| `Caller`, `get_caller` | `authorization.py` | The caller as our database sees them: `external_id`, `user_id` (None before their first `/me`), saved `role_ids`, `is_admin`. |
| `require_admin` | `authorization.py` | Returns the `Caller`, or `403` unless their saved roles include `ADMIN`. |
| `UserRole`, `role_options()` | `roles.py` | The role enum and the metadata option list with labels. |

`get_caller` reads `user_detail_view`, not the users repository, so
`core/security` never imports the users domain.

### Where roles come from

- **Clerk seeds roles.** `/me` creates the user with the roles in the token.
  On every later call it **adds** any token role the user lacks, and never
  removes one.
- **Our database is the source of truth after that.** Permission checks read
  saved roles, never the token. An admin granted through the API stays an
  admin even if Clerk stops sending the role, and revoking is done through
  the API.
- `STANDARD` is only the fallback for a user with no roles (the token parser
  supplies it when the token has none), so `/me` does not add it to a user
  who already has roles.

### Guarding routes

- Every route except `/health` requires a signed-in caller: `main.py` adds
  `Depends(get_authenticated_user)` to each router.
- Write endpoints that can change permissions or shared data require an
  admin: take `caller: Caller = Depends(require_admin)` as a parameter (so
  the service can use it), or add `dependencies=[Depends(require_admin)]` to
  the route or `include_router` when the caller isn't needed.
- Read endpoints take `caller: Caller = Depends(get_caller)` whenever links
  depend on permissions.
- Only offer links for what the caller may do (see "Link conventions").

### Personal resources

Some resources belong to one user and nobody else may use them, not even an
admin. The user's settings at `/users/{user_id}/settings` are one example:

- The service checks ownership first (`caller.user_id == user_id`) and raises
  a domain exception (`NotOwnerError`) that the router turns into `403`.
- Check ownership before existence: someone else's id gets `403` whether or
  not it exists, so the API doesn't reveal which ids exist. The caller's own
  user always exists, so no separate `404` is needed.
- Only offer links to personal resources on the owner's own view (e.g. the
  `userSettings` link appears only on your own profile).
- A resource can be public to read but owner-only to change: everyone may
  view any profile, only the owner may edit it (`can_edit_profile`).
- Shared defaults that admins manage live on a separate admin route
  (`/admin/settings`), not behind an "admin can edit anyone's" exception.

### Preventing lockout

An admin must not be able to leave the system without an admin. The service
refuses, with a domain exception that the router turns into `400`:

- removing your own `ADMIN` role;
- deleting yourself.

Compare by our id (`existing.id == caller.user_id`), not by name or email.

## Security and secret conventions

Never commit secrets.

Do not commit:

- `.env`
- Cloudflare API tokens
- Database credentials
- Render/Railway/Azure secrets
- Private keys

Commit safe examples only:

```text
.env.example
```

Use environment variables for secrets.

Cloudflare D1 HTTP mode requires:

```env
CF_ACCOUNT_ID=...
CF_D1_DATABASE_ID=...
CF_D1_API_TOKEN=...
```

The native Cloudflare D1 binding mode should not require a D1 API token inside
the app.

## Testing and validation conventions

At minimum, validate:

```powershell
uv sync
uv run python -m compileall src
uv run uvicorn main:app --app-dir src --host 127.0.0.1 --port 8001
```

Then smoke test:

```powershell
curl.exe http://127.0.0.1:8001/health
curl.exe http://127.0.0.1:8001/docs
curl.exe http://127.0.0.1:8001/todos/template
```

For CRUD resources, verify:

- Create returns UUID.
- List returns envelope.
- Get returns envelope.
- Update returns envelope.
- Delete returns `204` with empty body.
- Date fields use UTC `Z` format.
- Metadata contains only meaningful rules.
- Links are present or absent based on business rules.

For guarded resources, also verify with a non-admin and an admin caller:

- No token returns `401`; a non-admin on an admin route returns `403`.
- A non-admin gets no write links or write meta links.
- The lockout rules return `400`.
- Roles granted through the API survive a `/me` call whose token lacks them.

## Final design summary

The default application shape is:

```text
FastAPI router
  -> application service
    -> repository
      -> Database protocol
        -> SQLite for local/Docker
        -> D1 binding for Cloudflare Workers
        -> D1 HTTP for optional external hosting
```

The default response shape is:

```json
{
  "_data": {},
  "_metadata": {},
  "_metaLinks": {},
  "_messages": []
}
```

With messages:

```json
{
  "_data": {},
  "_metadata": {},
  "_metaLinks": {},
  "_messages": [
    {
      "type": "INFO",
      "value": "Useful message for the client."
    }
  ]
}
```

This convention exists so future Python APIs are easy to run locally, easy to
containerize, possible to deploy to Cloudflare, and consistent for clients.
