"""
wiltech-labs-rest: the response-building core shared by Wiltech's FastAPI apps.

This module is the entire public surface — import from `wiltech_labs_rest`,
not from its sub-packages.
"""
from wiltech_labs_rest.casing import CamelLinkedResource, CamelMetadataBase, CamelModel
from wiltech_labs_rest.links import Link, LinkedResource
from wiltech_labs_rest.metadata import (
    EmbeddedRef,
    FieldMetadata,
    MetadataBase,
    NoMetadata,
    choice_field,
    mandatory,
    read_only,
)
from wiltech_labs_rest.response import API_PREFIX, ApiResponse, Message, MessageType
from wiltech_labs_rest.serializers import (
    BlankAsNone,
    EmptyIfNone,
    Money,
    UtcDateTime,
    UtcTimestamp,
    as_utc,
    format_utc_datetime,
    money,
    to_db_date,
    to_db_datetime,
    utc_now,
)

__all__ = [
    "API_PREFIX",
    "ApiResponse",
    "BlankAsNone",
    "CamelLinkedResource",
    "CamelMetadataBase",
    "CamelModel",
    "EmbeddedRef",
    "EmptyIfNone",
    "FieldMetadata",
    "Link",
    "LinkedResource",
    "Message",
    "MessageType",
    "MetadataBase",
    "Money",
    "NoMetadata",
    "UtcDateTime",
    "UtcTimestamp",
    "as_utc",
    "choice_field",
    "format_utc_datetime",
    "mandatory",
    "money",
    "read_only",
    "to_db_date",
    "to_db_datetime",
    "utc_now",
]
