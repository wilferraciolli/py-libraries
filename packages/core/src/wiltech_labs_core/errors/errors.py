from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """
    A business-rule failure a service raises. `register_error_handlers` turns
    it into `{"detail": ...}` with `status_code`, so routers need no
    try/except. Domain exceptions (a domain's exceptions.py) subclass these.
    """

    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(AppError):
    status_code = 404


class ForbiddenError(AppError):
    status_code = 403


class ConflictError(AppError):
    status_code = 409


class InvalidInputError(AppError):
    """Well-formed input that refers to something that doesn't exist (e.g. an unknown user id)."""

    status_code = 422


class TooManyRequestsError(AppError):
    """A quota or rate limit was hit. `retry_after` (seconds) becomes the Retry-After header."""

    status_code = 429

    def __init__(self, detail: str, retry_after: int | None = None) -> None:
        super().__init__(detail)
        self.retry_after = retry_after


class UpstreamError(AppError):
    """A third-party API (Unsplash, Giphy, an LLM provider) failed."""

    status_code = 502


class NotConfiguredError(AppError):
    """A feature's key isn't set (e.g. UNSPLASH_ACCESS_KEY)."""

    status_code = 503


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = None
        retry_after = getattr(exc, "retry_after", None)
        if retry_after is not None:
            headers = {"Retry-After": str(retry_after)}
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)
