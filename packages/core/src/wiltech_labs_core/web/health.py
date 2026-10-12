import logging
from typing import Awaitable, Callable, Mapping, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# A check gets the request (so it can build a Database / AI client from it)
# and raises if its dependency is down.
HealthCheck = Callable[[Request], Awaitable[None]]


def health_router(checks: Optional[Mapping[str, HealthCheck]] = None, prefix: str = "/health") -> APIRouter:
    """
    GET /health (mount under /api): `{"status", "runtime"}` like every app's
    status_router, plus `"checks": {"db": "ok", ...}` when checks are given.
    Any failing check makes it a 503, so an uptime monitor (Uptime Kuma)
    alerts on a broken dependency, not only on a dead process.

        app.include_router(health_router({"db": database_check}), prefix="/api")
    """
    router = APIRouter(prefix=prefix, tags=["health"])

    @router.get("")
    async def health_check(request: Request):
        body: dict = {"status": "API is running", "runtime": "FastAPI"}
        if not checks:
            return body

        results: dict[str, str] = {}
        for name, check in checks.items():
            try:
                await check(request)
                results[name] = "ok"
            except Exception as exc:
                # The reason goes to the logs, not the public response.
                logger.warning("health check %s failed: %r", name, exc)
                results[name] = "error"

        body["checks"] = results
        if any(result != "ok" for result in results.values()):
            body["status"] = "API is degraded"
            return JSONResponse(status_code=503, content=body)
        return body

    return router


async def database_check(request: Request) -> None:
    """A health check that runs `SELECT 1` against the request's database."""
    from wiltech_labs_core.database import get_database

    await get_database(request).fetch_one("SELECT 1 AS ok")
