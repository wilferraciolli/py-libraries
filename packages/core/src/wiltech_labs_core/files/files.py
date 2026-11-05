"""
Portable file storage: the same three calls on a local folder (uvicorn, Docker, tests) and on a
Cloudflare R2 bucket binding (Workers), chosen per request like the Database.

Keys are the app's own (`documents/<org>/<uuid>`): a key never comes from a user's file name, so
nothing can be written outside the store. Files are kept whole in memory; this is for documents
and images (a few MB), not video.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from starlette.requests import HTTPConnection

from wiltech_labs_core.config import get_config

_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*$")
DEFAULT_CONTENT_TYPE = "application/octet-stream"


def check_key(key: str) -> str:
    """A key is slash-separated segments of letters, digits, dots, dashes and underscores, none
    starting with a dot: no `..`, no absolute paths, no surprises on any store."""
    if not _KEY.match(key) or len(key) > 512:
        raise ValueError(f"invalid file key: {key!r}")
    return key


@dataclass(frozen=True)
class StoredFile:
    key: str
    data: bytes
    content_type: str = DEFAULT_CONTENT_TYPE

    @property
    def size(self) -> int:
        return len(self.data)


class FileStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str = DEFAULT_CONTENT_TYPE) -> None:
        """Store `data` at `key`, replacing what was there."""
        ...

    async def get(self, key: str) -> Optional[StoredFile]:
        """The file at `key`, or None."""
        ...

    async def delete(self, key: str) -> None:
        """Remove the file at `key`; nothing happens if there is none."""
        ...


class LocalFileStore:
    """Files in a folder, each with a `<name>.meta.json` beside it holding its content type."""

    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def _path(self, key: str) -> Path:
        return self._root / check_key(key)

    @staticmethod
    def _meta(path: Path) -> Path:
        return path.with_name(f"{path.name}.meta.json")

    async def put(self, key: str, data: bytes, content_type: str = DEFAULT_CONTENT_TYPE) -> None:
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self._meta(path).write_text(json.dumps({"content_type": content_type}), encoding="utf8")

        await asyncio.to_thread(write)

    async def get(self, key: str) -> Optional[StoredFile]:
        path = self._path(key)

        def read() -> Optional[StoredFile]:
            if not path.is_file():
                return None
            meta = self._meta(path)
            content_type = DEFAULT_CONTENT_TYPE
            if meta.is_file():
                content_type = json.loads(meta.read_text(encoding="utf8")).get("content_type", content_type)
            return StoredFile(key, path.read_bytes(), content_type)

        return await asyncio.to_thread(read)

    async def delete(self, key: str) -> None:
        path = self._path(key)

        def remove() -> None:
            path.unlink(missing_ok=True)
            self._meta(path).unlink(missing_ok=True)

        await asyncio.to_thread(remove)


class R2BindingFileStore:
    """A Cloudflare Worker R2 bucket binding (`env.FILES` by default)."""

    def __init__(self, bucket: Any) -> None:
        self._bucket = bucket

    @staticmethod
    def _to_js(value: Any) -> Any:
        try:
            from pyodide.ffi import to_js
        except ImportError:  # not in a Worker (tests pass a fake binding)
            return value
        from js import Object  # type: ignore[import-not-found]

        return to_js(value, dict_converter=Object.fromEntries)

    @staticmethod
    def _bytes(value: Any) -> Any:
        try:
            from pyodide.ffi import to_js
        except ImportError:
            return value
        return to_js(value)

    async def put(self, key: str, data: bytes, content_type: str = DEFAULT_CONTENT_TYPE) -> None:
        options = self._to_js({"httpMetadata": {"contentType": content_type}})
        await self._bucket.put(check_key(key), self._bytes(data), options)

    async def get(self, key: str) -> Optional[StoredFile]:
        found = await self._bucket.get(check_key(key))
        if found is None:
            return None
        body = await found.arrayBuffer()
        data = bytes(body.to_py()) if hasattr(body, "to_py") else bytes(body)
        metadata = getattr(found, "httpMetadata", None)
        content_type = getattr(metadata, "contentType", None) if metadata is not None else None
        if content_type is None and isinstance(metadata, dict):
            content_type = metadata.get("contentType")
        return StoredFile(key, data, content_type or DEFAULT_CONTENT_TYPE)

    async def delete(self, key: str) -> None:
        await self._bucket.delete(check_key(key))


def get_file_store(request: HTTPConnection) -> FileStore:
    """
    Select the file store for the current runtime.

    Modes (`FILE_STORE_MODE`):
    - local: a folder (`FILES_DIR`, default ./files)
    - r2_binding: the Worker's R2 bucket binding named by `FILE_STORE_BINDING` (default FILES)

    If FILE_STORE_MODE is omitted and the binding exists, r2_binding is used.
    """
    env = request.scope.get("env")
    binding = get_config(request, "FILE_STORE_BINDING", "FILES") or "FILES"
    has_binding = env is not None and hasattr(env, binding)
    mode = get_config(request, "FILE_STORE_MODE", "r2_binding" if has_binding else "local")

    if mode == "local":
        return LocalFileStore(get_config(request, "FILES_DIR", "./files") or "./files")

    if mode == "r2_binding":
        if not has_binding:
            raise RuntimeError(f"FILE_STORE_MODE='r2_binding' requires a Cloudflare R2 env.{binding} binding")
        return R2BindingFileStore(getattr(env, binding))

    raise RuntimeError(f"unknown FILE_STORE_MODE: {mode!r}")
