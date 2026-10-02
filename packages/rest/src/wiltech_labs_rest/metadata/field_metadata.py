from enum import Enum
from typing import Optional, Type

from pydantic import BaseModel, SerializerFunctionWrapHandler, model_serializer


class EmbeddedRef(BaseModel):
    """
    An embedded reference to another resource — `id` plus its display
    `value` — so a client can render a human-readable name without a
    second round trip to look it up. Same `id`/`value` shape the API
    already uses for metadata option lists.
    """
    id: str
    value: str


class FieldMetadata(BaseModel):
    """
    Describes how a client should treat one field of a resource: whether it
    is read-only, hidden or mandatory, the allowed `values` for a choice
    field, and size limits (`maxLength` for text, `maxItems` for lists,
    `min`/`max`/`default` for numbers). Unset flags are omitted from the
    response.
    """
    readOnly: Optional[bool] = None
    hidden: Optional[bool] = None
    mandatory: Optional[bool] = None
    maxLength: Optional[int] = None
    maxItems: Optional[int] = None
    min: Optional[int] = None
    max: Optional[int] = None
    default: Optional[int] = None
    values: Optional[list[EmbeddedRef]] = None

    @model_serializer(mode="wrap")
    def _omit_unset_flags(self, handler: SerializerFunctionWrapHandler):
        return {key: value for key, value in handler(self).items() if value is not None}


class NoMetadata(BaseModel):
    """`_metadata` for a response whose fields have no client rules: `{}`."""


def choice_field(enum_type: Type[Enum]) -> FieldMetadata:
    """A mandatory field whose allowed `values` are every member of `enum_type`."""
    return FieldMetadata(
        mandatory=True,
        values=[EmbeddedRef(id=member.value, value=member.value) for member in enum_type],
    )
