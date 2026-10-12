# wiltech-labs-auth

Authentication and authorization. See root `../../CLAUDE.md` for repo-wide conventions and
`../../docs/PYTHON_APP_CONVENTIONS.md` ("Security") for the contract.

Ported from `fastapi-template`, which is the source of truth:

| Here | Origin |
|---|---|
| `clerk/clerk_auth.py` | template `src/core/security/auth.py`, verbatim apart from `print` → `logging`. Keeps the `asyncio.Lock` around the JWKS fetch and the `CLERK_AUDIENCE` default `wiltech-dev-api` (template behaviour) |
| `roles/roles.py` | template `src/core/security/roles.py`. `fastapi-ai`'s extra `to_role()` is not included |
| `authorization/authorization.py` | template `src/core/security/authorization.py`; the `user_detail_view` query moved behind `get_caller_lookup` / `CallerLookup` so apps can override it. `require_owner` is from `fastapi-ai` (the template has no equivalent) |
| `api_keys/` | New: service-to-service keys |
| `webhooks/` | New: Svix signature verification for Clerk webhooks |

## Rules

- `get_caller` reads **saved** roles, never token roles. Don't "simplify" it to trust Clerk
  claims.
- `require_owner` is deliberately stricter than `require_admin`: admins can't read another
  user's personal resources.
- API keys: store only the SHA-256 and return the plain key once. `mark_used` writes at most
  hourly (D1 write budget).
- Webhook verification needs the raw body bytes. Never re-serialise JSON before verifying.
