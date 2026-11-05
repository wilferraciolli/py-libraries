"""File storage: the local folder and the R2 binding (with a fake bucket) behave the same."""

from types import SimpleNamespace

import pytest

from wiltech_labs_core import LocalFileStore, R2BindingFileStore, check_key, get_file_store

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeObject:
    def __init__(self, data: bytes, content_type: str):
        self._data = data
        self.httpMetadata = {"contentType": content_type}

    async def arrayBuffer(self):
        return self._data


class FakeBucket:
    """Just enough of an R2 binding: put, get, delete."""

    def __init__(self):
        self.objects: dict[str, FakeObject] = {}

    async def put(self, key, data, options):
        self.objects[key] = FakeObject(bytes(data), options["httpMetadata"]["contentType"])

    async def get(self, key):
        return self.objects.get(key)

    async def delete(self, key):
        self.objects.pop(key, None)


@pytest.fixture(params=["local", "r2"])
def store(request, tmp_path):
    return LocalFileStore(str(tmp_path)) if request.param == "local" else R2BindingFileStore(FakeBucket())


async def test_a_file_is_stored_read_back_and_removed(store):
    await store.put("documents/org-1/abc.pdf", b"%PDF-1.7", "application/pdf")
    found = await store.get("documents/org-1/abc.pdf")
    assert (found.data, found.content_type, found.size) == (b"%PDF-1.7", "application/pdf", 8)

    await store.put("documents/org-1/abc.pdf", b"v2", "text/plain")  # replaced
    assert (await store.get("documents/org-1/abc.pdf")).data == b"v2"

    await store.delete("documents/org-1/abc.pdf")
    await store.delete("documents/org-1/abc.pdf")  # twice is fine
    assert await store.get("documents/org-1/abc.pdf") is None


@pytest.mark.parametrize("key", ["../etc/passwd", "/abs", "a//b", ".hidden", "a/../b", "spaces here", ""])
def test_keys_can_t_escape_the_store(key):
    with pytest.raises(ValueError):
        check_key(key)


async def test_a_bad_key_is_refused_before_anything_is_written(tmp_path):
    with pytest.raises(ValueError):
        await LocalFileStore(str(tmp_path)).put("../outside", b"x")
    assert not (tmp_path.parent / "outside").exists()


def test_the_store_follows_the_runtime(tmp_path, monkeypatch):
    monkeypatch.delenv("FILE_STORE_MODE", raising=False)
    monkeypatch.setenv("FILES_DIR", str(tmp_path))
    assert isinstance(get_file_store(SimpleNamespace(scope={})), LocalFileStore)
    worker = SimpleNamespace(scope={"env": SimpleNamespace(FILES=FakeBucket())})
    assert isinstance(get_file_store(worker), R2BindingFileStore)
    monkeypatch.setenv("FILE_STORE_MODE", "r2_binding")
    with pytest.raises(RuntimeError):
        get_file_store(SimpleNamespace(scope={}))
