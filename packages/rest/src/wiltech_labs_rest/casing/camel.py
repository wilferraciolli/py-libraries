from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from wiltech_labs_rest.links.link import LinkedResource
from wiltech_labs_rest.metadata.field_metadata import MetadataBase


class CamelModel(BaseModel):
    """
    Base for a Request, DTO or Metadata class whose Python attributes are
    snake_case but whose JSON is camelCase (`bed_number` <-> `bedNumber`).

    Requests accept either spelling. A service that turns a Request into a
    row model must dump it with `by_alias=False` to get the snake_case names.
    Apps that already name their fields in camelCase don't need this.
    """
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True)


class CamelLinkedResource(LinkedResource, CamelModel):
    """`LinkedResource` (adds `links`) serialized camelCase: the base for a camelCase DTO."""


class CamelMetadataBase(MetadataBase, CamelModel):
    """`MetadataBase` serialized camelCase: one camelCase key per field with a rule."""
