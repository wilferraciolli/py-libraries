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

- [x] **`wiltech-labs-holidays` 1.0.0** published (2026-10-23): a locale (`el-CY`) in,
      `PublicHoliday` items (`date`, `name`, `category`, `country`) out, on the `holidays`
      package; `holidays_router()` behind the `router` extra. Counterpart:
      `@wiltech-labs/ngx-calendar` 1.0.3's `holidays` input. Crewly depends on it (its copy is
      gone). Still unverified in a Python Worker (pure Python, should bundle).

- [ ] Review and publish **`wiltech-labs-core` 1.1.0** (drafted for Crewly, not yet committed):
      `Database.execute_returning` on every adapter; `UniqueConstraintError` mapped by every
      adapter (also from `batch`); D1 binding sends `None` as JS `null` (Pyodide's default
      `undefined` is rejected by D1) and converts result rows to dicts; each SQLite migration
      runs in one transaction with its bookkeeping row; SQLite turns on `PRAGMA foreign_keys`
      (D1 enforces foreign keys already, so local runs now match: check other apps' local data).
      Then `crewly-api` deletes its `core/config/database.py` shim and imports from here.
- [ ] Review and publish **`wiltech-labs-core` 1.1.1** (new, 2026-10-24, not committed): portable
      file storage, `FileStore` with `LocalFileStore` (a folder) and `R2BindingFileStore` (a
      Worker's R2 bucket binding), chosen by `get_file_store(request)` (`FILE_STORE_MODE`,
      `FILE_STORE_BINDING`, `FILES_DIR`); keys checked so a user's file name never becomes a path.
      Needed by Crewly's documents (02·2d), which keeps a `TEMPORARY` copy in
      `crewly-api/src/core/files/` until this is on PyPI. The R2 adapter is unverified in a real
      Worker (written against the R2 binding API, tested with a fake bucket).
- [ ] Review and publish **`wiltech-labs-auth` 1.0.2** (new, 2026-10-28, not committed): Clerk
      invitations, `get_inviter(request)` giving a `ClerkInviter` (`POST /v1/invitations` with
      `notify` and `ignore_existing`, `CLERK_SECRET_KEY`) or, without a key, a `ManualInviter` that
      sends nothing; `InvitationError` carries Clerk's message. Needed by Crewly's pre-boarding
      (03·3b), which keeps a `TEMPORARY` copy in `crewly-api/src/core/invitations/` until this is on
      PyPI. Tested with `httpx.MockTransport`, not yet against Clerk itself.
- [ ] `wiltech-labs-auth`: the module-level `asyncio.Lock` around the JWKS fetch is still there
      (`insurly-api` dropped it because it hung Cloudflare Workers, see Known drift). Decide
      before Crewly runs on Workers.

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
