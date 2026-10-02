# wiltech-labs-rest

The response-building core for Wiltech FastAPI apps: the typed
`_data` / `_metadata` / `_metaLinks` / `_messages` envelope, HATEOAS-style
links, field metadata and UTC date formatting, as described in
[`docs/PYTHON_APP_CONVENTIONS.md`](https://github.com/wilferraciolli/py-libraries/blob/main/docs/PYTHON_APP_CONVENTIONS.md).

It's the server side of [`@wiltech-labs/ngx-api-client`](https://github.com/wilferraciolli/ngx-libraries/tree/main/packages/api-client),
which reads these envelopes in the Angular apps.

Depends only on `pydantic` (no FastAPI import), so it's usable from any layer.

## Install

Published on [PyPI](https://pypi.org/project/wiltech-labs-rest/). In the consuming app:

```bash
uv add wiltech-labs-rest            # adds "wiltech-labs-rest>=x.y.z" to pyproject.toml + uv.lock
```

Upgrade later with `uv lock --upgrade-package wiltech-labs-rest && uv sync`.
Docker builds and Cloudflare Workers (`pywrangler`) download it from PyPI like any other
dependency — it's pure Python, depending only on `pydantic`.

## Usage

```python
# todos/schemas.py
from datetime import datetime

from pydantic import BaseModel, field_serializer

from wiltech_labs_rest import ApiResponse, FieldMetadata, LinkedResource, format_utc_datetime


class TodoDTO(LinkedResource):
    id: str
    title: str
    state: TodoState
    created_date: datetime

    @field_serializer("created_date")
    def serialize_created_date(self, value: datetime) -> str:
        return format_utc_datetime(value)


class TodoMetadata(BaseModel):
    id: FieldMetadata
    title: FieldMetadata
    state: FieldMetadata


TodoResponse = ApiResponse[TodoDTO, TodoMetadata]
TodoListResponse = ApiResponse[list[TodoDTO], TodoMetadata]
```

```python
# todos/todo_service.py
from wiltech_labs_rest import API_PREFIX, FieldMetadata, Link, choice_field


class TodoService:
    @staticmethod
    def build_links(todo_id: str) -> dict[str, Link]:
        url = f"{API_PREFIX}/todos/{todo_id}"
        return {
            LINK_SELF: Link(href=url),
            LINK_UPDATE_TODO: Link(href=url, method="PUT"),
        }

    def build_metadata(self, todo: TodoDTO) -> TodoMetadata:
        return TodoMetadata(
            id=FieldMetadata(readOnly=True, hidden=True),
            title=FieldMetadata(mandatory=True),
            state=choice_field(TodoState),   # every enum member as {id, value}
        )

    def build_response(self, todo: TodoDTO) -> TodoResponse:
        return TodoResponse.of(TODO_DATA_NAME, todo, self.build_metadata(todo))
```

```json
{
  "_data": { "todo": { "id": "…", "title": "…", "links": { "self": { "href": "/api/todos/…", "method": "GET" } } } },
  "_metadata": { "id": { "readOnly": true, "hidden": true }, "state": { "mandatory": true, "values": [ … ] } },
  "_metaLinks": {},
  "_messages": []
}
```

## Public API

Everything is imported from `wiltech_labs_rest`:

| Name | What it is |
|---|---|
| `ApiResponse[DataT, MetadataT]` | The envelope. Build with `ApiResponse.of(data_name, data, metadata, meta_links=None, messages=None)`. |
| `API_PREFIX` | `"/api"` — the prefix every router is mounted under; use it when building hrefs. |
| `Link` | `{href, method="GET"}` |
| `LinkedResource` | DTO base class adding `links: dict[str, Link]` |
| `FieldMetadata` | `readOnly` / `hidden` / `mandatory` / `values`; unset flags are left out of the JSON |
| `EmbeddedRef` | `{id, value}` — an option in `values`, or an embedded reference |
| `choice_field(enum)` | Mandatory `FieldMetadata` whose `values` are every member of the enum |
| `Message`, `MessageType` | One `_messages` entry: `INFO` / `WARNING` / `ERROR` / `SUCCESS` |
| `format_utc_datetime(value)` | `datetime` or ISO string → `YYYY-MM-DDTHH:MM:SSZ` |

## Development, building and publishing

See [`docs/PUBLISHING.md`](https://github.com/wilferraciolli/py-libraries/blob/main/docs/PUBLISHING.md)
for local development, building, and the PyPI release steps.

Quick version, from the repo root:

```bash
uv sync
uv run --package wiltech-labs-rest pytest packages/rest
cd packages/rest
uv version --bump patch            # or minor / major
uv build                           # -> ../../dist/
uv publish ../../dist/wiltech_labs_rest-<version>*
```
