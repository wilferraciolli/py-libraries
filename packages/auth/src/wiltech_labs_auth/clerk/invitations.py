"""Inviting someone to sign up, through Clerk's Backend API (`POST /v1/invitations`).

Clerk emails them a sign-up link; once they sign up with that address, the app's own `/me` links
them as usual. Without a Clerk secret key nothing is sent: `ManualInviter` returns `None`, and the
app tells the person how to sign in some other way.
"""

from dataclasses import dataclass
from typing import Any, Optional, Protocol

import httpx
from starlette.requests import HTTPConnection

from wiltech_labs_core import get_config

CLERK_API_URL = "https://api.clerk.com/v1"


@dataclass(frozen=True)
class Invitation:
    id: str
    email: str
    status: str  # Clerk's: pending, accepted, revoked, expired


class InvitationError(RuntimeError):
    """Clerk refused the invitation, or couldn't be reached."""


class Inviter(Protocol):
    async def invite(
        self, email: str, redirect_url: Optional[str] = None, public_metadata: Optional[dict[str, Any]] = None
    ) -> Optional[Invitation]: ...


class ClerkInviter:
    """Sends Clerk invitations. An address with a pending invitation, or already signed up, is
    invited again rather than refused (`ignore_existing`)."""

    def __init__(self, secret_key: str, api_url: str = CLERK_API_URL,
                 transport: Optional[httpx.AsyncBaseTransport] = None, timeout: float = 10):
        self.secret_key = secret_key
        self.api_url = api_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout

    async def invite(
        self, email: str, redirect_url: Optional[str] = None, public_metadata: Optional[dict[str, Any]] = None
    ) -> Invitation:
        body: dict[str, Any] = {"email_address": email, "notify": True, "ignore_existing": True}
        if redirect_url:
            body["redirect_url"] = redirect_url
        if public_metadata:
            body["public_metadata"] = public_metadata
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/invitations", json=body,
                    headers={"Authorization": f"Bearer {self.secret_key}"},
                )
        except httpx.HTTPError as error:
            raise InvitationError(f"Couldn't reach Clerk: {error}") from error
        if response.status_code >= 400:
            raise InvitationError(_clerk_message(response))
        data = response.json()
        return Invitation(id=data["id"], email=data.get("email_address", email), status=data.get("status", "pending"))


class ManualInviter:
    """No Clerk secret key: nothing is sent."""

    async def invite(
        self, email: str, redirect_url: Optional[str] = None, public_metadata: Optional[dict[str, Any]] = None
    ) -> None:
        return None


def _clerk_message(response: httpx.Response) -> str:
    try:
        errors = response.json().get("errors") or []
    except ValueError:
        errors = []
    if errors:
        first = errors[0]
        return str(first.get("long_message") or first.get("message") or first.get("code"))
    return f"Clerk answered {response.status_code}"


def get_inviter(request: HTTPConnection) -> Inviter:
    """FastAPI dependency: Clerk when `CLERK_SECRET_KEY` is set, else nothing is sent."""
    secret = get_config(request, "CLERK_SECRET_KEY")
    return ClerkInviter(secret) if secret else ManualInviter()
