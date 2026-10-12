import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from wiltech_labs_core import Database, get_database

API_KEY_HEADER = "X-Api-Key"
KEY_PREFIX = "wtk_"

# How stale last_used_date may get before a request updates it. Writing on
# every call would spend D1's free write allowance on bookkeeping.
LAST_USED_RESOLUTION = timedelta(hours=1)

# Migration for apps that accept service API keys (copy into migrations/ and schema.sql).
API_KEYS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    scopes TEXT NOT NULL,
    created_date TEXT NOT NULL,
    last_used_date TEXT,
    revoked_date TEXT
);
""".strip()

_api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


def generate_api_key() -> str:
    """A new random key, e.g. `wtk_3q2...`. Shown to the person once; only its hash is stored."""
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    """
    SHA-256 hex digest. A plain hash, not bcrypt: the key is 256 random bits,
    so there is nothing to brute-force, and lookups must be one indexed query.
    """
    return hashlib.sha256(key.encode()).hexdigest()


@dataclass(frozen=True)
class ApiKeyModel:
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    created_date: str
    last_used_date: Optional[str] = None
    revoked_date: Optional[str] = None


@dataclass(frozen=True)
class ServiceCaller:
    """An app (not a person) calling with an API key."""

    key_id: str
    name: str
    scopes: list[str]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_model(row: dict) -> ApiKeyModel:
    return ApiKeyModel(
        id=row["id"],
        name=row["name"],
        key_prefix=row["key_prefix"],
        scopes=[scope for scope in (row["scopes"] or "").split(",") if scope],
        created_date=row["created_date"],
        last_used_date=row.get("last_used_date"),
        revoked_date=row.get("revoked_date"),
    )


class ApiKeyRepository:
    """SQL for the `api_keys` table (API_KEYS_TABLE_SQL)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, name: str, scopes: list[str]) -> tuple[ApiKeyModel, str]:
        """Returns the saved key and the plain key. The plain key can't be recovered later."""
        plain = generate_api_key()
        key_id = str(uuid.uuid4())
        created = _now().isoformat()
        await self.db.execute(
            "INSERT INTO api_keys (id, name, key_hash, key_prefix, scopes, created_date) VALUES (?, ?, ?, ?, ?, ?)",
            (key_id, name, hash_api_key(plain), plain[: len(KEY_PREFIX) + 6], ",".join(sorted(set(scopes))), created),
        )
        model = await self.find(key_id)
        assert model is not None
        return model, plain

    async def find(self, key_id: str) -> Optional[ApiKeyModel]:
        row = await self.db.fetch_one("SELECT * FROM api_keys WHERE id = ?", (key_id,))
        return _to_model(row) if row else None

    async def find_active_by_key(self, plain: str) -> Optional[ApiKeyModel]:
        row = await self.db.fetch_one(
            "SELECT * FROM api_keys WHERE key_hash = ? AND revoked_date IS NULL",
            (hash_api_key(plain),),
        )
        return _to_model(row) if row else None

    async def list_all(self) -> list[ApiKeyModel]:
        rows = await self.db.fetch_all("SELECT * FROM api_keys ORDER BY created_date DESC")
        return [_to_model(row) for row in rows]

    async def revoke(self, key_id: str) -> None:
        await self.db.execute(
            "UPDATE api_keys SET revoked_date = ? WHERE id = ? AND revoked_date IS NULL",
            (_now().isoformat(), key_id),
        )

    async def mark_used(self, key: ApiKeyModel) -> None:
        if key.last_used_date and _now() - datetime.fromisoformat(key.last_used_date) < LAST_USED_RESOLUTION:
            return
        await self.db.execute("UPDATE api_keys SET last_used_date = ? WHERE id = ?", (_now().isoformat(), key.id))


def get_api_key_repository(request: Request) -> ApiKeyRepository:
    """Overridable like get_caller_lookup, e.g. to keep keys in another database."""
    return ApiKeyRepository(get_database(request))


def require_api_key(*scopes: str) -> Callable:
    """
    Route dependency factory for service-to-service calls:

        @router.post("/parse", dependencies=[Depends(require_api_key("docs:parse"))])

    401 without a valid, unrevoked key in X-Api-Key; 403 if the key lacks one
    of `scopes`. Returns the ServiceCaller.
    """
    required = set(scopes)

    async def dependency(
        key: Optional[str] = Depends(_api_key_header),
        repository: ApiKeyRepository = Depends(get_api_key_repository),
    ) -> ServiceCaller:
        if not key or not key.startswith(KEY_PREFIX):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required")

        saved = await repository.find_active_by_key(key)
        if saved is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

        missing = required - set(saved.scopes)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key lacks scope: {', '.join(sorted(missing))}",
            )

        await repository.mark_used(saved)
        return ServiceCaller(key_id=saved.id, name=saved.name, scopes=saved.scopes)

    return dependency
