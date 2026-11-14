# wiltech-labs-organization

An organisation's structure: org chart items and the rules for where each node may sit. See root
`../../CLAUDE.md` for repo-wide conventions.

New code (2026-11-15), not ported from an app: asked for while building Crewly's org chart, as the
API-side counterpart of `@wiltech-labs/ngx-organization` (the way `wiltech-labs-holidays` is
`ngx-calendar`'s). Any Wiltech app with departments and jobs needs the same rules.

## The rules (from the user, 2026-11-15)

- An organisation is at the top. Under it: departments or org entities.
- Departments go down from there with no limit on depth.
- Once a line has an org entity, there can't be another org entity within it (an entity may sit
  under a department, as long as no entity is above it).
- Jobs only ever sit under a department, never under the organisation or an org entity.
- A job may be occupied by a person for a date range. People and occupancies are not
  organisation nodes: an occupancy is just a person holding a job for a given time.

## Decisions

- **No storage.** Apps keep their own tables (Crewly: `departments`, `legal_entities`, `jobs`,
  `job_assignments`) and load an `OrgStructure` (id, type, parent) to check a change. The rules
  live in one place; the SQL stays the app's.
- **Explicit parents.** A top-level node's `parent_id` is the `ORG`'s id, never None: apps whose
  tables store "under the organisation" as NULL map it when they build the structure.
- **Occupancies travel on their job** (`OrgNode.occupancies`), not as items of the list. This
  changed ngx-organization's contract in 1.0.1 (1.0.0 sent `OCCUPANCY` items in `orgNodes`).
- **camelCase JSON** (`CamelLinkedResource`), because the item shape is ngx-organization's
  `OrgItem`. Field names are a contract: add fields freely; don't rename.
- **Errors are plain `ValueError`s with a `code`**, so the package doesn't need
  `wiltech-labs-core`; apps map them to their own `AppError` (409) in their own words.
- **One holder at a time is the app's rule**, not this package's: Crewly refuses overlapping
  assignments on a job, but job shares exist elsewhere. `OrgOccupancy.overlaps` helps.
- Version `1.0.0` for the first release.
