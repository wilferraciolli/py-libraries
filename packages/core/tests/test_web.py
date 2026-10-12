from fastapi import FastAPI
from fastapi.testclient import TestClient

from wiltech_labs_core import (
    EnvCORSMiddleware,
    NotFoundError,
    TooManyRequestsError,
    health_router,
    register_error_handlers,
)


def build_app(checks=None) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(EnvCORSMiddleware)
    app.include_router(health_router(checks), prefix="/api")

    @app.get("/api/missing")
    async def missing():
        raise NotFoundError("Todo not found")

    @app.get("/api/limited")
    async def limited():
        raise TooManyRequestsError("Daily AI limit reached", retry_after=3600)

    @app.get("/api/boom")
    async def boom():
        raise ValueError("bug")

    return app


def test_app_errors_become_detail_responses():
    client = TestClient(build_app())
    response = client.get("/api/missing")
    assert response.status_code == 404 and response.json() == {"detail": "Todo not found"}

    response = client.get("/api/limited")
    assert response.status_code == 429 and response.headers["Retry-After"] == "3600"


def test_health_without_checks_keeps_the_original_shape():
    assert TestClient(build_app()).get("/api/health").json() == {"status": "API is running", "runtime": "FastAPI"}


def test_a_failing_check_makes_health_503():
    async def ok(request):
        return None

    async def down(request):
        raise ConnectionError("db down")

    response = TestClient(build_app({"db": ok, "ai": down})).get("/api/health")
    assert response.status_code == 503
    assert response.json()["checks"] == {"db": "ok", "ai": "error"}


def test_cors_origins_are_read_per_request(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:4200")
    client = TestClient(build_app())

    allowed = client.get("/api/health", headers={"Origin": "http://localhost:4200"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:4200"

    other = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_an_unhandled_error_still_has_cors_headers(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:4200")
    client = TestClient(build_app(), raise_server_exceptions=False)

    response = client.get("/api/boom", headers={"Origin": "http://localhost:4200"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Something went wrong on the server."}
    assert response.headers["access-control-allow-origin"] == "http://localhost:4200"


def test_default_origins_apply_when_cors_origins_is_unset(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    app = FastAPI()
    app.add_middleware(EnvCORSMiddleware, default_origins="http://localhost:4200")
    app.include_router(health_router(), prefix="/api")

    response = TestClient(app).get("/api/health", headers={"Origin": "http://localhost:4200"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:4200"
