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
    is read-only, hidden or mandatory, and the allowed `values` for a
    choice field. Unset flags are omitted from the response.
    """
    readOnly: Optional[bool] = None
    hidden: Optional[bool] = None
    mandatory: Optional[bool] = None
    values: Optional[list[EmbeddedRef]] = None

    @model_serializer(mode="wrap")
    def _omit_unset_flags(self, handler: SerializerFunctionWrapHandler):
        return {key: value for key, value in handler(self).items() if value is not None}


def choice_field(enum_type: Type[Enum]) -> FieldMetadata:
    """A mandatory field whose allowed `values` are every member of `enum_type`."""
    return FieldMetadata(
        mandatory=True,
        values=[EmbeddedRef(id=member.value, value=member.value) for member in enum_type],
    )
