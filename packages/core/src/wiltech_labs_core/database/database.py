import os
import sqlite3
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from starlette.requests import HTTPConnection

from wiltech_labs_core.config import get_config

# One SQL statement and its parameters, as `batch` takes them.
Statement = tuple[str, tuple[Any, ...]]


class UniqueConstraintError(Exception):
    """
    A write broke a UNIQUE constraint or unique index, whatever the backend.

    Repositories catch it and raise their domain's ConflictError ("an employee
    with this email already exists"), so the message a user sees is written by
    the app, not by SQLite.
    """


def _is_unique_violation(exc: BaseException | str) -> bool:
    # SQLite, D1 (which surfaces SQLite's message) and D1 over HTTP all say this.
    return "UNIQUE constraint failed" in str(exc)


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

    async def execute_returning(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        """
        Run one write with a `RETURNING` clause, commit it, and return the first
        row, or None when no row matched. D1 has no interactive transactions, so a
        guarded state change is one statement ("UPDATE ... WHERE status = 'OPEN'
        RETURNING id"), and whether a row came back is how the caller knows it won.
        """
        ...

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
            await conn.commit()
            cursor = await conn.execute("SELECT filename FROM schema_migrations")
            applied = {row[0] for row in await cursor.fetchall()}

            for migration in sorted(migrations_dir().glob("*.sql")):
                if migration.name in applied:
                    continue
                # One transaction per migration, its bookkeeping row included: a migration that
                # fails half-way leaves nothing behind and runs again next time.
                name = migration.name.replace("'", "''")
                await conn.executescript(
                    f"BEGIN;\n{migration.read_text(encoding='utf-8')}\n"
                    f"INSERT INTO schema_migrations (filename) VALUES ('{name}');\nCOMMIT;"
                )

        _migrated_paths.add(self._path)

    async def _connect(self):
        await self._ensure_migrated()
        import aiosqlite

        conn = await aiosqlite.connect(self._path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        return conn

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        conn = await self._connect()
        try:
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        rows = await self.fetch_all(sql, params)
        return rows[0] if rows else None

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        await self.execute_returning(sql, params)

    async def execute_returning(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        conn = await self._connect()
        try:
            try:
                cursor = await conn.execute(sql, params)
                row = await cursor.fetchone()
                await conn.commit()
            except sqlite3.IntegrityError as exc:
                if _is_unique_violation(exc):
                    raise UniqueConstraintError(str(exc)) from exc
                raise
            return dict(row) if row is not None else None
        finally:
            await conn.close()

    async def batch(self, statements: Sequence[Statement]) -> None:
        """All statements in one transaction: either every one is applied or none is."""
        conn = await self._connect()
        try:
            try:
                for sql, params in statements:
                    await conn.execute(sql, params)
                await conn.commit()
            except Exception as exc:
                await conn.rollback()
                if isinstance(exc, sqlite3.IntegrityError) and _is_unique_violation(exc):
                    raise UniqueConstraintError(str(exc)) from exc
                raise
        finally:
            await conn.close()


class D1BindingDatabase:
    """Cloudflare Worker D1 binding adapter for env.DB."""

    def __init__(self, db: Any) -> None:
        self._db = db

    @staticmethod
    def _bind_params(params: tuple[Any, ...]) -> list[Any]:
        # Pyodide turns None into JS `undefined`, which D1 rejects: send JS null instead.
        try:
            from pyodide.ffi import jsnull
        except ImportError:  # not in a Worker (tests pass a fake binding)
            return list(params)
        return [jsnull if value is None else value for value in params]

    def _statement(self, sql: str, params: tuple[Any, ...]) -> Any:
        statement = self._db.prepare(sql)
        return statement.bind(*self._bind_params(params)) if params else statement

    @staticmethod
    def _get(value: Any, key: str, default: Any = None) -> Any:
        if value is None:
            return default
        try:
            return value[key]
        except (TypeError, KeyError):
            return getattr(value, key, default)

    @staticmethod
    def _to_dict(row: Any) -> Optional[dict[str, Any]]:
        if row is None:
            return None
        if hasattr(row, "to_py"):  # a JsProxy object from D1
            row = row.to_py()
        return dict(row)

    def _rows(self, result: Any) -> list[dict[str, Any]]:
        rows = self._get(result, "results", []) or []
        if hasattr(rows, "to_py"):
            rows = rows.to_py()
        return [self._to_dict(row) for row in rows]

    @staticmethod
    def _raise_unique(exc: BaseException) -> None:
        if _is_unique_violation(exc):
            raise UniqueConstraintError(str(exc)) from exc

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return self._rows(await self._statement(sql, params).all())

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        return self._to_dict(await self._statement(sql, params).first())

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        try:
            await self._statement(sql, params).run()
        except Exception as exc:  # D1 surfaces SQLite errors as JS exceptions
            self._raise_unique(exc)
            raise

    async def execute_returning(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        try:
            rows = self._rows(await self._statement(sql, params).all())
        except Exception as exc:
            self._raise_unique(exc)
            raise
        return rows[0] if rows else None

    async def batch(self, statements: Sequence[Statement]) -> None:
        """D1's batch(): the statements run as one implicit transaction."""
        prepared = [self._statement(sql, params) for sql, params in statements]
        try:
            # D1 expects a JS array; a Python list reaches JS as a PyProxy.
            from pyodide.ffi import to_js

            prepared = to_js(prepared)
        except ImportError:  # not in a Worker (tests pass a fake binding)
            pass
        try:
            await self._db.batch(prepared)
        except Exception as exc:
            self._raise_unique(exc)
            raise


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
            if response.status_code >= 400 and _is_unique_violation(response.text):
                raise UniqueConstraintError(response.text)
            response.raise_for_status()

        body = response.json()
        if not body.get("success"):
            errors = body.get("errors")
            if _is_unique_violation(str(errors)):
                raise UniqueConstraintError(str(errors))
            raise RuntimeError(f"D1 query failed: {errors}")
        return body["result"][0].get("results", [])

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return await self._query(sql, params)

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        rows = await self._query(sql, params)
        return rows[0] if rows else None

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        await self._query(sql, params)

    async def execute_returning(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        rows = await self._query(sql, params)
        return rows[0] if rows else None

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
