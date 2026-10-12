# Next steps

Roadmap for pulling the shared code out of the FastAPI apps. `fastapi-template`
is the master; other apps are brought in line with it later.

## Done

- [x] `wiltech-labs-rest` 0.1.0 — `ApiResponse`, `API_PREFIX`, `Link`, `LinkedResource`,
      `FieldMetadata`, `EmbeddedRef`, `choice_field`, `Message`, `MessageType`,
      `format_utc_datetime`. Tests pin the JSON shape.
- [x] Published 0.1.0 to TestPyPI and PyPI (2026-10-02).
- [x] `fastapi-template` uses it from PyPI: `core/common/` deleted, imports switched, both
      `_choice_field` copies replaced with `choice_field`. Smoke-tested every envelope endpoint.
- [x] `wiltech-labs-rest` 0.2.0 (never published) — `FieldMetadata.maxLength/maxItems/
      min/max/default`, `NoMetadata`, `as_utc`, `UtcDateTime`, for `fastapi-ai`.
- [x] Published **1.0.0** to PyPI (2026-10-02) — 0.2.0's contents, first stable release.
      `fastapi-template` now requires `wiltech-labs-rest>=1.0.0`; smoke test re-run.
- [x] `wiltech-labs-rest` 1.0.1 (built, **not yet published**) — `insurly-api`'s
      `core/common/` extras: `MetadataBase`, `read_only`, `mandatory`, `UtcTimestamp`
      (its serializing `UtcDateTime`), `Money`, `money`, `BlankAsNone`, `EmptyIfNone`,
      `utc_now`, `to_db_datetime`, `to_db_date`; plus `resource-management-api`'s
      `CamelModel`, as `CamelModel` / `CamelLinkedResource` / `CamelMetadataBase`.
- [x] `insurly-api` switched: `core/common/` deleted, everything imported from
      `wiltech_labs_rest`. Responses verified identical on 19 endpoints; Worker
      dry-run bundles the package. Needs 1.0.1 on PyPI, then `uv lock`.
- [x] `resource-management-api` switched: `core/common/` deleted, everything imported
      from `wiltech_labs_rest`. Needs 1.0.1 on PyPI, then `uv lock`.
- [x] `wiltech-labs-core`, `wiltech-labs-auth`, `wiltech-labs-ai` 0.1.0 built (in
      PythonTutorials' `libraries/` staging area, moved here). **Not yet published.**
      `fastapi-template` already imports core + auth (verified against the local packages).

## Next

- [ ] Publish in dependency order: **core → auth → ai** (tags `core-v0.1.0`,
      `auth-v0.1.0`, `ai-v0.1.0`). Then run `uv lock` in `fastapi-template`: its
      `uv.lock` is stale until core and auth are on PyPI, and the Dockerfile's
      `uv sync --frozen` would install the old dependency set without complaint.
- [ ] Switch `fastapi-ai` to core/auth/ai: delete `src/core/config/*`, `core/common/errors.py`,
      `metrics/status_router.py`, `core/security/*`, `core/ai/*`, `assistant/tools/tool.py`
      and the loop in `assistant_service.py`; import from the packages instead. Check the
      differences listed under *Known drift* first.
- [ ] Verify in a real Python Worker (`pywrangler dev`): the D1 binding `batch()` (uses
      `pyodide.ffi.to_js`) and bundling of the three packages.
- [ ] Verify `VectorizeVectorStore` and `QdrantVectorStore` against live services (tests
      only check the documented REST request shapes with `httpx.MockTransport`).
- [ ] Switch `fastapi-ai` to `wiltech-labs-rest>=1.0.0` (keeps `core/common/errors.py`,
      which depends on FastAPI).
- [ ] Add `maxLength` / `maxItems` / `min` / `max` / `default` to `ApiFieldMetadata` in
      `@wiltech-labs/ngx-api-client` so the Angular side can read them.
- [ ] Check `fastapi-template` under Docker and `uv run pywrangler dev` (Cloudflare bundling
      of the PyPI package) — only the uvicorn/TestClient path has been verified so far.
- [ ] Update `docs/PYTHON_APP_CONVENTIONS.md` (here and in `ai-conventions/python`) so
      `core/common/` points at `wiltech_labs_rest` instead of local files.

## Later candidates (from the template's `core/`)

- [x] Config: `get_config(request, key)` + `.env` loader (wiltech-labs-core).
- [x] Database: `Database` protocol, `SQLiteDatabase` + migration runner, `D1BindingDatabase`,
      `D1HttpDatabase`, `get_database` (SQLite behind an extra, lazy import) (wiltech-labs-core).
- [x] Security: Clerk JWT verification (`get_authenticated_user`), `Caller`, `require_admin`,
      with a pluggable caller lookup (wiltech-labs-auth).
- [ ] Link helpers to cut the `f"{API_PREFIX}/…"` + `Link(...)` repetition in services.
- [x] App wiring: CORS, `/api` prefix, `/health` router (wiltech-labs-core).
- [ ] Region settings (`shared/settings/region`) as its own package — the Python side of
      `@wiltech-labs/ngx-region-settings`.

## Known drift in other apps (reconcile against the template later)

- `insurly-api` `auth.py` dropped the `asyncio.Lock` around the JWKS fetch (reported to hang
  Cloudflare Workers); also accepts JWKS keys with no `use`.
- `fastapi-ai` `database.py` uses `CF_D1_ACCOUNT_ID` instead of `CF_ACCOUNT_ID`.
- `fastapi-ai` adds `core/common/errors.py`, `core/config/cors.py` (per-request CORS origins), `require_owner`.
- When `fastapi-ai` switches to core/auth/ai:
  - `DATABASE_MODE=d1_http` reads `CF_ACCOUNT_ID` (the template's name), not `CF_D1_ACCOUNT_ID`.
  - `CLERK_AUDIENCE` defaults to `wiltech-dev-api` when unset (template behaviour).
  - LLM failures raise `UpstreamError` (502) instead of `RuntimeError` (500);
    `tests/test_llm.py` expects `RuntimeError`.
  - `roles.to_role()` (case-insensitive Clerk roles) isn't in auth; keep it in the app or add it.
  - The chat search's `message_embeddings` store isn't ported; `resource_embeddings`
    (todos, posts) works as is through `DatabaseVectorStore`.
