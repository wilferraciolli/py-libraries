from pydantic import Field

from wiltech_labs_rest import ApiResponse, CamelLinkedResource, CamelMetadataBase, CamelModel, FieldMetadata, Link


class BedDTO(CamelLinkedResource):
    id: str
    bed_number: str


class BedMetadata(CamelMetadataBase):
    bed_number: FieldMetadata
    ward_name: FieldMetadata = Field(alias="ward.name")


class BedRequest(CamelModel):
    bed_number: str


def test_camel_dto_serializes_camel_case_with_links():
    bed = BedDTO(id="b1", bed_number="3", links={"self": Link(href="/api/beds/b1")})
    assert bed.model_dump() == {
        "links": {"self": {"href": "/api/beds/b1", "method": "GET"}},
        "id": "b1",
        "bedNumber": "3",
    }


def test_camel_metadata_keeps_explicit_aliases():
    metadata = BedMetadata(bed_number=FieldMetadata(mandatory=True), ward_name=FieldMetadata(readOnly=True))
    assert metadata.model_dump() == {"bedNumber": {"mandatory": True}, "ward.name": {"readOnly": True}}


def test_camel_request_accepts_either_spelling_and_dumps_snake_for_the_db():
    assert BedRequest.model_validate({"bedNumber": "3"}).bed_number == "3"
    assert BedRequest.model_validate({"bed_number": "3"}).model_dump(by_alias=False) == {"bed_number": "3"}


def test_camel_dto_inside_the_envelope():
    response = ApiResponse[BedDTO, BedMetadata].of(
        "bed", BedDTO(id="b1", bed_number="3"), BedMetadata(bed_number=FieldMetadata(), ward_name=FieldMetadata())
    )
    body = response.model_dump(by_alias=True)
    assert body["_data"]["bed"]["bedNumber"] == "3"
    assert body["_metadata"] == {"bedNumber": {}, "ward.name": {}}
