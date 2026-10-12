import uuid
from typing import Any, Optional, Sequence

import httpx

from wiltech_labs_ai.vectors.vector_store import VectorMatch, VectorRecord, chunked

ID_BATCH = 256


class QdrantVectorStore:
    """
    Qdrant over its REST API, e.g. the `qdrant/qdrant` container on the home
    server (reach it on the Docker network; don't publish it through NPM).

    One collection can hold every resource type: each point carries
    `namespace`, `scope` and `resource_id` in its payload, and every query
    filters on namespace + scope. Point ids are UUID5s of "{namespace}:{id}",
    because Qdrant only accepts UUIDs or integers as ids.

    Call `ensure_collection(dimensions)` once at startup (or from a script);
    it is a no-op when the collection exists.
    """

    def __init__(
        self,
        base_url: str,
        collection: str,
        namespace: str,
        api_key: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self.collection = collection
        self.namespace = namespace
        self._headers = {"api-key": api_key} if api_key else {}
        self._transport = transport  # tests pass an httpx.MockTransport

    def point_id(self, resource_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.namespace}:{resource_id}"))

    async def _request(self, method: str, path: str, body: Optional[dict] = None) -> Any:
        async with httpx.AsyncClient(timeout=30, transport=self._transport) as client:
            response = await client.request(
                method, f"{self._base_url}/collections/{self.collection}{path}", headers=self._headers, json=body
            )
            response.raise_for_status()
        return response.json().get("result")

    async def ensure_collection(self, dimensions: int) -> None:
        exists = await self._request("GET", "/exists")
        if exists and exists.get("exists"):
            return
        await self._request("PUT", "", {"vectors": {"size": dimensions, "distance": "Cosine"}})
        for field_name in ("namespace", "scope", "resource_id"):
            await self._request("PUT", "/index", {"field_name": field_name, "field_schema": "keyword"})

    async def upsert(self, records: Sequence[VectorRecord]) -> None:
        for batch in chunked(list(records), ID_BATCH):
            await self._request(
                "PUT",
                "/points?wait=true",
                {
                    "points": [
                        {
                            "id": self.point_id(record.id),
                            "vector": record.vector,
                            "payload": {
                                **record.metadata,
                                "namespace": self.namespace,
                                "scope": record.scope,
                                "resource_id": record.id,
                                "model": record.model,
                            },
                        }
                        for record in batch
                    ]
                },
            )

    async def query(self, scopes: Sequence[str], vector: list[float], limit: int) -> list[VectorMatch]:
        if not scopes:
            return []
        result = await self._request(
            "POST",
            "/points/search",
            {
                "vector": vector,
                "limit": max(1, limit),
                "with_payload": True,
                "filter": {
                    "must": [
                        {"key": "namespace", "match": {"value": self.namespace}},
                        {"key": "scope", "match": {"any": list(dict.fromkeys(scopes))}},
                    ]
                },
            },
        )
        return [
            VectorMatch(point["payload"]["resource_id"], float(point["score"]), point.get("payload") or {})
            for point in (result or [])
        ]

    async def delete(self, ids: Sequence[str]) -> None:
        for batch in chunked(list(ids), ID_BATCH):
            await self._request("POST", "/points/delete?wait=true", {"points": [self.point_id(i) for i in batch]})

    async def existing_ids(self, ids: Sequence[str]) -> set[str]:
        found: set[str] = set()
        for batch in chunked(list(ids), ID_BATCH):
            result = await self._request(
                "POST",
                "/points",
                {"ids": [self.point_id(i) for i in batch], "with_payload": ["resource_id"], "with_vector": False},
            )
            found.update(point["payload"]["resource_id"] for point in (result or []))
        return found
