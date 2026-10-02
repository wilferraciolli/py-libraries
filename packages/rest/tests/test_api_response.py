from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel, field_serializer

from wiltech_labs_rest import (
    ApiResponse,
    FieldMetadata,
    Link,
    LinkedResource,
    Message,
    MessageType,
    choice_field,
    format_utc_datetime,
)


class Colour(str, Enum):
    RED = "red"
    BLUE = "blue"


class ThingDTO(LinkedResource):
    id: str
    created_date: datetime

    @field_serializer("created_date")
    def serialize_created_date(self, value: datetime) -> str:
        return format_utc_datetime(value)


class ThingMetadata(BaseModel):
    id: FieldMetadata
    colour: FieldMetadata


ThingResponse = ApiResponse[ThingDTO, ThingMetadata]

METADATA = ThingMetadata(id=FieldMetadata(readOnly=True, hidden=True), colour=choice_field(Colour))


def _thing() -> ThingDTO:
    return ThingDTO(
        id="t1",
        created_date=datetime(2026, 1, 2, 3, 4, 5, 999, tzinfo=timezone.utc),
        links={"self": Link(href="/api/things/t1")},
    )


def test_envelope_serializes_with_underscore_aliases():
    body = ThingResponse.of("thing", _thing(), METADATA).model_dump(by_alias=True)

    assert body == {
        "_data": {
            "thing": {
                "links": {"self": {"href": "/api/things/t1", "method": "GET"}},
                "id": "t1",
                "created_date": "2026-01-02T03:04:05Z",
            }
        },
        "_metadata": {
            "id": {"readOnly": True, "hidden": True},
            "colour": {
                "mandatory": True,
                "values": [{"id": "red", "value": "red"}, {"id": "blue", "value": "blue"}],
            },
        },
        "_metaLinks": {},
        "_messages": [],
    }


def test_envelope_carries_meta_links_and_messages():
    response = ThingResponse.of(
        "thing",
        _thing(),
        METADATA,
        meta_links={"createThing": Link(href="/api/things", method="POST")},
        messages=[Message(type=MessageType.SUCCESS, value="Saved")],
    )
    body = response.model_dump(by_alias=True)

    assert body["_metaLinks"] == {"createThing": {"href": "/api/things", "method": "POST"}}
    assert body["_messages"] == [{"type": "SUCCESS", "value": "Saved"}]


def test_list_envelope():
    body = ApiResponse[list[ThingDTO], ThingMetadata].of("things", [_thing(), _thing()], METADATA)

    assert len(body.model_dump(by_alias=True)["_data"]["things"]) == 2


def test_field_metadata_omits_unset_flags():
    assert FieldMetadata().model_dump() == {}
    assert FieldMetadata(mandatory=True).model_dump() == {"mandatory": True}
    assert FieldMetadata(readOnly=False).model_dump() == {"readOnly": False}


def test_format_utc_datetime():
    assert format_utc_datetime(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05Z"

    plus_two = timezone(timedelta(hours=2))
    assert format_utc_datetime(datetime(2026, 1, 2, 3, 4, 5, tzinfo=plus_two)) == "2026-01-02T01:04:05Z"


def test_format_utc_datetime_accepts_iso_strings():
    assert format_utc_datetime("2026-01-02T03:04:05.123456+00:00") == "2026-01-02T03:04:05Z"
    assert format_utc_datetime("2026-01-02T03:04:05Z") == "2026-01-02T03:04:05Z"
    assert format_utc_datetime("2026-01-02 03:04:05") == "2026-01-02T03:04:05Z"
