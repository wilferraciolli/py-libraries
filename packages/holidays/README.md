# wiltech-labs-holidays

Public holidays for Wiltech apps: a locale in (`el-CY`, `en_GB`, `de-DE-BY`), holidays out as
`PublicHoliday` items (`date`, `name`, `category`, `country`), the shape
[`@wiltech-labs/ngx-calendar`](https://github.com/wilferraciolli/ngx-libraries/tree/main/packages/calendar)'s
`holidays` input shows as labelled public-holiday days. An app shows holidays with no mapping on
either side.

The calendars themselves come from the [`holidays`](https://pypi.org/project/holidays/) package
(MIT, ~150 countries, moveable feasts such as Orthodox Easter, names in several languages). This
package adds locale resolution, the shared item shape, categories kept per day, and a ready-made
FastAPI router.

## Install

```bash
uv add wiltech-labs-holidays                 # functions and the item shape
uv add "wiltech-labs-holidays[router]"       # plus holidays_router() (needs FastAPI)
```

Pure Python (`holidays`, `pydantic`, `wiltech-labs-rest`), so it loads in a Cloudflare Python Worker.

## Usage

### Serve a country's calendar as it is

```python
from wiltech_labs_holidays import holidays_router

app.include_router(holidays_router(default_country="CY"), prefix="/api")
```

`GET /api/public-holidays?locale=el-CY&from=2026-01-01&to=2026-12-31&categories=public,optional`:

```json
{
  "_data": { "publicHolidays": [
    { "date": "2026-02-23", "name": "Καθαρά Δευτέρα", "category": "public", "country": "CY", "subdivision": null }
  ] },
  "_metadata": { "country": "CY", "subdivision": null, "language": "el", "from_date": "2026-01-01", "to_date": "2026-12-31" },
  "_metaLinks": {},
  "_messages": []
}
```

The locale comes from `locale`, else the `Accept-Language` header; one without a region (`el`) uses
`default_country`. `from`/`to` default to this calendar year, at most 366 days apart.
`categories` defaults to `public`.

### Build your own calendar from it

An app that keeps its own calendar (which days its employer observes, plus company closure days)
uses the functions and answers with the same items:

```python
from wiltech_labs_holidays import PublicHoliday, public_holidays, resolve_locale

locale = resolve_locale("en-CY")                      # HolidayLocale(country="CY", language="en_CY")
for holiday in public_holidays(locale, 2026, categories=["public", "optional"]):
    ...                                                # Green Monday 2026-02-23 public, Christmas Eve 2026-12-24 optional

closure = PublicHoliday(date=date(2026, 12, 24), name="Office closed", category="company", country="CY")
```

## Public API

| Name | What it is |
|---|---|
| `resolve_locale(locale, default_country=None)` | `HolidayLocale(country, subdivision, language)` from `el-CY`, `en_GB`, `de-DE-BY`, `el-Grek-CY`; raises `UnsupportedLocaleError` |
| `HolidayLocale` | Country (ISO 3166-1 alpha-2), optional subdivision, and the `holidays` package's language code (None: the country's own) |
| `public_holidays(locale, years=None, *, from_date=None, to_date=None, categories=("public",))` | `list[PublicHoliday]`, earliest first; two holidays on one day are two items; `ValueError` for a category the country lacks |
| `PublicHoliday` | Pydantic model: `date`, `name`, `category` (default `public`), `country`, `subdivision` |
| `holiday_categories(country)` | The country's categories, e.g. Cyprus `("bank", "optional", "public")` |
| `supported_country(country)` | Whether there is a calendar |
| `holidays_router(*, default_country=None, prefix="/public-holidays", dependencies=None)` | FastAPI router (`router` extra) answering `PublicHolidayListResponse` |
| `PublicHolidayListResponse`, `PublicHolidayMetadata` | The router's envelope and metadata |
| `UnsupportedLocaleError` | A `ValueError` |
| `PUBLIC`, `DEFAULT_CATEGORIES` | `"public"`, `("public",)` |

Whether a public holiday is a paid day off is up to each country's law and each employer's
contracts; this package says which days are holidays, not who gets them.

## Publishing

Released to [TestPyPI](https://test.pypi.org/project/wiltech-labs-holidays/) (rehearsal) and
[PyPI](https://pypi.org/project/wiltech-labs-holidays/) (what apps install from). Account setup,
checking a TestPyPI release and fixing errors are covered in
[`docs/PUBLISHING.md`](https://github.com/wilferraciolli/py-libraries/blob/main/docs/PUBLISHING.md).
`wiltech-labs-rest` (>= 1.0.1) must be on PyPI first.

```bash
cd packages/holidays

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
git commit -am "wiltech-labs-holidays <version>"
git tag holidays-v<version> && git push && git push --tags
```
