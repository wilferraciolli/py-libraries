import os
from pathlib import Path
from typing import Optional

from starlette.requests import HTTPConnection


def load_dotenv(path: Optional[Path] = None) -> None:
    """
    Load the project's .env (in the working directory) for plain uvicorn/local runs, if one exists.

    Values already in the environment win, so docker-compose `environment:`
    entries override the file. Runs once on import; call it again only to load
    a different file.
    """
    env_path = path or Path.cwd() / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()


def get_config(request: HTTPConnection, key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Read config from either the Worker env object or process environment.

    Cloudflare injects bindings/config into request.scope["env"], while plain
    uvicorn/Docker uses environment variables loaded from .env/docker-compose.
    """
    env = request.scope.get("env")
    if env is not None:
        try:
            value = getattr(env, key)
            if value is not None:
                return str(value)
        except AttributeError:
            pass

    return os.environ.get(key, default)


def get_binding(request: HTTPConnection, name: str) -> Optional[object]:
    """
    A Cloudflare binding (env.DB, env.AI, env.BUCKET, ...) or None outside a
    Worker. Adapter factories use this to prefer the native binding when it
    exists and fall back to HTTP otherwise.
    """
    env = request.scope.get("env")
    if env is None:
        return None
    return getattr(env, name, None)
