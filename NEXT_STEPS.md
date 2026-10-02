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

## Next

- [ ] Switch `fastapi-ai` to `wiltech-labs-rest>=1.0.0` (keeps `core/common/errors.py`,
      which depends on FastAPI).
- [ ] Add `maxLength` / `maxItems` / `min` / `max` / `default` to `ApiFieldMetadata` in
      `@wiltech-labs/ngx-api-client` so the Angular side can read them.
- [ ] Check `fastapi-template` under Docker and `uv run pywrangler dev` (Cloudflare bundling
      of the PyPI package) — only the uvicorn/TestClient path has been verified so far.
- [ ] Update `docs/PYTHON_APP_CONVENTIONS.md` (here and in `ai-conventions/python`) so
      `core/common/` points at `wiltech_labs_rest` instead of local files.

## Later candidates (from the template's `core/`)

- [ ] Config: `get_config(request, key)` + `.env` loader.
- [ ] Database: `Database` protocol, `SQLiteDatabase` + migration runner, `D1BindingDatabase`,
      `D1HttpDatabase`, `get_database` (SQLite behind an extra, lazy import).
- [ ] Security: Clerk JWT verification (`get_authenticated_user`), `Caller`, `require_admin`.
      `get_caller` reads `user_detail_view`, so the lookup needs to become pluggable.
- [ ] Link helpers to cut the `f"{API_PREFIX}/…"` + `Link(...)` repetition in services.
- [ ] App wiring: CORS, `/api` prefix, `/health` router.
- [ ] Region settings (`shared/settings/region`) as its own package — the Python side of
      `@wiltech-labs/ngx-region-settings`.

## Known drift in other apps (reconcile against the template later)

- `insurly-api` `auth.py` dropped the `asyncio.Lock` around the JWKS fetch (reported to hang
  Cloudflare Workers); also accepts JWKS keys with no `use`.
- `fastapi-ai` `database.py` uses `CF_D1_ACCOUNT_ID` instead of `CF_ACCOUNT_ID`.
- `fastapi-ai` adds `core/common/errors.py`, `core/config/cors.py` (per-request CORS origins), `require_owner`.
- `insurly-api` adds `utc_now`, `Money`, `BlankAsNone`, `UtcDateTime`, `MetadataBase`,
  `read_only()` / `mandatory()`.
