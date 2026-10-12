import asyncio
import logging
from dataclasses import dataclass
from time import monotonic
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWK

from wiltech_labs_core import get_config

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_jwks_lock = asyncio.Lock()
_JWKS_CACHE_SECONDS = 3600


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    name: str
    email: str | None
    role_ids: list[str]
    claims: dict[str, Any]


def _unauthorized(detail: str = "Invalid or expired authentication token") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _get_jwks(jwks_url: str, force_refresh: bool = False) -> dict[str, Any]:
    cached = _jwks_cache.get(jwks_url)
    if not force_refresh and cached and cached[0] > monotonic():
        return cached[1]

    async with _jwks_lock:
        cached = _jwks_cache.get(jwks_url)
        if not force_refresh and cached and cached[0] > monotonic():
            return cached[1]

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(jwks_url)
            response.raise_for_status()

        jwks = response.json()
        if not isinstance(jwks.get("keys"), list):
            raise RuntimeError("Clerk JWKS response does not contain a keys list")

        _jwks_cache[jwks_url] = (monotonic() + _JWKS_CACHE_SECONDS, jwks)
        return jwks


def _find_signing_key(jwks: dict[str, Any], key_id: str) -> Any | None:
    for key in jwks["keys"]:
        if key.get("kid") == key_id and key.get("use") == "sig":
            return PyJWK.from_dict(key).key

    return None


def _normalise_role_ids(claims: dict[str, Any]) -> list[str]:
    value = claims.get("roleIds", claims.get("roles"))
    if not isinstance(value, list):
        return ["STANDARD"]

    roles = [str(role) for role in value if role]
    return list(dict.fromkeys(roles)) or ["STANDARD"]


async def get_authenticated_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser:
    """
    Route dependency: the Clerk user behind the `Authorization: Bearer` token.

    401 for a missing, malformed, expired or wrongly signed token; 503 if
    Clerk's JWKS can't be fetched. Needs CLERK_JWKS_URL and CLERK_AUDIENCE;
    CLERK_AUTHORIZED_PARTIES (comma-separated `azp` values) is optional.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Bearer token required")

    jwks_url = get_config(request, "CLERK_JWKS_URL")
    audience = get_config(request, "CLERK_AUDIENCE", "wiltech-dev-api")
    if not jwks_url or not audience:
        raise RuntimeError("CLERK_JWKS_URL and CLERK_AUDIENCE must be configured")

    issuer = jwks_url.removesuffix("/.well-known/jwks.json")

    try:
        header = jwt.get_unverified_header(credentials.credentials)
        key_id = header.get("kid")
        if not key_id or header.get("alg") != "RS256":
            raise _unauthorized()

        jwks = await _get_jwks(jwks_url)
        signing_key = _find_signing_key(jwks, key_id)
        if signing_key is None:
            jwks = await _get_jwks(jwks_url, force_refresh=True)
            signing_key = _find_signing_key(jwks, key_id)
        if signing_key is None:
            raise _unauthorized()

        claims = jwt.decode(
            credentials.credentials,
            signing_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except HTTPException:
        raise
    except (InvalidTokenError, ValueError, TypeError) as exc:
        raise _unauthorized() from exc
    except httpx.HTTPError as exc:
        logger.warning("could not reach Clerk JWKS at %r: %r", jwks_url, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    authorized_parties = get_config(request, "CLERK_AUTHORIZED_PARTIES")
    if authorized_parties:
        allowed = {
            party.strip()
            for party in authorized_parties.split(",")
            if party.strip()
        }
        if claims.get("azp") not in allowed:
            raise _unauthorized()

    name = claims.get("name") or claims.get("fullName") or claims["sub"]
    email = claims.get("email") or claims.get("emailAddress")

    return AuthenticatedUser(
        id=claims["sub"],
        name=str(name),
        email=str(email) if email else None,
        role_ids=_normalise_role_ids(claims),
        claims=claims,
    )
