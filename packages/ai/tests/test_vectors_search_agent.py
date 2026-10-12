import json

import httpx
import pytest

from wiltech_labs_ai import (
    RESOURCE_EMBEDDINGS_TABLE_SQL,
    STEP_LIMIT_ANSWER,
    DatabaseVectorStore,
    QdrantVectorStore,
    Tool,
    ToolAgent,
    VectorizeVectorStore,
    VectorRecord,
    reciprocal_rank_fusion,
)
from wiltech_labs_core import SQLiteDatabase

# --- DatabaseVectorStore (real SQLite)


@pytest.fixture
def db(tmp_path, monkeypatch):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_embeddings.sql").write_text(RESOURCE_EMBEDDINGS_TABLE_SQL)
    monkeypatch.setenv("MIGRATIONS_DIR", str(migrations))
    return SQLiteDatabase(str(tmp_path / "vectors.db"))


async def test_database_store_ranks_by_cosine_within_scopes_only(db):
    todos = DatabaseVectorStore(db, "todo")
    await todos.upsert(
        [
            VectorRecord("t1", "alice", [1.0, 0.0], "m"),
            VectorRecord("t2", "alice", [0.7, 0.7], "m"),
            VectorRecord("t3", "bob", [1.0, 0.0], "m"),
        ]
    )

    matches = await todos.query(["alice"], [2.0, 0.0], 10)
    assert [m.id for m in matches] == ["t1", "t2"]  # never bob's
    assert matches[0].score == pytest.approx(1.0)
    assert await todos.query([], [1.0, 0.0], 10) == []
    assert [m.id for m in await todos.query(["alice", "bob"], [1.0, 0.0], 10)][:2] in (["t1", "t3"], ["t3", "t1"])


async def test_database_store_namespaces_and_backfill_helpers(db):
    todos, posts = DatabaseVectorStore(db, "todo"), DatabaseVectorStore(db, "post")
    await todos.upsert([VectorRecord("same-id", "alice", [1.0, 0.0], "m")])
    await posts.upsert([VectorRecord("same-id", "group-1", [0.0, 1.0], "m")])

    ids = [f"id-{n}" for n in range(150)]  # more than D1's 100-parameter limit
    await todos.upsert([VectorRecord(i, "alice", [1.0, 0.0], "m") for i in ids])
    assert await todos.existing_ids(ids + ["missing"]) == set(ids)

    await todos.delete(["same-id"])
    assert await todos.existing_ids(["same-id"]) == set()
    assert await posts.existing_ids(["same-id"]) == {"same-id"}


# --- Vectorize (REST shape)


async def test_vectorize_store_requests():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path.rsplit("/", 1)[-1]
        if path == "query":
            return httpx.Response(200, json={"success": True, "result": {"matches": [{"id": "todo:t1", "score": 0.9}]}})
        if path == "get_by_ids":
            return httpx.Response(200, json={"success": True, "result": [{"id": "todo:t1"}]})
        return httpx.Response(200, json={"success": True, "result": {}})

    store = VectorizeVectorStore("acc", "tok", "app-vectors", "todo", transport=httpx.MockTransport(handler))
    await store.upsert([VectorRecord("t1", "alice", [0.1, 0.2], "m", {"title": "Tax"})])
    matches = await store.query(["alice"], [0.1, 0.2], 500)
    assert await store.existing_ids(["t1", "t2"]) == {"t1"}
    await store.delete(["t1"])

    upsert, query, get, delete = seen
    assert str(upsert.url) == "https://api.cloudflare.com/client/v4/accounts/acc/vectorize/v2/indexes/app-vectors/upsert"
    assert upsert.headers["Content-Type"] == "application/x-ndjson"
    assert json.loads(upsert.content.decode().splitlines()[0]) == {
        "id": "todo:t1",
        "values": [0.1, 0.2],
        "namespace": "todo",
        "metadata": {"title": "Tax", "scope": "alice", "model": "m"},
    }
    body = json.loads(query.content)
    assert body["filter"] == {"scope": {"$in": ["alice"]}} and body["topK"] == 100 and body["namespace"] == "todo"
    assert [(m.id, m.score) for m in matches] == [("t1", 0.9)]
    assert json.loads(get.content) == {"ids": ["todo:t1", "todo:t2"]}
    assert json.loads(delete.content) == {"ids": ["todo:t1"]}


# --- Qdrant (REST shape)


async def test_qdrant_store_requests():
    seen = []
    store = QdrantVectorStore("http://qdrant:6333/", "vectors", "todo", api_key="secret")

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/exists"):
            return httpx.Response(200, json={"result": {"exists": False}})
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"result": [{"id": "x", "score": 0.8, "payload": {"resource_id": "t1"}}]})
        return httpx.Response(200, json={"result": {}})

    store._transport = httpx.MockTransport(handler)
    await store.ensure_collection(768)
    await store.upsert([VectorRecord("t1", "alice", [0.1], "m")])
    matches = await store.query(["alice", "alice"], [0.1], 5)

    assert seen[0].headers["api-key"] == "secret"
    create = seen[1]
    assert (create.method, create.url.path) == ("PUT", "/collections/vectors")
    assert json.loads(create.content) == {"vectors": {"size": 768, "distance": "Cosine"}}
    upsert = json.loads(seen[-2].content)["points"][0]
    assert upsert["id"] == store.point_id("t1") and upsert["payload"]["scope"] == "alice"
    search = json.loads(seen[-1].content)
    assert search["filter"]["must"][1] == {"key": "scope", "match": {"any": ["alice"]}}
    assert [(m.id, m.score) for m in matches] == [("t1", 0.8)]


# --- Reciprocal rank fusion


def test_rrf_rewards_items_found_by_both_rankings():
    fused = reciprocal_rank_fusion(["a", "b", "c"], ["c", "d"])
    assert [item for item, _ in fused][:1] == ["c"]
    assert dict(fused)["a"] == pytest.approx(1 / 61)
    assert reciprocal_rank_fusion() == []


# --- ToolAgent


class ScriptedLlm:
    """Replays a fixed list of assistant turns and records what it was sent."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.sent = []

    async def complete(self, model, messages, tools):
        self.sent.append((list(messages), tools))
        return self.turns.pop(0)


def count_tool(calls):
    async def handler(user_id, arguments):
        calls.append((user_id, arguments))
        return {"count": 2}

    return Tool("count_todos", "Count todos", {"type": "object"}, handler)


async def test_agent_runs_tools_as_the_server_user_and_answers():
    calls = []
    llm = ScriptedLlm(
        [
            {"content": None, "tool_calls": [{"id": "c1", "name": "count_todos", "arguments": '{"user_id": "bob", "state": "NEW"}'}]},
            {"content": " You have 2 new todos. ", "tool_calls": []},
        ]
    )
    question = [{"role": "user", "content": "how many new todos?"}]
    result = await ToolAgent(llm, "m", [count_tool(calls)]).run("alice", question)

    assert result.answer == "You have 2 new todos." and result.completed
    assert calls == [("alice", {"user_id": "bob", "state": "NEW"})]  # handler gets alice, whatever the model says
    assert [(c.name, c.result) for c in result.tool_calls] == [("count_todos", {"count": 2})]
    second_messages = llm.sent[1][0]
    assert second_messages[-1] == {"role": "tool", "tool_call_id": "c1", "content": '{"count": 2}'}
    assert question == [{"role": "user", "content": "how many new todos?"}]  # caller's list untouched


async def test_agent_reports_bad_tools_back_to_the_model_and_stops_at_the_step_limit():
    loop_turn = {"content": None, "tool_calls": [{"id": "c", "name": "nope", "arguments": "{}"}]}
    result = await ToolAgent(ScriptedLlm([loop_turn] * 3), "m", [], max_steps=3).run("alice", [])

    assert not result.completed and result.answer == STEP_LIMIT_ANSWER
    assert result.tool_calls[0].result == {"error": "unknown tool 'nope'"}
