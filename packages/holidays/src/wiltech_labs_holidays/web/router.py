"""`holidays_router()`: public holidays over HTTP in the standard envelope, for apps that serve the
country's calendar as it is. An app with its own calendar (days it adds or leaves out) serves its
own endpoint and answers with the same `PublicHoliday` items."""

from datetime import date
from typing import Optional

from pydantic import BaseModel
from wiltech_labs_rest import ApiResponse

from wiltech_labs_holidays.calendar.calendar import DEFAULT_CATEGORIES, PublicHoliday, public_holidays
from wiltech_labs_holidays.locale.locale import UnsupportedLocaleError, resolve_locale

DATA_NAME = "publicHolidays"
MAX_RANGE_DAYS = 366


class PublicHolidayMetadata(BaseModel):
    """What the request resolved to."""

    country: str
    subdivision: Optional[str] = None
    language: Optional[str] = None
    from_date: date
    to_date: date


PublicHolidayListResponse = ApiResponse[list[PublicHoliday], PublicHolidayMetadata]


def _first_accept_language(header: Optional[str]) -> Optional[str]:
    if not header:
        return None
    first = header.split(",")[0].split(";")[0].strip()
    return first if first and first != "*" else None


def holidays_router(
        *,
        default_country: Optional[str] = None,
        prefix: str = "/public-holidays",
        dependencies: Optional[list] = None,
):
    """GET `<prefix>?locale=el-CY&from=2026-01-01&to=2026-12-31&categories=public,optional`.

    The locale comes from `locale`, else the `Accept-Language` header; one without a region uses
    `default_country`. `from`/`to` default to this calendar year (at most 366 days apart).

        app.include_router(holidays_router(default_country="CY"), prefix="/api")

    Needs the `router` extra (`wiltech-labs-holidays[router]`) for FastAPI.
    """
    from fastapi import APIRouter, HTTPException, Query, Request

    router = APIRouter(prefix=prefix, tags=["public holidays"], dependencies=dependencies or [])

    @router.get("")
    async def list_public_holidays(
            request: Request,
            locale: Optional[str] = Query(default=None, description="e.g. el-CY; default: Accept-Language"),
            from_date: Optional[date] = Query(default=None, alias="from"),
            to_date: Optional[date] = Query(default=None, alias="to"),
            categories: str = Query(default=",".join(DEFAULT_CATEGORIES), description="Comma-separated"),
    ) -> PublicHolidayListResponse:
        wanted = locale or _first_accept_language(request.headers.get("accept-language")) or ""
        today = date.today()
        start = from_date or date(today.year, 1, 1)
        end = to_date or date(start.year, 12, 31)
        if end < start or (end - start).days + 1 > MAX_RANGE_DAYS:
            raise HTTPException(status_code=400, detail=f"Choose a range of {MAX_RANGE_DAYS} days or fewer")
        try:
            resolved = resolve_locale(wanted, default_country)
            items = public_holidays(
                resolved, from_date=start, to_date=end,
                categories=[c.strip() for c in categories.split(",") if c.strip()],
            )
        except (UnsupportedLocaleError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        metadata = PublicHolidayMetadata(
            country=resolved.country, subdivision=resolved.subdivision, language=resolved.language,
            from_date=start, to_date=end,
        )
        return PublicHolidayListResponse.of(DATA_NAME, items, metadata)

    return router
