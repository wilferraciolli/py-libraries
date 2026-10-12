import json
from datetime import datetime, timezone
from typing import Sequence

from wiltech_labs_ai.vectors.vector_store import VectorMatch, VectorRecord, chunked, dot, normalise
from wiltech_labs_core import Database

# Migration for DatabaseVectorStore (copy into migrations/ and schema.sql).
# The same table fastapi-ai's migration 007 creates, so that app can switch
# without moving data. `user_id` holds the record's scope.
RESOURCE_EMBEDDINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS resource_embeddings (
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    model TEXT NOT NULL,
    embedding TEXT NOT NULL,
    created_date TEXT NOT NULL,
    PRIMARY KEY (resource_type, resource_id)
);

CREATE INDEX IF NOT EXISTS idx_resource_embeddings_user_type
    ON resource_embeddings(user_id, resource_type);
""".strip()

# D1 allows at most 100 bound parameters per statement.
MAX_PARAMS = 90


class DatabaseVectorStore:
    """
    Vectors in the app's own database (`resource_embeddings`), ranked in
    Python: brute-force cosine over the rows of the queried scopes. Works on
    SQLite and D1 with no extra infrastructure; fine for thousands of vectors
    per scope. Move to Vectorize or Qdrant behind VectorStore when that stops
    being true.

    Vectors are stored normalised, so cosine similarity is a dot product.
    """

    def __init__(self, db: Database, namespace: str, table: str = "resource_embeddings") -> None:
        self.db = db
        self.namespace = namespace
        self.table = table

    async def upsert(self, records: Sequence[VectorRecord]) -> None:
        if not records:
            return
        created = datetime.now(timezone.utc).isoformat()
        await self.db.batch(
            [
                (
                    f"INSERT OR REPLACE INTO {self.table} "
                    "(resource_type, resource_id, user_id, model, embedding, created_date) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        self.namespace,
                        record.id,
                        record.scope,
                        record.model,
                        json.dumps(normalise(record.vector)),
                        created,
                    ),
                )
                for record in records
            ]
        )

    async def query(self, scopes: Sequence[str], vector: list[float], limit: int) -> list[VectorMatch]:
        # The scope filter is always part of the query: it is the tenancy boundary.
        if not scopes:
            return []

        query_vector = normalise(vector)
        matches: list[VectorMatch] = []
        for scope_chunk in chunked(list(dict.fromkeys(scopes)), MAX_PARAMS):
            placeholders = ", ".join("?" for _ in scope_chunk)
            rows = await self.db.fetch_all(
                f"SELECT resource_id, embedding FROM {self.table} "
                f"WHERE resource_type = ? AND user_id IN ({placeholders})",
                (self.namespace, *scope_chunk),
            )
            matches.extend(
                VectorMatch(row["resource_id"], dot(query_vector, json.loads(row["embedding"]))) for row in rows
            )

        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:limit]

    async def delete(self, ids: Sequence[str]) -> None:
        for id_chunk in chunked(list(ids), MAX_PARAMS):
            placeholders = ", ".join("?" for _ in id_chunk)
            await self.db.execute(
                f"DELETE FROM {self.table} WHERE resource_type = ? AND resource_id IN ({placeholders})",
                (self.namespace, *id_chunk),
            )

    async def existing_ids(self, ids: Sequence[str]) -> set[str]:
        found: set[str] = set()
        for id_chunk in chunked(list(ids), MAX_PARAMS):
            placeholders = ", ".join("?" for _ in id_chunk)
            rows = await self.db.fetch_all(
                f"SELECT resource_id FROM {self.table} WHERE resource_type = ? AND resource_id IN ({placeholders})",
                (self.namespace, *id_chunk),
            )
            found.update(row["resource_id"] for row in rows)
        return found
