# wiltech-labs-core

Runtime plumbing: config, the portable `Database`, errors, CORS, health. See root
`../../CLAUDE.md` for repo-wide conventions and `../../docs/PYTHON_APP_CONVENTIONS.md`
("Runtime targets", "Database") for the contract.

Ported from `fastapi-template` (`../PythonTutorials/Tutorials/fastapi-template` relative to
this repo's parent), which is the source of truth:

| Here | Origin |
|---|---|
| `config/config.py` | template `src/core/config/config.py`. `_load_dotenv` is public as `load_dotenv(path=None)`; added `get_binding` |
| `database/database.py` | template `src/core/config/database.py`, verbatim apart from: `MIGRATIONS_DIR` is read when `migrations_dir()` runs (not at import), the new `batch()` method, and an injectable `transport` on `D1HttpDatabase` |
| `errors/errors.py` | `fastapi-ai` `src/core/common/errors.py` (the template has none); added `TooManyRequestsError` (429 + `Retry-After`) |
| `web/cors.py` | `fastapi-ai` `src/core/config/cors.py`; the template builds `CORSMiddleware` at import, which gets no origins in a Worker |
| `web/health.py` | template `src/metrics/status_router.py` as a factory, with optional checks |

`d1_http` reads `CF_ACCOUNT_ID` (template). `fastapi-ai` reads `CF_D1_ACCOUNT_ID` and must
rename it when it switches.

## Rules

- Keep it loadable in a Cloudflare Python Worker: `aiosqlite` only behind the `sqlite`
  extra and imported lazily; no native dependencies.
- `batch()` is the only multi-statement write. D1 has no interactive transactions, so don't
  add a `transaction()` context manager.
- D1 allows at most 100 bound parameters per statement. Helpers that build `IN (...)` lists
  must chunk.
