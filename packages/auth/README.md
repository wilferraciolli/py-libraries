# wiltech-labs-auth

Who is calling a Wiltech FastAPI app, and may they? Clerk JWT verification, the `Caller`
with the roles **saved in the app's database**, `require_admin` / `require_owner`,
**service API keys** for app-to-app calls, and **Clerk webhook** (Svix) verification.

Builds on [`wiltech-labs-core`](../core) (config, `Database`) and
[`wiltech-labs-rest`](../rest) (`EmbeddedRef` for role options). Pure Python
(`pyjwt[crypto]`, `httpx`), so it runs in Cloudflare Workers.

## Install

```bash
uv add wiltech-labs-auth
```

## Usage

### Signed-in users (Clerk)

```python
# main.py
from fastapi import Depends
from wiltech_labs_auth import get_authenticated_user, require_admin

app.include_router(todo_router.router, prefix="/api", dependencies=[Depends(get_authenticated_user)])
app.include_router(system_settings_router.router, prefix="/api", dependencies=[Depends(require_admin)])
```

```python
# todos/todo_router.py — personal resources: only the user in the path, not even an admin
from wiltech_labs_auth import Caller, get_caller, require_owner

router = APIRouter(prefix="/users/{user_id}/todos")


@router.get("")
async def list_todos(user_id: str = Depends(require_owner), service: TodoService = Depends(get_todo_service)):
    ...
```

`get_caller` finds the saved user through `get_caller_lookup`, which by default reads
`user_detail_view (id, external_user_id, role_ids)`, the view every app built from
`fastapi-template` has. An app with a different schema overrides it:

```python
from wiltech_labs_auth import SavedUser, get_caller_lookup


class MembersLookup:
    def __init__(self, db): self.db = db

    async def find(self, external_id: str) -> SavedUser | None:
        row = await self.db.fetch_one("SELECT id, roles FROM members WHERE clerk_id = ?", (external_id,))
        return SavedUser(row["id"], row["roles"].split(",")) if row else None


app.dependency_overrides[get_caller_lookup] = lambda request: MembersLookup(get_database(request))
```

### Service API keys (app → app)

For a Worker calling a shared service at home (a PDF parser, a transcriber) where there is
no signed-in person.

1. Add the table: copy `API_KEYS_TABLE_SQL` into a migration (and `schema.sql` for D1).
2. Issue a key from an admin route or a one-off script. The plain key is returned **once**;
   only its SHA-256 is stored.

   ```python
   saved, plain_key = await ApiKeyRepository(db).create("docs-worker", ["docs:parse"])
   ```

3. Protect routes:

   ```python
   from wiltech_labs_auth import ServiceCaller, require_api_key

   @router.post("/documents/parse")
   async def parse(service: ServiceCaller = Depends(require_api_key("docs:parse"))): ...
   ```

4. The caller sends `X-Api-Key: wtk_...`. A missing or revoked key gets 401, a missing
   scope gets 403. `last_used_date` updates at most once an hour per key, to save D1 writes.

Rotate a key by creating a new one, deploying it, then calling `revoke(old_id)`.

### Clerk webhooks

Keep the local `users` table in step with Clerk (for example, delete a user's data on
`user.deleted`). In Clerk: *Webhooks → Add endpoint* → `https://api.example.com/api/webhooks/clerk`,
then put its signing secret in `CLERK_WEBHOOK_SECRET`.

```python
from wiltech_labs_auth import clerk_webhook_event

@router.post("/webhooks/clerk")      # NOT behind get_authenticated_user
async def clerk(event: dict = Depends(clerk_webhook_event)):
    if event["type"] == "user.deleted":
        await users.delete_by_external_id(event["data"]["id"])
    return {"received": True}
```

`verify_svix_signature(secret, headers, raw_body)` is also exported for non-FastAPI use.

## Configuration

| Variable | Used by | Notes |
|---|---|---|
| `CLERK_JWKS_URL` | `get_authenticated_user` | The issuer is this URL minus `/.well-known/jwks.json` |
| `CLERK_AUDIENCE` | `get_authenticated_user` | Default `wiltech-dev-api` (as in the template) |
| `CLERK_AUTHORIZED_PARTIES` | `get_authenticated_user` | Optional, comma-separated allowed `azp` |
| `CLERK_WEBHOOK_SECRET` | `clerk_webhook_event` | `whsec_...` |

## Public API

| Name | What it is |
|---|---|
| `get_authenticated_user`, `AuthenticatedUser` | Verify the Clerk bearer token (JWKS cached for 1 h, refreshed on an unknown `kid`) |
| `get_caller`, `Caller` | The caller with **saved** roles (`user_id` is `None` before their first `/me`) |
| `get_caller_lookup`, `CallerLookup`, `SavedUser`, `UserDetailViewLookup` | Where `get_caller` looks users up; override per app |
| `require_admin` | 403 unless the saved roles include `ADMIN` |
| `require_owner` | For `/users/{user_id}/...`: 403 unless the caller *is* `user_id` |
| `UserRole`, `ROLE_LABELS`, `role_options()`, `parse_role_ids()` | Roles and their metadata option list |
| `require_api_key(*scopes)`, `ServiceCaller` | Service-to-service dependency (`X-Api-Key`) |
| `ApiKeyRepository`, `ApiKeyModel`, `API_KEYS_TABLE_SQL`, `get_api_key_repository` | Key storage |
| `generate_api_key()`, `hash_api_key()`, `API_KEY_HEADER` | Key helpers |
| `clerk_webhook_event`, `verify_svix_signature`, `WebhookVerificationError` | Webhook verification |

## Development

```bash
uv run --package wiltech-labs-auth pytest packages/auth
```

## Publishing

Publish `wiltech-labs-core` first; this package depends on it.

```bash
cd packages/auth

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
git commit -am "wiltech-labs-auth <version>"
git tag auth-v<version> && git push && git push --tags
```

A version number can only be uploaded once to each site. To retry after a fix, bump the
version and rebuild.
