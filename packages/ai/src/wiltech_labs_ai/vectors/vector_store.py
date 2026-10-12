import math
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence


@dataclass(frozen=True)
class VectorRecord:
    """
    One vector to store.

    `id` is the resource's id (a todo, a post, a document chunk). `scope` is
    the tenancy boundary: the owner's user id for private data, or e.g. a
    group id for data shared with a group. Every query filters by scope.
    `metadata` is kept by stores that support it (Vectorize, Qdrant); the
    database store ignores it.
    """

    id: str
    scope: str
    vector: list[float]
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VectorMatch:
    id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(Protocol):
    """
    Portable vector storage for one kind of resource (the store's
    `namespace`, e.g. "todo"), same idea as Database and AI: a search service
    doesn't know where the vectors live.

    - DatabaseVectorStore: the app's own SQLite/D1, brute-force cosine. No
      extra infrastructure; fine for thousands of vectors per scope.
    - VectorizeVectorStore: Cloudflare Vectorize over REST.
    - QdrantVectorStore: Qdrant (e.g. on the home server).
    """

    async def upsert(self, records: Sequence[VectorRecord]) -> None: ...

    async def query(self, scopes: Sequence[str], vector: list[float], limit: int) -> list[VectorMatch]:
        """The closest vectors, best first, only from `scopes` (empty scopes -> no results)."""
        ...

    async def delete(self, ids: Sequence[str]) -> None: ...

    async def existing_ids(self, ids: Sequence[str]) -> set[str]:
        """Which of `ids` are already indexed — for backfills that embed only what's missing."""
        ...


def normalise(vector: list[float]) -> list[float]:
    length = math.sqrt(sum(value * value for value in vector))
    return [value / length for value in vector] if length else vector


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def chunked(items: Sequence[Any], size: int) -> list[Sequence[Any]]:
    return [items[start : start + size] for start in range(0, len(items), size)]
