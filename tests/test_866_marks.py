"""
What an 866 says besides its numbers: the breaks its punctuation marks, and
its notes.

Measured on a real export whose 866s Alma generated from hand-entered 863s --
48 statements, each linked back to the 863 it was built from by $8. Reading
them back, the enumeration and chronology agreed in all 48, and everything
else that differed was one of two things:

    23 statements   863 $w g        Alma's 866 ends in a comma     not written
     5 statements   863 $z          Alma's 866 carries the $z      not written

If the ILS regenerates 866s from 863s on reload, both vanish from display:
the comma goes with the $w, "Incomplete" with the $z. With these carried,
all 48 agree on every subfield.

And with "Remove each 866" ticked, an 866 whose statement converted was
removed with its $z still on it, and nothing said so.
"""

from __future__ import annotations

import io

import pytest
from pymarc import Field, MARCReader, MARCWriter, Record, Subfield

from conftest import upload_marc
from marc_serials.converter import convert_holdings
from marc_serials.parser import parse_866


def _863s(statement: str) -> list:
    return [" ".join(f"${sf.code} {sf.value}" for sf in f.subfields
                     if sf.code != "8")
            for f in convert_holdings(parse_866(statement)).fields_863]


# -- breaks -------------------------------------------------------------------

@pytest.mark.parametrize("statement, expected", [
    # Alma's own shape: the comma after the last run is the $w g it came from.
    ("v.45(1988),", ["$a 45 $i 1988 $w g"]),
    ("v.1(1960)-v.35(1994),", ["$a 1-35 $i 1960-1994 $w g"]),
    ("v.44:no.3(1987:May/June),", ["$a 44 $b 3 $i 1987 $j 05/06 $w g"]),
    # Z39.71 punctuates a break that is not a gap with a semicolon.
    ("v.12(1928)-v.13(1929);", ["$a 12-13 $i 1928-1929 $w n"]),
    # And with no punctuation there is no break to write.
    ("v.45(1988)", ["$a 45 $i 1988"]),
])
def test_a_statement_ending_on_a_break_says_so(statement, expected):
    assert _863s(statement) == expected


def test_a_comma_between_two_runs_is_the_gap_between_them():
    assert _863s("v.1(1990)-v.5(1994), v.7(1996)-v.9(1998)") == [
        "$a 1-5 $i 1990-1994 $w g", "$a 7-9 $i 1996-1998"]


def test_runs_that_carry_straight_on_have_no_gap_to_mark():
    """The same test _gap_after() applies between the items of a list."""
    assert _863s("v.1(1990)-v.5(1994), v.6(1995)-v.9(1998)") == [
        "$a 1-5 $i 1990-1994", "$a 6-9 $i 1995-1998"]


def test_a_semicolon_between_two_runs_is_a_break_that_is_not_a_gap():
    assert _863s("v.1(1990)-v.5(1994); v.7(1996)-v.9(1998)") == [
        "$a 1-5 $i 1990-1994 $w n", "$a 7-9 $i 1996-1998"]


# -- notes --------------------------------------------------------------------

def _file(*subfields) -> bytes:
    rec = Record()
    rec.leader = "00522cy  a22001453n 4500"
    rec.add_field(Field(tag="001", data="notes-test"))
    rec.add_field(Field(tag="866", indicators=[" ", "0"],
                        subfields=[Subfield(c, v) for c, v in subfields]))
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def _converted(client, remove_866=True):
    body = client.post("/api/batch-convert",
                       json={"remove_866": remove_866}).get_json()
    with client.get("/api/download-converted") as got:
        record = list(MARCReader(got.data))[0]
    return body["summary"][0]["warnings"], record


def test_public_and_nonpublic_notes_go_to_the_863(client):
    upload_marc(client, _file(("a", "v. 41-71 (1943-1973)"),
                              ("z", "Shelved in storage."),
                              ("x", "Bound by vendor 2004")))
    warnings, record = _converted(client)

    field = record.get_fields("863")[0]
    assert field.get_subfields("z") == ["Shelved in storage."]
    assert field.get_subfields("x") == ["Bound by vendor 2004"]
    assert record.get_fields("866") == [], "the 866 was accounted for in full"
    assert warnings == []


def test_it_is_the_same_when_a_record_is_converted_on_its_own(client):
    upload_marc(client, _file(("a", "v. 41-71 (1943-1973)"),
                              ("z", "Shelved in storage.")))
    client.post("/api/convert-record", json={
        "record_index": 0,
        "conversions": [{"text": "v. 41-71 (1943-1973)", "remove_866": True}]})
    with client.get("/api/download-converted") as got:
        record = list(MARCReader(got.data))[0]
    assert record.get_fields("863")[0].get_subfields("z") == ["Shelved in storage."]


def test_the_preview_shows_the_note_that_will_be_written(client):
    upload_marc(client, _file(("a", "v.85(1993)-v.90(1997),"), ("z", "Incomplete")))
    preview = client.post("/api/preview-record",
                          json={"record_index": 0}).get_json()
    assert preview["previews"][0]["fields_863"] == [
        "863 40 $8 1.1 $a 85-90 $i 1993-1997 $w g $z Incomplete"]


def test_a_note_on_a_statement_of_several_runs_is_placed_and_said(client):
    upload_marc(client, _file(("a", "v. 1-5 (1990-1994), v. 7-9 (1996-1998)"),
                              ("z", "Incomplete")))
    warnings, record = _converted(client)

    fields = record.get_fields("863")
    assert [f.get_subfields("z") for f in fields] == [[], ["Incomplete"]]
    assert any("put on the last" in w for w in warnings), warnings


def test_an_866_carrying_what_an_863_cannot_is_kept_and_says_why(client):
    upload_marc(client, _file(("a", "v. 41-71 (1943-1973)"), ("6", "880-01")))
    warnings, record = _converted(client)

    assert record.get_fields("863"), "the holdings still convert"
    assert record.get_fields("866"), "the 866 went, and its $6 with it"
    assert any("$6" in w for w in warnings), warnings
