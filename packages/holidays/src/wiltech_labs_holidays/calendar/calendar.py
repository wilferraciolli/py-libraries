"""Public holidays as `PublicHoliday` items, on the `holidays` package's calendars.

The shape is the contract with the UI: `@wiltech-labs/ngx-calendar`'s `holidays` input takes these
items as the API sends them (`date`, `name`, `category`), so an app shows holidays with no mapping.
"""

from datetime import date
from typing import Iterable, Optional

import holidays
from pydantic import BaseModel

from wiltech_labs_holidays.locale.locale import HolidayLocale, UnsupportedLocaleError, supported_country

# The `holidays` package's categories, in the order a day's holidays are listed.
PUBLIC = "public"
DEFAULT_CATEGORIES = (PUBLIC,)


class PublicHoliday(BaseModel):
    """One holiday. `category` is the `holidays` package's (`public`, `bank`, `optional`, ...);
    `public` days are the country's public holidays. An app may add its own categories (a company
    closure day) in the same shape."""

    date: date
    name: str
    category: str = PUBLIC
    country: str
    subdivision: Optional[str] = None


def _years(years: Optional[int | Iterable[int]], from_date: Optional[date], to_date: Optional[date]) -> list[int]:
    if years is not None:
        return [years] if isinstance(years, int) else sorted(set(years))
    if from_date is None or to_date is None:
        raise ValueError("Give the years, or both from_date and to_date")
    return list(range(from_date.year, to_date.year + 1))


def public_holidays(
        locale: HolidayLocale,
        years: Optional[int | Iterable[int]] = None,
        *,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        categories: Iterable[str] = DEFAULT_CATEGORIES,
) -> list[PublicHoliday]:
    """The holidays of `locale`'s country (and subdivision), named in its language, for the
    `years` or the inclusive `from_date`–`to_date` range, earliest first. Two holidays on one day
    are two items. `categories` defaults to the public holidays only.

    Raises `UnsupportedLocaleError` for a country with no calendar, `ValueError` for a category
    the country doesn't have.
    """
    if not supported_country(locale.country):
        raise UnsupportedLocaleError(f"No public holiday calendar for {locale.country}")
    categories = tuple(dict.fromkeys(categories))
    supported = holidays.country_holidays(locale.country).supported_categories
    unknown = [category for category in categories if category not in supported]
    if unknown:
        raise ValueError(f"{locale.country} has no {', '.join(unknown)} holidays; it has {', '.join(supported)}")

    items: list[PublicHoliday] = []
    for order, category in enumerate(categories):
        calendar = holidays.country_holidays(
            locale.country, subdiv=locale.subdivision, years=_years(years, from_date, to_date),
            language=locale.language, categories=(category,),
        )
        for day in calendar:
            if (from_date and day < from_date) or (to_date and day > to_date):
                continue
            for name in calendar.get_list(day):
                items.append(PublicHoliday(
                    date=day, name=name, category=category, country=locale.country, subdivision=locale.subdivision,
                ))
    rank = {category: order for order, category in enumerate(categories)}
    return sorted(items, key=lambda item: (item.date, rank[item.category]))


def holiday_categories(country: str) -> tuple[str, ...]:
    """The categories `country`'s calendar has, e.g. Cyprus: `bank`, `optional`, `public`."""
    if not supported_country(country):
        raise UnsupportedLocaleError(f"No public holiday calendar for {country}")
    return tuple(holidays.country_holidays(country.upper()).supported_categories)
