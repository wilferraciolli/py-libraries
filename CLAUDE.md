# py-libraries

Wiltech's shared Python libraries — small packages for the FastAPI apps, so
each new API installs the common pieces instead of copy-pasting `core/` from
the last project. The Python counterpart of `../ngx-libraries` (Angular,
`@wiltech-labs/ngx-*` on npm).

## Repo layout

```
py-libraries/
├── packages/
│   └── rest/               # wiltech-labs-rest (import: wiltech_labs_rest) — see its own CLAUDE.md
├── docs/
│   ├── PYTHON_APP_CONVENTIONS.md   # conventions every consuming FastAPI app follows — the
│   │                               # contract these packages meet
│   └── PUBLISHING.md       # build, release to PyPI, and consume in an app
├── NEXT_STEPS.md           # roadmap: what is still to be extracted, and in what order
├── pyproject.toml          # uv workspace root (members: packages/*); not a package itself
└── LICENSE                 # Apache-2.0, applies to every package
```

## Locked-in decisions (don't relitigate without asking)

| Area | Decision |
|---|---|
| Source of truth | `../PythonTutorials/Tutorials/fastapi-template` is the master app. Code is ported from there as-is; if another app (fastapi-ai, insurly-api, resource-management-api) differs, the template wins and the user reconciles the other app later. Don't pull another app's variant in without asking. |
| Conventions | Every package meets `docs/PYTHON_APP_CONVENTIONS.md`. Change the doc and the package together when a rule needs to move. |
| Naming | Distribution `wiltech-labs-<name>` (PyPI has no scopes; mirrors npm `@wiltech-labs`), import package `wiltech_labs_<name>`, folder `packages/<name>/`. |
| Tooling | `uv` workspace, `hatchling` build backend, `src/` layout, `pytest`. Python `>=3.13` (same as the apps). |
| Dependencies | As few as possible. `wiltech-labs-rest` depends only on `pydantic` — no FastAPI import — so it's usable in every layer. Optional backends (e.g. `aiosqlite`) go behind extras and lazy imports, so Cloudflare Workers can still load the package. |
| Public surface | Exactly what the package's top-level `__init__.py` re-exports (its `__all__`). Consumers import from `wiltech_labs_<name>`, never from sub-modules. |
| Publishing | Public PyPI (TestPyPI for rehearsals), released by hand with `uv build` + `uv publish` — see `docs/PUBLISHING.md`. Apps depend on the published version only, never a `path`/`git` source, so they build on any computer. Tag each release `<folder>-v<version>`. |
| License | Apache-2.0. |

## Working in this repo

- One package = one PyPI-publishable unit. Organize each package's
  `src/wiltech_labs_<name>/` into folders by concern (`response/`, `links/`,
  `metadata/`, `serializers/`) rather than a flat file list.
- Code style follows the apps: `typing` hints as the template writes them,
  docstrings explaining *why*, `@staticmethod` for helpers without state.
- **New package checklist**: `packages/<name>/` containing
  - `pyproject.toml` — name `wiltech-labs-<name>`, `license = "Apache-2.0"`, hatchling, `requires-python = ">=3.13"`
  - `src/wiltech_labs_<name>/__init__.py` with `__all__`, plus `py.typed`
  - `tests/`
  - `README.md` — usage examples, public API table, **Publishing** section (copy `packages/rest/README.md`)
  - `CLAUDE.md` — where the code was ported from and package-specific rules
  - an entry in this file's repo layout
- Run tests: `uv sync && uv run --package wiltech-labs-<name> pytest packages/<name>`.
