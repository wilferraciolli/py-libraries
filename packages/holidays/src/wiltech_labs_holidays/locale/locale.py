"""From a locale the way the apps store it (`el-CY`, `en_GB`, `en-US-CA`) to the country, region
and language the `holidays` package needs."""

import re
from dataclasses import dataclass
from typing import Optional

import holidays

# language[-Script][-REGION][-subdivision]; separators `-` or `_`.
_LOCALE = re.compile(
    r"^(?P<language>[A-Za-z]{2,3})(?:[-_][A-Za-z]{4})?(?:[-_](?P<country>[A-Za-z]{2}))?(?:[-_](?P<subdivision>[A-Za-z0-9]{1,3}))?$"
)


class UnsupportedLocaleError(ValueError):
    """The locale names no country, or one with no holiday calendar."""


@dataclass(frozen=True)
class HolidayLocale:
    """Where and in which language: `country` an ISO 3166-1 alpha-2 code, `subdivision` its own
    code when the calendar differs by region (US states, German Länder), `language` the
    `holidays` package's name for it (`el`, `en_US`), or None for the country's own."""

    country: str
    subdivision: Optional[str] = None
    language: Optional[str] = None


def supported_country(country: str) -> bool:
    return country.upper() in holidays.list_supported_countries()


def _language_for(country: str, language: str) -> Optional[str]:
    """The best of the country's supported languages: `en_CY` for `en` in Cyprus, else a plain
    `en`, else any `en_*`, else None (the country's own language)."""
    supported = holidays.country_holidays(country).supported_languages
    for candidate in (f"{language}_{country}", language):
        if candidate in supported:
            return candidate
    variants = sorted(code for code in supported if code.split("_")[0] == language)
    return variants[0] if variants else None


def resolve_locale(locale: str, default_country: Optional[str] = None) -> HolidayLocale:
    """`el-CY` → Cyprus in Greek. A locale without a region (`el`) uses `default_country`.

    Raises `UnsupportedLocaleError` when there is no country, or no calendar for it.
    """
    match = _LOCALE.match(locale.strip()) if locale else None
    if match is None:
        raise UnsupportedLocaleError(f"Not a locale: {locale!r}")
    country = (match["country"] or default_country or "").upper()
    if not country:
        raise UnsupportedLocaleError(f"{locale!r} names no country, and there is no default")
    if not supported_country(country):
        raise UnsupportedLocaleError(f"No public holiday calendar for {country}")
    subdivision = match["subdivision"].upper() if match["subdivision"] else None
    if subdivision and subdivision not in holidays.list_supported_countries()[country]:
        subdivision = None  # a script or variant subtag, not a region of this country
    return HolidayLocale(
        country=country, subdivision=subdivision, language=_language_for(country, match["language"].lower())
    )
