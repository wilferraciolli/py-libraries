"""
wiltech-labs-rest: the response-building core shared by Wiltech's FastAPI apps.

This module is the entire public surface — import from `wiltech_labs_rest`,
not from its sub-packages.
"""
from wiltech_labs_rest.links import Link, LinkedResource
from wiltech_labs_rest.metadata import EmbeddedRef, FieldMetadata, NoMetadata, choice_field
from wiltech_labs_rest.response import API_PREFIX, ApiResponse, Message, MessageType
from wiltech_labs_rest.serializers import UtcDateTime, as_utc, format_utc_datetime

__all__ = [
    "API_PREFIX",
    "ApiResponse",
    "EmbeddedRef",
    "FieldMetadata",
    "Link",
    "LinkedResource",
    "Message",
    "MessageType",
    "NoMetadata",
    "UtcDateTime",
    "as_utc",
    "choice_field",
    "format_utc_datetime",
]
