from datetime import date, datetime, timezone
from typing import Annotated, Optional

from pydantic import AfterValidator, PlainSerializer


def utc_now() -> datetime:
    """Current UTC time at second precision — what every stored timestamp uses."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def format_utc_datetime(value: datetime | str) -> str:
    """
    Serialize datetimes as UTC seconds: YYYY-MM-DDTHH:MM:SSZ.

    Also accepts the ISO string SQLite/D1 hands back. A naive value is taken
    to be UTC already.
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def as_utc(value: datetime) -> datetime:
    """A datetime in UTC; a naive one (as SQLite may hand back) is taken to be UTC already."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def to_db_datetime(value: datetime) -> str:
    """Store datetimes as sortable UTC ISO strings (same format as the API)."""
    return format_utc_datetime(value)


def to_db_date(value: Optional[date]) -> Optional[str]:
    """Store dates as ISO `YYYY-MM-DD`; `None` stays `None`."""
    return value.isoformat() if value else None


# For database row models: stored dates are ISO strings that may or may not
# carry an offset, and comparing a naive datetime with an aware one fails.
UtcDateTime = Annotated[datetime, AfterValidator(as_utc)]

# For DTO fields: a UTC timestamp, serialized as YYYY-MM-DDTHH:MM:SSZ, so no
# per-field `@field_serializer` is needed.
UtcTimestamp = Annotated[datetime, PlainSerializer(format_utc_datetime, return_type=str)]
