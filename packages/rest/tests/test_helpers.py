from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Optional

from pydantic import BaseModel, Field

from wiltech_labs_rest import (
    BlankAsNone,
    EmbeddedRef,
    EmptyIfNone,
    FieldMetadata,
    MetadataBase,
    Money,
    UtcTimestamp,
    mandatory,
    money,
    read_only,
    to_db_date,
    to_db_datetime,
    utc_now,
)


def test_read_only_and_mandatory_shortcuts():
    assert read_only().model_dump() == {"readOnly": True}
    assert read_only(hidden=True).model_dump() == {"readOnly": True, "hidden": True}
    assert mandatory().model_dump() == {"mandatory": True}
    assert mandatory([EmbeddedRef(id="A", value="Aye")]).model_dump() == {
        "mandatory": True,
        "values": [{"id": "A", "value": "Aye"}],
    }


def test_metadata_base_serializes_dotted_keys_by_alias():
    class QuoteMetadata(MetadataBase):
        id: FieldMetadata
        driver_sex: FieldMetadata = Field(alias="driver.sex")

    metadata = QuoteMetadata(id=read_only(), driver_sex=mandatory())

    assert metadata.model_dump() == {"id": {"readOnly": True}, "driver.sex": {"mandatory": True}}


def test_utc_timestamp_serializes_as_utc_seconds():
    class EventDTO(BaseModel):
        at: UtcTimestamp

    event = EventDTO(at=datetime(2026, 1, 2, 4, 4, 5, 999, tzinfo=timezone(timedelta(hours=1))))

    assert event.model_dump(mode="json") == {"at": "2026-01-02T03:04:05Z"}
    assert event.model_dump() == {"at": "2026-01-02T03:04:05Z"}


def test_money_rounds_half_up_and_serializes_as_a_number():
    class PriceDTO(BaseModel):
        amount: Money

    assert money("2.345") == Decimal("2.35")
    assert money(1) == Decimal("1.00")
    assert PriceDTO(amount=money("10.5")).model_dump(mode="json") == {"amount": 10.5}


def test_blank_as_none_and_empty_if_none():
    class FormRequest(BaseModel):
        nickname: Annotated[Optional[str], BlankAsNone] = None

    class FormDTO(BaseModel):
        nickname: EmptyIfNone = None

    assert FormRequest(nickname="  ").nickname is None
    assert FormRequest(nickname="Wil").nickname == "Wil"
    assert FormDTO().model_dump(mode="json") == {"nickname": ""}
    assert FormDTO(nickname="Wil").model_dump(mode="json") == {"nickname": "Wil"}


def test_db_helpers_and_utc_now():
    assert to_db_datetime(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05Z"
    assert to_db_date(date(2026, 1, 2)) == "2026-01-02"
    assert to_db_date(None) is None

    now = utc_now()
    assert now.tzinfo == timezone.utc and now.microsecond == 0
