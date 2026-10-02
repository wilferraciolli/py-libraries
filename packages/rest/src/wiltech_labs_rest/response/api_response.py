from typing import Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from wiltech_labs_rest.links.link import Link
from wiltech_labs_rest.response.message import Message

# Must match the prefix the app mounts every router under, so hrefs built
# with it are actually followable rather than 404ing against the unprefixed path.
API_PREFIX = "/api"

DataT = TypeVar("DataT")
MetadataT = TypeVar("MetadataT")


class ApiResponse(BaseModel, Generic[DataT, MetadataT]):
    """
    The API's standard response envelope, typed per resource:
    `ApiResponse[UserSettingsDTO, UserSettingsMetadata]`.

    `_data` holds a single named entry, e.g. `{"userSettings": {...}}`.
    Build it with `ApiResponse.of(...)` rather than the constructor.
    """
    model_config = ConfigDict(populate_by_name=True)

    data: Dict[str, DataT] = Field(alias="_data")
    metadata: MetadataT = Field(alias="_metadata")
    meta_links: Dict[str, Link] = Field(default_factory=dict, alias="_metaLinks")
    messages: List[Message] = Field(default_factory=list, alias="_messages")

    @classmethod
    def of(
            cls,
            data_name: str,
            data: DataT,
            metadata: MetadataT,
            meta_links: Optional[Dict[str, Link]] = None,
            messages: Optional[List[Message]] = None,
    ) -> "ApiResponse[DataT, MetadataT]":
        return cls(
            data={data_name: data},
            metadata=metadata,
            meta_links=meta_links or {},
            messages=messages or [],
        )
