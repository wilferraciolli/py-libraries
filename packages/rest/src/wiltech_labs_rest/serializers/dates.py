from datetime import datetime, timezone


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
