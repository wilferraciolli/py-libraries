import os
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from starlette.requests import HTTPConnection

from wiltech_labs_core.config import get_config

# One SQL statement and its parameters, as `batch` takes them.
Statement = tuple[str, tuple[Any, ...]]


def migrations_dir() -> Path:
    """
    Where the SQL migrations live: MIGRATIONS_DIR (Docker: /app/migrations),
    otherwise ./migrations relative to the working directory, i.e. the project
    root that uvicorn and pytest run from. Never derived from __file__, which
    would point inside this installed package.

    Raises a RuntimeError if the folder doesn't exist: a missing folder must
    never silently mean "no migrations to run". Checked when SQLite applies
    migrations, not at import: a Cloudflare Worker ships only src/ and uses D1
    (migrated with wrangler), so it has no migrations folder and must still start.
    """
    configured = os.environ.get("MIGRATIONS_DIR")
    path = Path(configured) if configured else Path.cwd() / "migrations"
    if not path.is_dir():
        raise RuntimeError(
            f"Migrations directory not found at {path}. "
            "Set MIGRATIONS_DIR or run from the project root."
        )
    return path


class Database(Protocol):
    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]: ...

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]: ...

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None: ...

    async def batch(self, statements: Sequence[Statement]) -> None:
        """
        Run several writes together. D1 has no interactive transactions, so
        this (D1's `batch()`) is the portable way to change two tables at once,
        e.g. a row plus its audit event.
        """
        ...


_migrated_paths: set[str] = set()


class SQLiteDatabase:
    """SQLite adapter for local uvicorn/Docker development. Needs the `sqlite` extra (aiosqlite)."""

    def __init__(self, path: str) -> None:
        self._path = path

    async def _ensure_migrated(self) -> None:
        if self._path in _migrated_paths:
            return

        import aiosqlite

        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY)"
            )
            cursor = await conn.execute("SELECT filename FROM schema_migrations")
            applied = {row[0] for row in await cursor.fetchall()}

            for migration in sorted(migrations_dir().glob("*.sql")):
                if migration.name in applied:
                    continue
                await conn.executescript(migration.read_text())
                await conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (?)",
                    (migration.name,),
                )

            await conn.commit()

        _migrated_paths.add(self._path)

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        await self._ensure_migrated()
        import aiosqlite

        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        rows = await self.fetch_all(sql, params)
        return rows[0] if rows else None

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        await self._ensure_migrated()
        import aiosqlite

        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(sql, params)
            await conn.commit()

    async def batch(self, statements: Sequence[Statement]) -> None:
        """All statements in one transaction: either every one is applied or none is."""
        await self._ensure_migrated()
        import aiosqlite

        async with aiosqlite.connect(self._path) as conn:
            try:
                for sql, params in statements:
                    await conn.execute(sql, params)
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise


class D1BindingDatabase:
    """Cloudflare Worker D1 binding adapter for env.DB."""

    def __init__(self, db: Any) -> None:
        self._db = db

    @staticmethod
    def _get(value: Any, key: str, default: Any = None) -> Any:
        if value is None:
            return default
        try:
            return value[key]
        except (TypeError, KeyError):
            return getattr(value, key, default)

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        result = await self._db.prepare(sql).bind(*params).all()
        return self._get(result, "results", [])

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        return await self._db.prepare(sql).bind(*params).first()

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        await self._db.prepare(sql).bind(*params).run()

    async def batch(self, statements: Sequence[Statement]) -> None:
        """D1's batch(): the statements run as one implicit transaction."""
        prepared = [self._db.prepare(sql).bind(*params) for sql, params in statements]
        try:
            # D1 expects a JS array; a Python list reaches JS as a PyProxy.
            from pyodide.ffi import to_js

            prepared = to_js(prepared)
        except ImportError:  # not in a Worker (tests pass a fake binding)
            pass
        await self._db.batch(prepared)


class D1HttpDatabase:
    """
    D1 HTTP adapter for non-Worker runtimes that still want to use Cloudflare D1.

    Prefer D1BindingDatabase inside Cloudflare Workers. This adapter is useful
    if the same app is later hosted somewhere like Render but still points at D1.
    """

    def __init__(self, account_id: str, database_id: str, api_token: str, transport: Any = None) -> None:
        self._url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/d1/database/{database_id}/query"
        )
        self._headers = {"Authorization": f"Bearer {api_token}"}
        self._transport = transport  # tests pass an httpx.MockTransport

    async def _query(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=10, transport=self._transport) as client:
            response = await client.post(
                self._url,
                headers=self._headers,
                json={"sql": sql, "params": list(params)},
            )
            response.raise_for_status()

        body = response.json()
        if not body.get("success"):
            raise RuntimeError(f"D1 query failed: {body.get('errors')}")
        return body["result"][0].get("results", [])

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return await self._query(sql, params)

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        rows = await self._query(sql, params)
        return rows[0] if rows else None

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        await self._query(sql, params)

    async def batch(self, statements: Sequence[Statement]) -> None:
        """
        One request per statement, in order. NOT atomic: if a later statement
        fails, the earlier ones stay applied. Use the binding when that matters.
        """
        for sql, params in statements:
            await self._query(sql, params)


def get_database(request: HTTPConnection) -> Database:
    """
    Select the database backend for the current runtime.

    Modes:
    - sqlite: local uvicorn/Docker
    - d1_binding: Cloudflare Workers env.DB binding
    - d1_http: any runtime using Cloudflare D1 over REST

    If DATABASE_MODE is omitted and env.DB exists, d1_binding is used.
    """
    env = request.scope.get("env")
    has_d1_binding = env is not None and hasattr(env, "DB")
    mode = get_config(request, "DATABASE_MODE", "d1_binding" if has_d1_binding else "sqlite")

    if mode == "sqlite":
        return SQLiteDatabase(get_config(request, "DATABASE_PATH", "./local.db") or "./local.db")

    if mode == "d1_binding":
        if not has_d1_binding:
            raise RuntimeError("DATABASE_MODE='d1_binding' requires a Cloudflare D1 env.DB binding")
        return D1BindingDatabase(env.DB)

    if mode == "d1_http":
        account_id = get_config(request, "CF_ACCOUNT_ID")
        database_id = get_config(request, "CF_D1_DATABASE_ID")
        api_token = get_config(request, "CF_D1_API_TOKEN")
        if not account_id or not database_id or not api_token:
            raise RuntimeError("d1_http mode requires CF_ACCOUNT_ID, CF_D1_DATABASE_ID, and CF_D1_API_TOKEN")
        return D1HttpDatabase(account_id, database_id, api_token)

    raise RuntimeError(f"unknown DATABASE_MODE: {mode!r}")
