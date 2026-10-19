"""
wiltech-labs-core: the runtime plumbing shared by Wiltech's FastAPI apps.

Config that reads the Worker env or .env, the portable Database protocol
(SQLite / D1 binding / D1 over HTTP), the AppError family, per-request CORS
and a health router.

This module is the entire public surface — import from `wiltech_labs_core`,
not from its sub-packages.
"""
from wiltech_labs_core.config import get_binding, get_config, load_dotenv
from wiltech_labs_core.database import (
    D1BindingDatabase,
    D1HttpDatabase,
    Database,
    SQLiteDatabase,
    Statement,
    UniqueConstraintError,
    get_database,
    migrations_dir,
)
from wiltech_labs_core.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    NotConfiguredError,
    NotFoundError,
    TooManyRequestsError,
    UpstreamError,
    register_error_handlers,
)
from wiltech_labs_core.web import EnvCORSMiddleware, HealthCheck, allowed_origins, database_check, health_router

__all__ = [
    "AppError",
    "ConflictError",
    "D1BindingDatabase",
    "D1HttpDatabase",
    "Database",
    "EnvCORSMiddleware",
    "ForbiddenError",
    "HealthCheck",
    "InvalidInputError",
    "NotConfiguredError",
    "NotFoundError",
    "SQLiteDatabase",
    "Statement",
    "TooManyRequestsError",
    "UniqueConstraintError",
    "UpstreamError",
    "allowed_origins",
    "database_check",
    "get_binding",
    "get_config",
    "get_database",
    "health_router",
    "load_dotenv",
    "migrations_dir",
    "register_error_handlers",
]
