from typing import Annotated, Any, Optional

from pydantic import BeforeValidator, PlainSerializer


def _blank_to_none(value: Any) -> Any:
    # Angular forms send "" for an untouched optional field; treat it as
    # "not given" instead of failing validation with a 422.
    if isinstance(value, str) and not value.strip():
        return None
    return value


# An optional request value where "" (or whitespace) means "not given":
# `Annotated[Optional[str], BlankAsNone]`.
BlankAsNone = BeforeValidator(_blank_to_none)

# An optional string sent as "" rather than null, for fields a client binds
# straight into form controls.
EmptyIfNone = Annotated[
    Optional[str],
    PlainSerializer(lambda value: "" if value is None else str(value), return_type=str),
]
