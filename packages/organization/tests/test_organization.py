from datetime import date

import pytest

from wiltech_labs_organization import (
    ORG_NODES_DATA_NAME,
    InvalidParentError,
    NestedEntityError,
    OrgChartResponse,
    OrgCycleError,
    OrgNode,
    OrgNodeRef,
    OrgNodeType,
    OrgOccupancy,
    OrgRootError,
    OrgStructure,
    UnknownOrgNodeError,
    org_chart_nodes,
)
from wiltech_labs_rest import NoMetadata

ORG, ENTITY, DEPARTMENT, JOB = OrgNodeType.ORG, OrgNodeType.ORG_ENTITY, OrgNodeType.DEPARTMENT, OrgNodeType.JOB


def structure() -> OrgStructure:
    """org ─┬─ hotels (entity) ── front (department) ── reception (department) ── receptionist (job)
            └─ group (department) ── finance (department)"""
    return OrgStructure([
        OrgNodeRef("org", ORG),
        OrgNodeRef("hotels", ENTITY, "org"),
        OrgNodeRef("front", DEPARTMENT, "hotels"),
        OrgNodeRef("reception", DEPARTMENT, "front"),
        OrgNodeRef("receptionist", JOB, "reception"),
        OrgNodeRef("group", DEPARTMENT, "org"),
        OrgNodeRef("finance", DEPARTMENT, "group"),
    ])


# Adding


@pytest.mark.parametrize("node_type, parent", [
    (ENTITY, "org"), (ENTITY, "group"), (ENTITY, "finance"),
    (DEPARTMENT, "org"), (DEPARTMENT, "hotels"), (DEPARTMENT, "reception"),
    (JOB, "front"), (JOB, "finance"),
])
def test_allowed_places(node_type, parent):
    structure().check_add(node_type, parent)


@pytest.mark.parametrize("parent", ["org", "hotels", "receptionist"])
def test_a_job_sits_under_a_department_only(parent):
    with pytest.raises(InvalidParentError, match="only sit under a department"):
        structure().check_add(JOB, parent)


@pytest.mark.parametrize("parent", ["hotels", "front", "reception"])
def test_no_entity_inside_an_entity_at_any_depth(parent):
    with pytest.raises(NestedEntityError):
        structure().check_add(ENTITY, parent)


def test_nothing_sits_under_a_job():
    with pytest.raises(InvalidParentError):
        structure().check_add(DEPARTMENT, "receptionist")


def test_one_organisation_at_the_top():
    with pytest.raises(OrgRootError):
        structure().check_add(ORG, None)
    with pytest.raises(OrgRootError):
        OrgStructure([]).check_add(ORG, "somewhere")
    OrgStructure([]).check_add(ORG, None)


def test_unknown_parent():
    with pytest.raises(UnknownOrgNodeError):
        structure().check_add(DEPARTMENT, "nowhere")


# Moving


def test_a_department_moves_anywhere_a_department_may_sit():
    structure().check_move("finance", "front")
    structure().check_move("group", "hotels")


def test_moving_takes_the_branch_along():
    s = OrgStructure([
        OrgNodeRef("org", ORG),
        OrgNodeRef("hotels", ENTITY, "org"),
        OrgNodeRef("group", DEPARTMENT, "org"),
        OrgNodeRef("travel", ENTITY, "group"),
    ])
    # "group" holds an entity, so it can't go inside "hotels" even though departments may.
    with pytest.raises(NestedEntityError):
        s.check_move("group", "hotels")
    s.check_move("travel", "org")


def test_no_cycles():
    with pytest.raises(OrgCycleError):
        structure().check_move("front", "reception")
    with pytest.raises(OrgCycleError):
        structure().check_move("front", "front")


def test_an_entity_moves_under_a_department_outside_any_entity():
    structure().check_move("hotels", "finance")
    with pytest.raises(NestedEntityError):
        OrgStructure([
            OrgNodeRef("org", ORG),
            OrgNodeRef("a", ENTITY, "org"),
            OrgNodeRef("d", DEPARTMENT, "a"),
            OrgNodeRef("b", ENTITY, "org"),
        ]).check_move("b", "d")


def test_a_job_moves_between_departments_only():
    structure().check_move("receptionist", "finance")
    with pytest.raises(InvalidParentError):
        structure().check_move("receptionist", "hotels")


def test_the_organisation_never_moves():
    with pytest.raises(OrgRootError):
        structure().check_move("org", "group")


# The whole structure


def test_a_valid_structure_has_no_problems():
    assert structure().problems() == []
    structure().check()


def test_problems_lists_every_broken_rule():
    s = OrgStructure([
        OrgNodeRef("org", ORG),
        OrgNodeRef("a", ENTITY, "org"),
        OrgNodeRef("b", ENTITY, "a"),
        OrgNodeRef("j", JOB, "org"),
        OrgNodeRef("x", DEPARTMENT, "y"),
        OrgNodeRef("y", DEPARTMENT, "x"),
        OrgNodeRef("self", DEPARTMENT, "self"),
        OrgNodeRef("lost", DEPARTMENT, "gone"),
    ])
    kinds = sorted(type(problem).__name__ for problem in s.problems())
    assert kinds == [
        "InvalidParentError",   # b (an entity under an entity)
        "InvalidParentError",   # j (a job under the org)
        "NestedEntityError",    # b
        "OrgCycleError",        # x
        "OrgCycleError",        # y
        "OrgCycleError",        # self
        "UnknownOrgNodeError",  # lost
    ]
    with pytest.raises(OrgRootError):
        OrgStructure([OrgNodeRef("d", DEPARTMENT, None)]).check()


def test_ancestors_and_descendants():
    s = structure()
    assert [ref.id for ref in s.ancestors("receptionist")] == ["reception", "front", "hotels", "org"]
    assert {ref.id for ref in s.descendants("hotels")} == {"front", "reception", "receptionist"}
    assert s.root == OrgNodeRef("org", ORG)


def test_reads_any_node_with_an_id_type_and_parent():
    nodes = [OrgNode(id="org", type=ORG, name="Harbour"), OrgNode(id="d", type="DEPARTMENT", name="Bar", parent_id="org")]
    OrgStructure(nodes).check()


# Occupancies and the chart's items


def occupancy(start: date, end: date | None = None, name: str = "Eleni Georgiou") -> OrgOccupancy:
    return OrgOccupancy(id=f"a-{start}", person_id="p1", name=name, start_date=start, end_date=end)


def test_an_occupancy_covers_its_days_inclusive():
    held = occupancy(date(2026, 3, 1), date(2026, 3, 31))
    assert held.covers(date(2026, 3, 1)) and held.covers(date(2026, 3, 31))
    assert not held.covers(date(2026, 4, 1))
    assert occupancy(date(2026, 3, 1)).covers(date(2030, 1, 1))


def test_overlaps():
    held = occupancy(date(2026, 3, 1), date(2026, 3, 31))
    assert held.overlaps(date(2026, 3, 31), None)
    assert not held.overlaps(date(2026, 4, 1), None)
    assert occupancy(date(2026, 3, 1)).overlaps(date(2020, 1, 1), date(2026, 3, 1))
    assert not occupancy(date(2026, 3, 1)).overlaps(date(2020, 1, 1), date(2026, 2, 28))


def test_org_chart_nodes_attach_each_jobs_occupancies():
    nodes = [
        OrgNode(id="org", type=ORG, name="Harbour"),
        OrgNode(id="front", type=DEPARTMENT, name="Front office", parent_id="org", reporting_job_id="manager"),
        OrgNode(id="manager", type=JOB, name="Front office manager", parent_id="front"),
        OrgNode(id="night", type=JOB, name="Night auditor", parent_id="front"),
    ]
    past, current = occupancy(date(2025, 1, 1), date(2025, 12, 31), "Andreas"), occupancy(date(2026, 1, 1))
    items = org_chart_nodes(nodes, {"manager": [current, past]}, as_of=date(2026, 11, 15))
    assert [item.occupancies for item in items] == [None, None, [current], []]
    assert org_chart_nodes(nodes, {"manager": [current, past]})[2].occupancies == [past, current]


def test_the_json_is_the_shape_ngx_organization_reads():
    node = OrgNode(
        id="manager", type=JOB, name="Front office manager", parent_id="front",
        occupancies=[occupancy(date(2026, 1, 1))],
    )
    body = OrgChartResponse.of(ORG_NODES_DATA_NAME, [node], NoMetadata()).model_dump(mode="json", by_alias=True)
    item = body["_data"]["orgNodes"][0]
    assert item["type"] == "JOB" and item["parentId"] == "front"
    assert item["occupancies"][0] == {
        "id": "a-2026-01-01", "personId": "p1", "name": "Eleni Georgiou", "startDate": "2026-01-01",
        "endDate": None, "links": {},
    }
