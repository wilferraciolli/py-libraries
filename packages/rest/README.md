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
| `FieldMetadata` | `readOnly` / `hidden` / `mandatory` / `values`, plus limits `maxLength` (text), `maxItems` (lists), `min` / `max` / `default` (numbers); unset flags are left out of the JSON |
| `NoMetadata` | `_metadata` for a response with no field rules; serializes as `{}` |
| `MetadataBase` | Base for `{Resource}Metadata` classes with dotted keys (`driver.licenseStatus`): declare them with `Field(alias=...)`, serialized by alias |
| `CamelModel` | Base for a Request/DTO/Metadata with snake_case attributes and camelCase JSON (`bed_number` ↔ `bedNumber`); requests accept either spelling |
| `CamelLinkedResource`, `CamelMetadataBase` | `LinkedResource` / `MetadataBase` serialized camelCase |
| `read_only(hidden=False)`, `mandatory(values=None)` | `FieldMetadata` shortcuts |
| `EmbeddedRef` | `{id, value}` — an option in `values`, or an embedded reference |
| `choice_field(enum)` | Mandatory `FieldMetadata` whose `values` are every member of the enum |
| `Message`, `MessageType` | One `_messages` entry: `INFO` / `WARNING` / `ERROR` / `SUCCESS` |
| `format_utc_datetime(value)` | `datetime` or ISO string → `YYYY-MM-DDTHH:MM:SSZ` |
| `UtcDateTime`, `as_utc(value)` | Field type for database row models: parses stored dates and makes them timezone-aware UTC (naive = UTC), so they compare safely |
| `UtcTimestamp` | Field type for DTOs: a `datetime` serialized as `YYYY-MM-DDTHH:MM:SSZ`, with no `@field_serializer` needed |
| `utc_now()` | Current UTC time at second precision |
| `to_db_datetime(value)`, `to_db_date(value)` | Store a `datetime` as the API's UTC string, a `date` as `YYYY-MM-DD` (`None` stays `None`) |
| `Money`, `money(value)` | `Decimal` field sent as a JSON number; `money()` rounds to 2 places, half up |
| `BlankAsNone` | Validator for optional request fields: `Annotated[Optional[str], BlankAsNone]` turns `""` into `None` |
| `EmptyIfNone` | Optional string field sent as `""` instead of `null`, for values bound straight into form controls |

## Development

From the repo root:

```bash
uv sync
uv run --package wiltech-labs-rest pytest packages/rest
```

## Publishing

Released to [TestPyPI](https://test.pypi.org/project/wiltech-labs-rest/) (rehearsal) and
[PyPI](https://pypi.org/project/wiltech-labs-rest/) (what apps install from). They're separate
sites with separate accounts and API tokens. Account setup, checking a TestPyPI release and
fixing errors are covered in
[`docs/PUBLISHING.md`](https://github.com/wilferraciolli/py-libraries/blob/main/docs/PUBLISHING.md).

```bash
cd packages/rest

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
git commit -am "wiltech-labs-rest <version>"
git tag rest-v<version> && git push && git push --tags
```

A version number can only be uploaded once to each site. To retry after a fix, bump the
version and rebuild.
