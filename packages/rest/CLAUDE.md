# wiltech-labs-rest

The response-building core: the `ApiResponse` envelope, links, field
metadata, messages and UTC date formatting. See root `../../CLAUDE.md` for
repo-wide conventions and `../../docs/PYTHON_APP_CONVENTIONS.md` ("Response
envelope", "Metadata", "Link", "Message" and "Date and time" sections) for
the contract.

Ported from `fastapi-template` (`../PythonTutorials/Tutorials/fastapi-template`
relative to this repo's parent):

| Here | Template origin |
|---|---|
| `response/api_response.py` | `src/core/common/api_response.py` |
| `response/message.py` | `Message`, `MessageType` in `src/core/common/base_dto.py` |
| `links/link.py` | `Link`, `LinkedResource` in `src/core/common/base_dto.py` |
| `metadata/field_metadata.py` | `EmbeddedRef`, `FieldMetadata` in `src/core/common/base_dto.py`; `choice_field` was the `_choice_field` static method copied into `user_settings_service.py` and `system_settings_service.py` |
| `serializers/dates.py` | `src/core/common/serializers.py`, widened to accept ISO strings per the conventions doc |

0.2.0 added what `fastapi-ai` had on top of the template: `FieldMetadata`'s
`maxLength` / `maxItems` / `min` / `max` / `default`, `NoMetadata`, and
`as_utc` / `UtcDateTime` (from its `src/core/common/base_dto.py` and
`serializers.py`).

The wire shape must stay what `@wiltech-labs/ngx-api-client`
(`../ngx-libraries/packages/api-client`) reads. Changing a field name or
alias here is a breaking change for every Angular app.

## Layout

```
src/wiltech_labs_rest/
├── __init__.py          # the entire public surface (__all__)
├── response/            # ApiResponse, API_PREFIX, Message, MessageType
├── links/               # Link, LinkedResource
├── metadata/            # FieldMetadata, NoMetadata, EmbeddedRef, choice_field
└── serializers/         # format_utc_datetime, as_utc, UtcDateTime
```

## Rules

- Pydantic only — never import FastAPI here.
- `FieldMetadata`'s `model_serializer` has no return annotation on purpose:
  Pydantic uses it for the OpenAPI schema (see the conventions doc).
- Don't add `response_model_exclude_none` tricks; `FieldMetadata` drops its
  own unset flags, while a DTO's `None` fields stay as `null`.
- Tests in `tests/` pin the exact JSON shape — update them deliberately.
