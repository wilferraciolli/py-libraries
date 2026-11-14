# wiltech-labs-organization

An organisation's structure for Wiltech FastAPI apps: the org chart's items in the shape
[`@wiltech-labs/ngx-organization`](https://www.npmjs.com/package/@wiltech-labs/ngx-organization)
draws, and the rules for where each part of the structure may sit. Apps keep the structure in
their own tables; this package says what's allowed and how to send it.

```bash
uv add wiltech-labs-organization
```

## The structure

```text
ORG                                   one, at the top
├── ORG_ENTITY                        under the ORG or a DEPARTMENT; never inside another ORG_ENTITY
│   └── DEPARTMENT                    under the ORG, an ORG_ENTITY or a DEPARTMENT, to any depth
│       ├── DEPARTMENT …
│       └── JOB                       under a DEPARTMENT only
│             occupancies: person A 2026-03-01 → 2026-08-31, person B 2026-09-01 → (open)
└── DEPARTMENT
    └── ORG_ENTITY                    allowed: no ORG_ENTITY above it
```

- **One `ORG`** at the top, with no parent.
- **`ORG_ENTITY`** (a company or other part of the group) sits under the `ORG` or under a
  `DEPARTMENT`. Once a line from the top has passed an `ORG_ENTITY`, no other `ORG_ENTITY` can
  appear below it: at most one on any line.
- **`DEPARTMENT`** sits under the `ORG`, an `ORG_ENTITY` or another `DEPARTMENT`, with no limit on
  depth. A department may name one of its jobs as its reporting job (`reporting_job_id`): whoever
  holds it heads the department.
- **`JOB`** sits under a `DEPARTMENT`, never under the `ORG` or an `ORG_ENTITY`.
- **People are not nodes.** A person holding a job for a time is an `OrgOccupancy` (who, from,
  until) carried on the job. A person can hold several jobs; whether a job can have more than one
  holder at a time is the app's rule (`OrgOccupancy.overlaps` helps enforce one at a time).

## Checking a change

Load every node's id, type and parent (any object with `id`, `type`, `parent_id`: an `OrgNode`,
an `OrgNodeRef` or the app's own row) and ask before saving:

```python
from wiltech_labs_organization import OrgNodeRef, OrgNodeType, OrgStructure, OrgStructureError

structure = OrgStructure([
    OrgNodeRef(org.id, OrgNodeType.ORG),
    *(OrgNodeRef(e.id, OrgNodeType.ORG_ENTITY, e.parent_id or org.id) for e in entities),
    *(OrgNodeRef(d.id, OrgNodeType.DEPARTMENT, d.parent_id or org.id) for d in departments),
])

try:
    structure.check_add(OrgNodeType.ORG_ENTITY, parent_id=department_id)  # a new node
    structure.check_move(department_id, parent_id=entity_id)              # a node and its branch
except OrgStructureError as error:
    raise ConflictError(error.code, str(error))  # or answer in the app's own words, by error.code
```

| Error                 | `code`              | When                                                           |
| --------------------- | ------------------- | -------------------------------------------------------------- |
| `InvalidParentError`  | `INVALID_PARENT`    | A type under a parent it may not sit under (a job under an entity) |
| `NestedEntityError`   | `NESTED_ORG_ENTITY` | An entity inside another entity, directly or further down; moving a branch that holds an entity into one |
| `OrgCycleError`       | `ORG_CYCLE`         | A node moved under itself or under something below it          |
| `OrgRootError`        | `ORG_ROOT`          | A second `ORG`, an `ORG` with a parent, or none at the top     |
| `UnknownOrgNodeError` | `UNKNOWN_ORG_NODE`  | A parent or node that isn't in the structure                   |

All are `OrgStructureError`, a `ValueError`. `structure.problems()` lists every broken rule in a
whole structure (for tests and integrity checks); `structure.check()` raises the first.

## Sending the org chart

`GET /org-chart` answers `_data.orgNodes`: a flat list of `OrgNode`, each pointing at its parent,
camelCase JSON (`parentId`, `reportingJobId`, `occupancies[].personId`, `startDate`, `endDate`).

```python
from wiltech_labs_organization import ORG_NODES_DATA_NAME, OrgChartResponse, OrgNode, org_chart_nodes
from wiltech_labs_rest import NoMetadata

nodes = [OrgNode(id=org.id, type="ORG", name=org.name), ...]          # every node, with its links
items = org_chart_nodes(nodes, occupancies_by_job_id, as_of=today)   # who holds each job today
return OrgChartResponse.of(ORG_NODES_DATA_NAME, items, NoMetadata())
```

`org_chart_nodes` attaches each job's occupancies (only those covering `as_of`, when given),
earliest first; jobs nobody holds get `[]`.

## Public API

| Name                       | What                                                                  |
| -------------------------- | --------------------------------------------------------------------- |
| `OrgNodeType`              | `ORG`, `ORG_ENTITY`, `DEPARTMENT`, `JOB`                              |
| `OrgNode`                  | One node (camelCase DTO with `links`)                                 |
| `OrgOccupancy`             | A person in a job from `start_date` to `end_date`; `covers`, `overlaps` |
| `OrgChartResponse`         | `ApiResponse[list[OrgNode], NoMetadata]`                              |
| `ORG_NODES_DATA_NAME`      | `"orgNodes"`                                                          |
| `org_chart_nodes`          | Attaches occupancies to jobs for the chart                            |
| `OrgStructure`             | `check_add`, `check_move`, `problems`, `check`, `ancestors`, `descendants`, `root` |
| `OrgNodeRef`               | A node as the rules see it: `id`, `type`, `parent_id`                 |
| `ALLOWED_PARENTS`          | Each type's allowed parent types                                      |
| `OrgStructureError` and subclasses | See the table above                                           |

## Publishing

Released to [TestPyPI](https://test.pypi.org/project/wiltech-labs-organization/) (rehearsal) and
[PyPI](https://pypi.org/project/wiltech-labs-organization/) (what apps install from). Account
setup, checking a TestPyPI release and fixing errors are covered in
[`docs/PUBLISHING.md`](https://github.com/wilferraciolli/py-libraries/blob/main/docs/PUBLISHING.md).
`wiltech-labs-rest` (>= 1.0.1) must be on PyPI first.

```bash
cd packages/organization

# 1. Test, bump, build
uv run pytest
uv version --bump patch                 # skip for the first 1.0.0
rm -rf ../../dist && uv build           # -> ../../dist/

# 2. TestPyPI (optional rehearsal), using a token from test.pypi.org
read -rsp "TestPyPI token: " UV_PUBLISH_TOKEN && export UV_PUBLISH_TOKEN && echo
uv publish --index testpypi ../../dist/*
unset UV_PUBLISH_TOKEN

# 3. PyPI (the real thing), using a token from pypi.org
read -rsp "PyPI token: " UV_PUBLISH_TOKEN && export UV_PUBLISH_TOKEN && echo
uv publish ../../dist/*
unset UV_PUBLISH_TOKEN

# 4. Commit and tag
git commit -am "wiltech-labs-organization <version>"
git tag organization-v<version> && git push && git push --tags
```
