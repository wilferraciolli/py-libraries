import base64
import hashlib
import hmac
import json
import time
from typing import Any, Mapping, Optional

from fastapi import HTTPException, Request, status

from wiltech_labs_core import get_config

# Reject deliveries whose timestamp is further than this from now (replay protection).
TOLERANCE_SECONDS = 5 * 60


class WebhookVerificationError(Exception):
    pass


def verify_svix_signature(
    secret: str,
    headers: Mapping[str, str],
    body: bytes,
    now: Optional[float] = None,
    tolerance: int = TOLERANCE_SECONDS,
) -> None:
    """
    Check a Svix-signed webhook (what Clerk sends). Raises
    WebhookVerificationError unless one of the `svix-signature` values is the
    HMAC-SHA256 of "{svix-id}.{svix-timestamp}.{body}" under the endpoint's
    `whsec_...` secret, and the timestamp is recent.

    `body` must be the raw bytes as received: re-serialised JSON won't match.
    """
    msg_id = headers.get("svix-id")
    timestamp = headers.get("svix-timestamp")
    signatures = headers.get("svix-signature")
    if not msg_id or not timestamp or not signatures:
        raise WebhookVerificationError("missing svix headers")

    try:
        sent_at = int(timestamp)
    except ValueError as exc:
        raise WebhookVerificationError("invalid svix-timestamp") from exc
    if abs((now if now is not None else time.time()) - sent_at) > tolerance:
        raise WebhookVerificationError("timestamp outside the allowed window")

    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{msg_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()

    # Space-separated "v1,<base64>" entries: several while a secret is being rotated.
    for entry in signatures.split():
        version, _, signature = entry.partition(",")
        if version == "v1" and hmac.compare_digest(signature, expected):
            return

    raise WebhookVerificationError("no matching signature")


async def clerk_webhook_event(request: Request) -> dict[str, Any]:
    """
    Route dependency for a Clerk webhook endpoint: the verified event
    (`{"type": "user.deleted", "data": {...}}`). 400 if the signature is bad,
    503 if CLERK_WEBHOOK_SECRET isn't set.

        @router.post("/webhooks/clerk")
        async def clerk(event: dict = Depends(clerk_webhook_event)): ...
    """
    secret = get_config(request, "CLERK_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="CLERK_WEBHOOK_SECRET isn't set")

    body = await request.body()
    try:
        verify_svix_signature(secret, request.headers, body)
    except WebhookVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature") from exc

    return json.loads(body)
