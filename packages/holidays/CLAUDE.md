# wiltech-labs-holidays

Public holidays in the shape the Wiltech UI shows. See root `../../CLAUDE.md` for repo-wide
conventions.

New code (2026-10-23), not ported from an app: asked for while building Crewly's leave module
(04·4d, public holidays out of leave day counts), on the reasoning that any Wiltech app with a
calendar or working days needs it. The counterpart is `@wiltech-labs/ngx-calendar` 1.0.3's
`holidays` input, which takes these items as the API sends them.

## Decisions

- **The `holidays` package does the dates**, not our own algorithms: ~150 countries, Orthodox and
  Western Easter, observed-day rules, names in several languages, MIT, pure Python (one dependency,
  `python-dateutil`). Checked against Crewly's Cyprus requirements register (CY-16): Green Monday,
  Good Friday, Easter Monday and Kataklysmos (Pentecost Monday) land right for 2026–2027, and the
  register's optional days are there too: Easter Tuesday is `bank`, Holy Saturday and 24 December
  are `optional`.
- **What this package adds**: locale resolution (`el-CY` → country, subdivision, the best supported
  language), one item per holiday with its category (the `holidays` package merges a day's names
  and drops the category when several categories are asked for at once, so each category is
  fetched on its own and tagged), and the router.
- **The item shape is a contract**: `date`, `name`, `category`, `country`, `subdivision`, plain
  JSON. ngx-calendar reads `date`, `name` and `category`. Add fields freely; don't rename these.
- **Apps own entitlement.** Whether a holiday is a paid day off depends on the country's law and
  the employer's contracts (in Cyprus, private-sector entitlement is by contract or collective
  agreement). Apps that need that keep their own calendar and answer with the same items, adding
  their own categories (`company`).
- **FastAPI is optional** (`router` extra, imported inside `holidays_router()`), so apps that only
  compute holidays don't pull it in.
- Version `1.0.0` for the first release, like the other packages' first stable releases.
