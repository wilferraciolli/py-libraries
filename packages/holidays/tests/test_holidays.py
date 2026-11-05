from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wiltech_labs_holidays import (
    HolidayLocale,
    PublicHoliday,
    UnsupportedLocaleError,
    holiday_categories,
    holidays_router,
    public_holidays,
    resolve_locale,
)

CY = HolidayLocale(country="CY", language="en_US")


# Locale


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("el-CY", HolidayLocale("CY", None, "el")),
        ("en_CY", HolidayLocale("CY", None, "en_CY")),
        ("en-GB", HolidayLocale("GB", None, "en_GB")),
        ("de-DE-BY", HolidayLocale("DE", "BY", "de")),
        ("el-Grek-CY", HolidayLocale("CY", None, "el")),  # a script subtag is skipped
        ("xx-CY", HolidayLocale("CY", None, None)),  # a language the calendar lacks: the country's own
    ],
)
def test_a_locale_resolves_to_country_region_and_language(locale, expected):
    assert resolve_locale(locale) == expected


def test_a_locale_without_a_region_uses_the_default_country():
    assert resolve_locale("el", default_country="cy") == HolidayLocale("CY", None, "el")
    with pytest.raises(UnsupportedLocaleError):
        resolve_locale("el")


@pytest.mark.parametrize("locale", ["", "cyprus", "en-ZZ"])
def test_nonsense_or_unknown_countries_are_refused(locale):
    with pytest.raises(UnsupportedLocaleError):
        resolve_locale(locale)


# Calendar: Cyprus is pinned against Crewly's requirements register (CY-16)


def test_cyprus_2026_public_holidays_follow_orthodox_easter():
    days = {item.date: item.name for item in public_holidays(CY, 2026)}
    assert days[date(2026, 2, 23)] == "Green Monday"
    assert days[date(2026, 4, 10)] == "Good Friday"
    assert days[date(2026, 4, 13)] == "Easter Monday"
    assert days[date(2026, 6, 1)] == "Pentecost Monday"  # Kataklysmos
    assert date(2026, 4, 14) not in days  # Easter Tuesday is optional, not public


def test_the_2027_easter_moves():
    names = {item.name: item.date for item in public_holidays(CY, 2027)}
    assert names["Easter Sunday"] == date(2027, 5, 2)


def test_optional_and_bank_days_come_only_when_asked_for_and_say_so():
    items = public_holidays(
        CY, from_date=date(2026, 4, 10), to_date=date(2026, 4, 14), categories=["public", "optional", "bank"]
    )
    assert [(i.date.isoformat(), i.name, i.category) for i in items] == [
        ("2026-04-10", "Good Friday", "public"),
        ("2026-04-11", "Holy Saturday", "optional"),
        ("2026-04-12", "Easter Sunday", "public"),
        ("2026-04-13", "Easter Monday", "public"),
        ("2026-04-14", "Easter Tuesday", "bank"),
    ]
    assert "bank" in holiday_categories("CY")


def test_names_come_in_the_locale_s_language():
    greek = public_holidays(resolve_locale("el-CY"), from_date=date(2026, 12, 25), to_date=date(2026, 12, 25))
    assert greek[0].name == "Χριστούγεννα"


def test_a_range_spans_years_and_stays_inside_its_dates():
    items = public_holidays(CY, from_date=date(2026, 12, 25), to_date=date(2027, 1, 6))
    assert [item.date.isoformat() for item in items] == ["2026-12-25", "2026-12-26", "2027-01-01", "2027-01-06"]


def test_an_unknown_category_is_refused():
    with pytest.raises(ValueError):
        public_holidays(CY, 2026, categories=["school"])


def test_the_item_is_the_shape_the_ui_reads():
    item = PublicHoliday(date=date(2026, 2, 23), name="Green Monday", country="CY")
    assert item.model_dump(mode="json") == {
        "date": "2026-02-23", "name": "Green Monday", "category": "public", "country": "CY", "subdivision": None,
    }


# Router


def client() -> TestClient:
    app = FastAPI()
    app.include_router(holidays_router(default_country="CY"), prefix="/api")
    return TestClient(app)


def test_the_router_answers_in_the_envelope():
    response = client().get("/api/public-holidays", params={"locale": "en-CY", "from": "2026-04-01", "to": "2026-04-30"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"_data", "_metadata", "_metaLinks", "_messages"}
    assert [h["name"] for h in body["_data"]["publicHolidays"]] == [
        "Cyprus National Day", "Good Friday", "Easter Sunday", "Easter Monday",
    ]
    assert body["_metadata"]["country"] == "CY" and body["_metadata"]["language"] == "en_CY"


def test_the_router_reads_accept_language_and_defaults_to_this_year():
    response = client().get("/api/public-holidays", headers={"Accept-Language": "el;q=0.9, en;q=0.8"})
    assert response.status_code == 200, response.text
    metadata = response.json()["_metadata"]
    assert metadata["country"] == "CY" and metadata["language"] == "el"
    assert metadata["from_date"].endswith("-01-01") and metadata["to_date"].endswith("-12-31")


def test_the_router_refuses_what_it_can_t_answer():
    assert client().get("/api/public-holidays", params={"locale": "en-ZZ"}).status_code == 400
    assert client().get("/api/public-holidays", params={"from": "2026-01-01", "to": "2027-06-30"}).status_code == 400
