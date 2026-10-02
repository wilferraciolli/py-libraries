# py-libraries

Wiltech's shared Python libraries for FastAPI apps, published to PyPI.

| Package | Import | What it is |
|---|---|---|
| [`wiltech-labs-rest`](packages/rest) | `wiltech_labs_rest` | Response envelope, links, field metadata, UTC dates |

All apps follow [`docs/PYTHON_APP_CONVENTIONS.md`](docs/PYTHON_APP_CONVENTIONS.md).

## Development

A [uv](https://docs.astral.sh/uv/) workspace, so one `uv sync` at the root installs every package:

```bash
uv sync
uv run --package wiltech-labs-rest pytest packages/rest
```

Building, releasing to PyPI and using a package in an app: [`docs/PUBLISHING.md`](docs/PUBLISHING.md).
