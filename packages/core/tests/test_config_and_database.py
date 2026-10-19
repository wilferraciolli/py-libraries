import json
from types import SimpleNamespace

import httpx
import pytest

from wiltech_labs_core import (
    D1BindingDatabase,
    D1HttpDatabase,
    SQLiteDatabase,
    UniqueConstraintError,
    get_binding,
    get_config,
    get_database,
    load_dotenv,
)


def request_with(env=None):
    """Just enough of a Starlette request: get_config only reads scope["env"]."""
    return SimpleNamespace(scope={"env": env} if env is not None else {})


def test_worker_env_wins_over_os_environ(monkeypatch):
    monkeypatch.setenv("GREETING", "from-os")
    assert get_config(request_with(SimpleNamespace(GREETING="from-worker")), "GREETING") == "from-worker"
    assert get_config(request_with(), "GREETING") == "from-os"
    assert get_config(request_with(), "MISSING", "fallback") == "fallback"


def test_get_binding_is_none_outside_a_worker():
    bucket = object()
    assert get_binding(request_with(SimpleNamespace(BUCKET=bucket)), "BUCKET") is bucket
    assert get_binding(request_with(), "BUCKET") is None


def test_load_dotenv_never_overrides_the_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('# comment\nNEW_KEY="quoted"\nEXISTING=from-file\n')
    monkeypatch.setenv("EXISTING", "from-env")
    monkeypatch.delenv("NEW_KEY", raising=False)

    load_dotenv(env_file)

    import os

    assert os.environ["NEW_KEY"] == "quoted"
    assert os.environ["EXISTING"] == "from-env"


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_items.sql").write_text("CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT NOT NULL);")
    monkeypatch.setenv("MIGRATIONS_DIR", str(migrations))
    return SQLiteDatabase(str(tmp_path / "test.db"))


async def test_sqlite_applies_migrations_and_round_trips(sqlite_db):
    await sqlite_db.execute("INSERT INTO items (id, name) VALUES (?, ?)", ("1", "one"))
    assert await sqlite_db.fetch_all("SELECT id, name FROM items") == [{"id": "1", "name": "one"}]
    assert await sqlite_db.fetch_one("SELECT name FROM items WHERE id = ?", ("2",)) is None


async def test_sqlite_batch_is_all_or_nothing(sqlite_db):
    await sqlite_db.batch([("INSERT INTO items VALUES (?, ?)", ("1", "one")), ("INSERT INTO items VALUES (?, ?)", ("2", "two"))])
    assert len(await sqlite_db.fetch_all("SELECT * FROM items")) == 2

    with pytest.raises(Exception):
        await sqlite_db.batch(
            [
                ("INSERT INTO items VALUES (?, ?)", ("3", "three")),
                ("INSERT INTO items VALUES (?, ?)", ("1", "duplicate id")),
            ]
        )
    assert await sqlite_db.fetch_one("SELECT * FROM items WHERE id = '3'") is None


async def test_a_missing_migrations_folder_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("MIGRATIONS_DIR", str(tmp_path / "nope"))
    with pytest.raises(RuntimeError, match="Migrations directory not found"):
        await SQLiteDatabase(str(tmp_path / "x.db")).fetch_all("SELECT 1")


async def test_sqlite_execute_returning_commits_and_returns_the_row(sqlite_db):
    row = await sqlite_db.execute_returning("INSERT INTO items (id, name) VALUES (?, ?) RETURNING id, name", ("1", "one"))
    assert row == {"id": "1", "name": "one"}
    assert await sqlite_db.fetch_one("SELECT name FROM items WHERE id = '1'") == {"name": "one"}
    # A guarded update that matches nothing returns None: the caller lost the race.
    assert await sqlite_db.execute_returning("UPDATE items SET name = 'x' WHERE id = '9' RETURNING id") is None


async def test_sqlite_unique_violations_raise_unique_constraint_error(sqlite_db):
    await sqlite_db.execute("INSERT INTO items VALUES (?, ?)", ("1", "one"))
    with pytest.raises(UniqueConstraintError):
        await sqlite_db.execute("INSERT INTO items VALUES (?, ?)", ("1", "again"))
    with pytest.raises(UniqueConstraintError):
        await sqlite_db.batch([("INSERT INTO items VALUES (?, ?)", ("1", "again"))])


async def test_a_failing_migration_leaves_nothing_behind(tmp_path, monkeypatch):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_bad.sql").write_text("CREATE TABLE a (id TEXT); CREATE TABLE a (id TEXT);")
    monkeypatch.setenv("MIGRATIONS_DIR", str(migrations))
    db = SQLiteDatabase(str(tmp_path / "bad.db"))
    with pytest.raises(Exception):
        await db.fetch_all("SELECT 1")
    (migrations / "001_bad.sql").write_text("CREATE TABLE a (id TEXT);")
    assert await db.fetch_all("SELECT name FROM sqlite_master WHERE name = 'a'") == [{"name": "a"}]


class FakeStatement:
    def __init__(self, log, sql, rows=None, error=None):
        self.log, self.sql, self.params, self.rows, self.error = log, sql, (), rows or [], error

    def bind(self, *params):
        self.params = params
        return self

    async def run(self):
        if self.error:
            raise self.error
        self.log.append(("run", self.sql, self.params))

    async def all(self):
        if self.error:
            raise self.error
        self.log.append(("all", self.sql, self.params))
        return {"results": self.rows}

    async def first(self):
        return self.rows[0] if self.rows else None


class FakeD1:
    def __init__(self, rows=None, error=None):
        self.log, self.rows, self.error = [], rows, error

    def prepare(self, sql):
        return FakeStatement(self.log, sql, self.rows, self.error)

    async def batch(self, statements):
        if self.error:
            raise self.error
        self.log.append(("batch", [(s.sql, s.params) for s in statements]))


async def test_d1_binding_execute_returning_reads_the_row():
    d1 = FakeD1(rows=[{"id": "1"}])
    assert await D1BindingDatabase(d1).execute_returning("UPDATE t SET x = ? RETURNING id", (None,)) == {"id": "1"}
    assert d1.log == [("all", "UPDATE t SET x = ? RETURNING id", (None,))]


async def test_d1_binding_maps_unique_violations():
    d1 = FakeD1(error=RuntimeError("D1_ERROR: UNIQUE constraint failed: items.id: SQLITE_CONSTRAINT"))
    with pytest.raises(UniqueConstraintError):
        await D1BindingDatabase(d1).execute("INSERT INTO items VALUES (?)", ("1",))


async def test_d1_binding_batch_prepares_every_statement_and_sends_one_batch():
    d1 = FakeD1()
    await D1BindingDatabase(d1).batch([("INSERT A", (1,)), ("INSERT B", (2,))])
    assert d1.log == [("batch", [("INSERT A", (1,)), ("INSERT B", (2,))])]


async def test_d1_http_posts_sql_and_params():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"success": True, "result": [{"results": [{"id": "1"}]}]})

    db = D1HttpDatabase("acc", "dbid", "token", transport=httpx.MockTransport(handler))
    assert await db.fetch_one("SELECT id FROM t WHERE id = ?", ("1",)) == {"id": "1"}
    assert str(seen[0].url) == "https://api.cloudflare.com/client/v4/accounts/acc/d1/database/dbid/query"
    assert seen[0].headers["Authorization"] == "Bearer token"
    assert json.loads(seen[0].content) == {"sql": "SELECT id FROM t WHERE id = ?", "params": ["1"]}


def test_get_database_picks_the_binding_inside_a_worker(monkeypatch):
    monkeypatch.delenv("DATABASE_MODE", raising=False)
    assert isinstance(get_database(request_with(SimpleNamespace(DB=FakeD1()))), D1BindingDatabase)
    assert isinstance(get_database(request_with()), SQLiteDatabase)


def test_get_database_d1_http_needs_credentials(monkeypatch):
    monkeypatch.setenv("DATABASE_MODE", "d1_http")
    for key in ("CF_ACCOUNT_ID", "CF_D1_DATABASE_ID", "CF_D1_API_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="CF_ACCOUNT_ID"):
        get_database(request_with())
