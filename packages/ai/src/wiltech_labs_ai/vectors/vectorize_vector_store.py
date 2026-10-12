import json
from typing import Any, Optional, Sequence

import httpx

from wiltech_labs_ai.vectors.vector_store import VectorMatch, VectorRecord, chunked

# Vectorize caps topK at 100 when values and full metadata aren't returned.
MAX_TOP_K = 100
# Ids per get_by_ids / delete_by_ids request, and vectors per upsert request.
ID_BATCH = 100
UPSERT_BATCH = 500


class VectorizeVectorStore:
    """
    Cloudflare Vectorize over its REST API (v2), so it works from a Worker,
    Docker or the home server alike.

    One-off setup per index (dimensions must match the embedding model):

        npx wrangler vectorize create app-vectors --dimensions=768 --metric=cosine
        npx wrangler vectorize create-metadata-index app-vectors --propertyName=scope --type=string

    The metadata index on `scope` is what makes the tenancy filter work; create
    it before inserting vectors. The store's `namespace` maps to a Vectorize
    namespace, and vector ids are "{namespace}:{id}" so two resource types
    can't collide (ids are limited to 64 bytes).
    """

    def __init__(
        self,
        account_id: str,
        api_token: str,
        index_name: str,
        namespace: str,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self._base_url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/vectorize/v2/indexes/{index_name}"
        )
        self._headers = {"Authorization": f"Bearer {api_token}"}
        self.namespace = namespace
        self._transport = transport  # tests pass an httpx.MockTransport

    def _vector_id(self, resource_id: str) -> str:
        return f"{self.namespace}:{resource_id}"

    def _resource_id(self, vector_id: str) -> str:
        return vector_id.removeprefix(f"{self.namespace}:")

    async def _post(self, path: str, extra_headers: Optional[dict[str, str]] = None, **kwargs: Any) -> Any:
        headers = {**self._headers, **(extra_headers or {})}
        async with httpx.AsyncClient(timeout=30, transport=self._transport) as client:
            response = await client.post(f"{self._base_url}/{path}", headers=headers, **kwargs)
            response.raise_for_status()
        body = response.json()
        if not body.get("success", False):
            raise RuntimeError(f"Vectorize {path} failed: {body.get('errors')}")
        return body.get("result")

    async def upsert(self, records: Sequence[VectorRecord]) -> None:
        for batch in chunked(list(records), UPSERT_BATCH):
            lines = [
                json.dumps(
                    {
                        "id": self._vector_id(record.id),
                        "values": record.vector,
                        "namespace": self.namespace,
                        "metadata": {**record.metadata, "scope": record.scope, "model": record.model},
                    }
                )
                for record in batch
            ]
            await self._post(
                "upsert",
                content="\n".join(lines).encode(),
                extra_headers={"Content-Type": "application/x-ndjson"},
            )

    async def query(self, scopes: Sequence[str], vector: list[float], limit: int) -> list[VectorMatch]:
        if not scopes:
            return []
        result = await self._post(
            "query",
            json={
                "vector": vector,
                "topK": max(1, min(limit, MAX_TOP_K)),
                "namespace": self.namespace,
                "returnMetadata": "indexed",
                "filter": {"scope": {"$in": list(dict.fromkeys(scopes))}},
            },
        )
        return [
            VectorMatch(self._resource_id(match["id"]), float(match["score"]), match.get("metadata") or {})
            for match in (result or {}).get("matches", [])
        ]

    async def delete(self, ids: Sequence[str]) -> None:
        for batch in chunked(list(ids), ID_BATCH):
            await self._post("delete_by_ids", json={"ids": [self._vector_id(i) for i in batch]})

    async def existing_ids(self, ids: Sequence[str]) -> set[str]:
        found: set[str] = set()
        for batch in chunked(list(ids), ID_BATCH):
            result = await self._post("get_by_ids", json={"ids": [self._vector_id(i) for i in batch]})
            found.update(self._resource_id(vector["id"]) for vector in (result or []))
        return found
