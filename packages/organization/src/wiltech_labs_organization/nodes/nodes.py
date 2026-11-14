"""The org chart's items: the flat list `@wiltech-labs/ngx-organization` draws, as the API sends it.

Four node types make the tree (`OrgNodeType`). A person holding a job is not a node: an
`OrgOccupancy` (who, from when, until when) travels on the job it fills.
"""

from datetime import date
from enum import StrEnum
from typing import Iterable, Mapping, Optional

from wiltech_labs_rest import ApiResponse, CamelLinkedResource, NoMetadata

# The `_data` name of the org chart response, which ngx-organization's `OrgChartStore` reads.
ORG_NODES_DATA_NAME = "orgNodes"


class OrgNodeType(StrEnum):
    """What a node is. `OrgStructure` holds the rules for where each one may sit."""

    ORG = "ORG"
    ORG_ENTITY = "ORG_ENTITY"
    DEPARTMENT = "DEPARTMENT"
    JOB = "JOB"


class OrgOccupancy(CamelLinkedResource):
    """A person holding a job from `start_date` to `end_date`, both included (no `end_date`: still
    holding it). Not a node of the structure: the job carries it in `occupancies`.

    `person_id` is the same across every job the person holds."""

    id: str
    person_id: str
    name: str
    start_date: date
    end_date: Optional[date] = None

    def covers(self, day: date) -> bool:
        """Whether the person holds the job on `day`."""
        return self.start_date <= day and (self.end_date is None or day <= self.end_date)

    def overlaps(self, start_date: date, end_date: Optional[date]) -> bool:
        """Whether this occupancy shares at least one day with `start_date`–`end_date` (no
        `end_date`: open-ended). Apps that allow one person per job at a time refuse a new
        occupancy that overlaps an existing one."""
        return (end_date is None or self.start_date <= end_date) and (
            self.end_date is None or start_date <= self.end_date
        )


class OrgNode(CamelLinkedResource):
    """One node of the structure, pointing at its parent (`parent_id`, None only for the `ORG`).

    - `reporting_job_id`: `DEPARTMENT` only, the `JOB` that heads it (its manager), if any. The
      chart draws the two as one card.
    - `occupancies`: `JOB` only, who holds it, earliest first. None on the other types.
    - `links`: the actions the API allows on this node.

    JSON is camelCase (`parentId`, `reportingJobId`, `personId`, `startDate`), the names
    ngx-organization reads."""

    id: str
    type: OrgNodeType
    name: str
    parent_id: Optional[str] = None
    description: Optional[str] = None
    reporting_job_id: Optional[str] = None
    occupancies: Optional[list[OrgOccupancy]] = None


OrgChartResponse = ApiResponse[list[OrgNode], NoMetadata]


def org_chart_nodes(
        nodes: Iterable[OrgNode],
        occupancies: Mapping[str, Iterable[OrgOccupancy]],
        *,
        as_of: Optional[date] = None,
) -> list[OrgNode]:
    """`nodes` with each job's occupancies attached (`occupancies` maps a job's id to its own),
    earliest first. With `as_of`, only the occupancies covering that day: who holds each job on
    the chart's date. Jobs nobody holds get an empty list; other nodes keep `occupancies=None`.
    The nodes come back in the order given."""
    result: list[OrgNode] = []
    for node in nodes:
        if node.type != OrgNodeType.JOB:
            result.append(node.model_copy(update={"occupancies": None}))
            continue
        held = [o for o in occupancies.get(node.id, ()) if as_of is None or o.covers(as_of)]
        held.sort(key=lambda o: (o.start_date, o.name))
        result.append(node.model_copy(update={"occupancies": held}))
    return result
