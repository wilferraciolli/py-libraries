from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator


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


# For database row models: stored dates are ISO strings that may or may not
# carry an offset, and comparing a naive datetime with an aware one fails.
UtcDateTime = Annotated[datetime, AfterValidator(as_utc)]
