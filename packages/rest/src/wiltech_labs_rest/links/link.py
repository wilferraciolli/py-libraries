from typing import Dict

from pydantic import BaseModel, Field


# Shared HATEOAS-style link, reused by any response DTO
class Link(BaseModel):
    """A single navigation link describing a related action on a resource."""
    href: str
    method: str = "GET"


class LinkedResource(BaseModel):
    """
    Base class adding a `links` map to any response DTO.

    Any model that inherits this gets a `links: Dict[str, Link]` field for free,
    so the same Link shape/behavior is shared across every resource - no
    copy-pasting the field definition each time.
    """
    links: Dict[str, Link] = Field(default_factory=dict)
