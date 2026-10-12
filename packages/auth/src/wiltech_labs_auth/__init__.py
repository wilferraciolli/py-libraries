"""
wiltech-labs-auth: who is calling a Wiltech FastAPI app, and may they?

Clerk JWT verification, the Caller with the roles saved in the app's
database, require_admin / require_owner, service API keys for app-to-app
calls, and Clerk (Svix) webhook verification.

This module is the entire public surface — import from `wiltech_labs_auth`,
not from its sub-packages.
"""
from wiltech_labs_auth.api_keys import (
    API_KEY_HEADER,
    API_KEYS_TABLE_SQL,
    ApiKeyModel,
    ApiKeyRepository,
    ServiceCaller,
    generate_api_key,
    get_api_key_repository,
    hash_api_key,
    require_api_key,
)
from wiltech_labs_auth.authorization import (
    Caller,
    CallerLookup,
    SavedUser,
    UserDetailViewLookup,
    get_caller,
    get_caller_lookup,
    require_admin,
    require_owner,
)
from wiltech_labs_auth.clerk import AuthenticatedUser, get_authenticated_user
from wiltech_labs_auth.roles import ROLE_LABELS, UserRole, parse_role_ids, role_options
from wiltech_labs_auth.webhooks import WebhookVerificationError, clerk_webhook_event, verify_svix_signature

__all__ = [
    "API_KEYS_TABLE_SQL",
    "API_KEY_HEADER",
    "ApiKeyModel",
    "ApiKeyRepository",
    "AuthenticatedUser",
    "Caller",
    "CallerLookup",
    "ROLE_LABELS",
    "SavedUser",
    "ServiceCaller",
    "UserDetailViewLookup",
    "UserRole",
    "WebhookVerificationError",
    "clerk_webhook_event",
    "generate_api_key",
    "get_api_key_repository",
    "get_authenticated_user",
    "get_caller",
    "get_caller_lookup",
    "hash_api_key",
    "parse_role_ids",
    "require_admin",
    "require_api_key",
    "require_owner",
    "role_options",
    "verify_svix_signature",
]
