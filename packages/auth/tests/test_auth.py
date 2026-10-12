import base64
import hashlib
import hmac
import json
import time
from time import monotonic

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from wiltech_labs_auth import (
    API_KEYS_TABLE_SQL,
    ApiKeyRepository,
    AuthenticatedUser,
    Caller,
    SavedUser,
    ServiceCaller,
    WebhookVerificationError,
    clerk_webhook_event,
    get_api_key_repository,
    get_authenticated_user,
    get_caller,
    get_caller_lookup,
    parse_role_ids,
    require_admin,
    require_api_key,
    require_owner,
    verify_svix_signature,
)
from wiltech_labs_auth.clerk import clerk_auth
from wiltech_labs_core import SQLiteDatabase

JWKS_URL = "https://example.clerk.accounts.dev/.well-known/jwks.json"
ISSUER = "https://example.clerk.accounts.dev"
AUDIENCE = "test-api"


# --- Clerk JWT


@pytest.fixture
def signing_key(monkeypatch):
    """An RSA key whose public half is already in the JWKS cache, so no network call happens."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": "kid-1", "use": "sig", "alg": "RS256"})
    monkeypatch.setitem(clerk_auth._jwks_cache, JWKS_URL, (monotonic() + 3600, {"keys": [jwk]}))
    monkeypatch.setenv("CLERK_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("CLERK_AUDIENCE", AUDIENCE)
    monkeypatch.delenv("CLERK_AUTHORIZED_PARTIES", raising=False)
    return key


def make_token(key, **overrides) -> str:
    now = int(time.time())
    claims = {"sub": "user_clerk_1", "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300,
              "name": "Ada", "email": "ada@example.com", "roles": ["ADMIN", "ADMIN"]}
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "kid-1"})


def whoami_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(user: AuthenticatedUser = Depends(get_authenticated_user)):
        return {"id": user.id, "name": user.name, "email": user.email, "roles": user.role_ids}

    return app


def test_a_valid_clerk_token_becomes_an_authenticated_user(signing_key):
    response = TestClient(whoami_app()).get("/whoami", headers={"Authorization": f"Bearer {make_token(signing_key)}"})
    assert response.status_code == 200
    assert response.json() == {"id": "user_clerk_1", "name": "Ada", "email": "ada@example.com", "roles": ["ADMIN"]}


@pytest.mark.parametrize(
    "overrides",
    [{"aud": "someone-else"}, {"iss": "https://evil.example"}, {"exp": int(time.time()) - 10}],
)
def test_wrong_audience_issuer_or_expiry_is_401(signing_key, overrides):
    token = make_token(signing_key, **overrides)
    assert TestClient(whoami_app()).get("/whoami", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_no_token_is_401():
    assert TestClient(whoami_app()).get("/whoami").status_code == 401


def test_authorized_parties_are_enforced(signing_key, monkeypatch):
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "http://localhost:4200")
    client = TestClient(whoami_app())
    good = make_token(signing_key, azp="http://localhost:4200")
    bad = make_token(signing_key, azp="https://other.example")
    assert client.get("/whoami", headers={"Authorization": f"Bearer {good}"}).status_code == 200
    assert client.get("/whoami", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


# --- Caller, require_admin, require_owner


class FakeLookup:
    def __init__(self, users: dict[str, SavedUser]) -> None:
        self.users = users

    async def find(self, external_id: str):
        return self.users.get(external_id)


def authz_app(external_id: str, users: dict[str, SavedUser]) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(external_id, "x", None, [], {})
    app.dependency_overrides[get_caller_lookup] = lambda: FakeLookup(users)

    @app.get("/me")
    async def me(caller: Caller = Depends(get_caller)):
        return {"userId": caller.user_id, "admin": caller.is_admin}

    @app.get("/admin")
    async def admin(caller: Caller = Depends(require_admin)):
        return {"ok": True}

    @app.get("/users/{user_id}/todos")
    async def todos(user_id: str = Depends(require_owner)):
        return {"userId": user_id}

    return app


USERS = {"clerk_admin": SavedUser("u-admin", ["ADMIN", "STANDARD"]), "clerk_ada": SavedUser("u-ada", ["STANDARD"])}


def test_caller_reads_saved_roles_not_token_roles():
    assert TestClient(authz_app("clerk_ada", USERS)).get("/me").json() == {"userId": "u-ada", "admin": False}
    assert TestClient(authz_app("clerk_new", USERS)).get("/me").json() == {"userId": None, "admin": False}


def test_require_admin():
    assert TestClient(authz_app("clerk_admin", USERS)).get("/admin").status_code == 200
    assert TestClient(authz_app("clerk_ada", USERS)).get("/admin").status_code == 403


def test_require_owner_blocks_everyone_else_even_admins():
    assert TestClient(authz_app("clerk_ada", USERS)).get("/users/u-ada/todos").json() == {"userId": "u-ada"}
    assert TestClient(authz_app("clerk_admin", USERS)).get("/users/u-ada/todos").status_code == 403
    assert TestClient(authz_app("clerk_new", USERS)).get("/users/u-ada/todos").status_code == 403


def test_parse_role_ids_sorts_and_handles_null():
    assert parse_role_ids("STANDARD,ADMIN") == ["ADMIN", "STANDARD"]
    assert parse_role_ids(None) == []


# --- API keys


@pytest.fixture
def key_repository(tmp_path, monkeypatch):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_api_keys.sql").write_text(API_KEYS_TABLE_SQL)
    monkeypatch.setenv("MIGRATIONS_DIR", str(migrations))
    return ApiKeyRepository(SQLiteDatabase(str(tmp_path / "keys.db")))


async def test_only_the_hash_is_stored(key_repository):
    saved, plain = await key_repository.create("docs-worker", ["docs:parse"])
    assert plain.startswith("wtk_") and plain.startswith(saved.key_prefix)
    row = await key_repository.db.fetch_one("SELECT key_hash FROM api_keys WHERE id = ?", (saved.id,))
    assert row["key_hash"] == hashlib.sha256(plain.encode()).hexdigest()
    assert plain not in json.dumps(await key_repository.db.fetch_all("SELECT * FROM api_keys"))


async def test_require_api_key_checks_key_scope_and_revocation(key_repository):
    _, docs_key = await key_repository.create("docs-worker", ["docs:parse"])
    other, other_key = await key_repository.create("mailer", ["mail:send"])

    app = FastAPI()
    app.dependency_overrides[get_api_key_repository] = lambda: key_repository

    @app.post("/parse")
    async def parse(service: ServiceCaller = Depends(require_api_key("docs:parse"))):
        return {"service": service.name}

    client = TestClient(app)
    assert client.post("/parse", headers={"X-Api-Key": docs_key}).json() == {"service": "docs-worker"}
    assert client.post("/parse").status_code == 401
    assert client.post("/parse", headers={"X-Api-Key": "wtk_made-up"}).status_code == 401
    assert client.post("/parse", headers={"X-Api-Key": other_key}).status_code == 403

    await key_repository.revoke(other.id)
    assert client.post("/parse", headers={"X-Api-Key": other_key}).status_code == 401
    assert (await key_repository.find_active_by_key(docs_key)).last_used_date is not None


# --- Clerk / Svix webhooks

SECRET = "whsec_" + base64.b64encode(b"test-secret-bytes").decode()


def sign(body: bytes, msg_id="msg_1", timestamp=None) -> dict[str, str]:
    timestamp = str(timestamp if timestamp is not None else int(time.time()))
    digest = hmac.new(b"test-secret-bytes", f"{msg_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    return {"svix-id": msg_id, "svix-timestamp": timestamp, "svix-signature": "v1,bad v1," + base64.b64encode(digest).decode()}


def test_svix_signature_accepts_a_valid_delivery_and_rejects_tampering():
    body = b'{"type":"user.deleted","data":{"id":"user_1"}}'
    verify_svix_signature(SECRET, sign(body), body)

    with pytest.raises(WebhookVerificationError):
        verify_svix_signature(SECRET, sign(body), body.replace(b"user_1", b"user_2"))
    with pytest.raises(WebhookVerificationError, match="window"):
        verify_svix_signature(SECRET, sign(body, timestamp=int(time.time()) - 3600), body)


def test_clerk_webhook_dependency(monkeypatch):
    monkeypatch.setenv("CLERK_WEBHOOK_SECRET", SECRET)
    app = FastAPI()

    @app.post("/webhooks/clerk")
    async def clerk(event: dict = Depends(clerk_webhook_event)):
        return {"type": event["type"]}

    body = b'{"type":"user.deleted","data":{"id":"user_1"}}'
    client = TestClient(app)
    assert client.post("/webhooks/clerk", content=body, headers=sign(body)).json() == {"type": "user.deleted"}
    assert client.post("/webhooks/clerk", content=body, headers={"svix-id": "x"}).status_code == 400
