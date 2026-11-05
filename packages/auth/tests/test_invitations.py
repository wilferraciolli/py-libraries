import json

import httpx
import pytest

from wiltech_labs_auth import ClerkInviter, InvitationError, ManualInviter

async def test_clerk_is_asked_to_email_a_sign_up_link():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "inv_1", "email_address": "nina@example.com", "status": "pending"})

    inviter = ClerkInviter("sk_test_1", transport=httpx.MockTransport(handler))
    invitation = await inviter.invite("nina@example.com", redirect_url="https://app.example.com/onboarding")

    assert (invitation.id, invitation.email, invitation.status) == ("inv_1", "nina@example.com", "pending")
    assert seen["url"] == "https://api.clerk.com/v1/invitations"
    assert seen["auth"] == "Bearer sk_test_1"
    assert seen["body"] == {
        "email_address": "nina@example.com", "notify": True, "ignore_existing": True,
        "redirect_url": "https://app.example.com/onboarding",
    }


async def test_clerk_s_refusal_comes_back_in_its_own_words():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"errors": [{"code": "form_param_format_invalid",
                                                     "long_message": "email_address must be a valid email address."}]})

    with pytest.raises(InvitationError, match="must be a valid email address"):
        await ClerkInviter("sk_test_1", transport=httpx.MockTransport(handler)).invite("not-an-email")


async def test_without_a_secret_key_nothing_is_sent():
    assert await ManualInviter().invite("nina@example.com") is None
