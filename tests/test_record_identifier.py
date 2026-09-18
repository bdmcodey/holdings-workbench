"""
The identifier a cataloguer finds a record by.

Holdings records usually carry no 245 -- the title is on the bibliographic
record -- so without an identifier every row on the Convert step reads
"Record 41" and a file of several hundred is a list nobody can navigate. A real
372-record Alma export measured while this was built had no 245 and no 022 on
any record: title and ISSN were empty on all 372, the location was identical on
all 372, and the only thing distinguishing one row from another was its number.

So this is not decoration, and the tests are about a row staying findable.
"""

from __future__ import annotations

import io

import pytest
from pymarc import Field, MARCWriter, Record, Subfield

from conftest import upload_marc
from marc_serials.records import (
    DEFAULT_IDENTIFIER_SPEC,
    parse_identifier_spec,
    read_marc_file,
    record_identifier,
)


def _record(*, mms: str = "", control: str = "", holdings: str = "") -> Record:
    """A holdings record shaped like the ones this was built against."""
    rec = Record()
    rec.leader = "00522cy  a22001453n 4500"
    if control:
        rec.add_field(Field(tag="001", data=control))
    rec.add_field(Field(tag="866", indicators=[" ", "0"],
                        subfields=[Subfield(code="a", value="v.1(1990)")]))
    if mms or holdings:
        subs = [Subfield(code="a", value="ALMA_BIB_NUMBER")]
        if mms:
            subs.append(Subfield(code="b", value=mms))
        subs.append(Subfield(code="c", value="ALMA_HOLDINGS_NUMBER"))
        if holdings:
            subs.append(Subfield(code="d", value=holdings))
        rec.add_field(Field(tag="999", indicators=[" ", " "], subfields=subs))
    return rec


def _as_file(*records: Record) -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for rec in records:
        writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


# --- reading the spec ------------------------------------------------------

@pytest.mark.parametrize("spec, expected", [
    ("999$b", ("999", "b")),
    ("999 $b", ("999", "b")),
    ("999b", ("999", "b")),
    ("999|b", ("999", "b")),
    ("  999$B  ", ("999", "b")),
    ("001", ("001", "")),
    ("999", ("999", "")),
])
def test_a_field_can_be_named_the_way_anyone_would_write_it(spec, expected):
    """
    Four ways of writing the same field, because all four get typed.

    A cataloguer entering a field in a settings box should not have to guess
    which punctuation this wanted.
    """
    assert parse_identifier_spec(spec) == expected


@pytest.mark.parametrize("spec", ["", "   ", None, "abc", "99", "9999x", "$b"])
def test_nonsense_is_no_identifier_rather_than_a_silent_mismatch(spec):
    """
    A typo has to be distinguishable from a field that is simply absent.

    Returning a tag that matches nothing would show the same empty column as a
    file genuinely lacking the field, and those want different actions: one is
    "fix what you typed", the other "this export does not carry it".
    """
    assert parse_identifier_spec(spec) is None


# --- reading the value -----------------------------------------------------

def test_the_mms_id_is_what_a_record_is_found_by():
    rec = _record(mms="991000485469603731", holdings="22671059520003731")
    assert record_identifier(rec) == "991000485469603731"
    assert DEFAULT_IDENTIFIER_SPEC == "999$b"


def test_a_control_field_is_read_whole():
    """001-009 hold data, not subfields, so a subfield code cannot apply."""
    rec = _record(control="h120583-01usc_inst")
    assert record_identifier(rec, "001") == "h120583-01usc_inst"
    assert record_identifier(rec, "001$a") == "h120583-01usc_inst"


def test_a_record_without_the_field_is_blank_rather_than_an_error():
    """
    The ordinary case. Files arrive from every ILS there is, and a missing
    local field is not a damaged record -- both committed fixtures are like
    this, and they must still upload and convert.
    """
    rec = _record(control="only-an-001")
    assert record_identifier(rec) == ""
    assert record_identifier(rec, "947$z") == ""


def test_the_holdings_number_is_reachable_even_though_it_is_not_the_default():
    """
    999 carries both: $b the bib MMS ID, $d the holdings MMS ID.

    $b is the default because it is the number Alma shows beside a record and
    keys reports on, which is what a cataloguer recognises -- not because it is
    the more precise of the two. Naming the other must work, because that
    choice belongs to the library.
    """
    rec = _record(mms="991000485469603731", holdings="22671059520003731")
    assert record_identifier(rec, "999$d") == "22671059520003731"


# --- reaching the screen ---------------------------------------------------

def test_every_summary_carries_an_identifier_key():
    """
    Present on every record, blank where unknown -- never absent.

    The row template asks each record for it, so a missing key would be
    "undefined" printed beside a row rather than nothing printed.
    """
    data = _as_file(_record(mms="991000485469603731"), _record(control="x1"))
    summaries = read_marc_file(io.BytesIO(data))
    assert [r["identifier"] for r in summaries] == ["991000485469603731", ""]
    assert all("identifier" in r for r in summaries)


def test_the_upload_says_whether_the_file_carries_the_field_at_all(client):
    """
    So the screen can say "this file has no 999 $b" once, instead of drawing an
    empty slot beside every one of 372 rows and leaving the cataloguer to work
    out whether the file or the tool is at fault.
    """
    with_id = _as_file(_record(mms="991000485469603731"))
    got = upload_marc(client, with_id).get_json()
    assert got["identifier_found"] is True
    assert got["identifier_field"] == "999$b"

    without = _as_file(_record(control="no-999-here"))
    got = upload_marc(client, without).get_json()
    assert got["identifier_found"] is False, (
        "a file with no 999 $b must say so, not report an identifier it lacks")
    assert got["records"][0]["identifier"] == ""
