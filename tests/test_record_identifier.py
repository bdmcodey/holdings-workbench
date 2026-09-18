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


# --- offering a field the file actually carries ----------------------------

def test_the_candidates_are_the_fields_that_could_name_a_record():
    """
    Three properties together, and the middle one earns its place.

    On the 372-record export this was built against, these three -- on every
    record, once per record, all values different -- return exactly the four
    identifiers it carries and nothing else. 866 $a has 371 distinct values
    across 372 records and would otherwise rank near the top; it occurs up to
    33 times in a single record, which is what rules it out.
    """
    from marc_serials.records import identifier_candidates

    records = [
        _record(mms="991000000000000001", control="c1", holdings="22000000000000001"),
        _record(mms="991000000000000002", control="c2", holdings="22000000000000002"),
        _record(mms="991000000000000003", control="c3", holdings="22000000000000003"),
    ]
    specs = [c["spec"] for c in identifier_candidates(records)]
    assert "999$b" in specs and "999$d" in specs and "001" in specs
    assert "999$a" not in specs, (
        "999 $a is 'ALMA_BIB_NUMBER' on every record -- a label, not a name")
    assert "866$a" not in specs, (
        "holdings data is what the tool converts, not what identifies a record")


def test_a_field_repeated_within_a_record_ranks_below_one_that_is_not():
    """
    The criterion that earns its place, tested on a field the tag list does
    not already exclude.

    A field occurring several times in one record is data *about* the record,
    not a name *for* it -- there is no single value to put beside the row. On
    the export this was built against, 866 $a had 371 distinct values across
    372 records and would have ranked near the top on distinctness alone; it
    occurs up to 33 times in one record. That one is excluded by tag as
    holdings data, so this uses a local note field to test the rule itself.
    """
    from pymarc import Field, Subfield
    from marc_serials.records import identifier_candidates

    # 001 is deliberately the weaker field on every other measure: it repeats
    # a value across two records, so it is distinct on only two of three. The
    # note is distinct on all three. If being repeated within a record did not
    # count, the note would rank first -- so this fails the moment that test
    # stops being applied, which a version of it using a perfect 001 did not.
    controls = ["c1", "c1", "c3"]
    records = []
    for n, control in enumerate(controls, start=1):
        rec = _record(control=control)
        for part in ("a", "b"):
            rec.add_field(Field(tag="590", indicators=[" ", " "],
                                subfields=[Subfield(code="a",
                                                    value=f"note {n}{part}")]))
        records.append(rec)

    found = {c["spec"]: c for c in identifier_candidates(records)}
    assert found["590$a"]["repeated"] is True
    assert found["590$a"]["distinct"] == 3 and found["001"]["distinct"] == 2, (
        "the note must out-score 001 on distinctness, or this proves nothing")
    specs = list(found)
    assert specs.index("001") < specs.index("590$a"), (
        "a field appearing twice in a record cannot name it, however many "
        "distinct values it has across the file")


def test_a_candidate_carries_a_sample_because_that_is_what_is_recognisable():
    """"999$b" means nothing; "991000485469603731" is an MMS ID to its user."""
    from marc_serials.records import identifier_candidates

    records = [_record(mms="991000485469603731"), _record(mms="991000218369603731")]
    chosen = next(c for c in identifier_candidates(records) if c["spec"] == "999$b")
    assert chosen["sample"] == "991000485469603731"
    assert chosen["present"] == 2 and chosen["total"] == 2 and chosen["distinct"] == 2


def test_a_field_missing_from_some_records_ranks_below_one_on_all_of_them():
    """A record the field is absent from is a row that cannot be found."""
    from marc_serials.records import identifier_candidates

    records = [_record(mms="a1", control="c1"), _record(mms="a2", control="c2"),
               _record(control="c3")]
    specs = [c["spec"] for c in identifier_candidates(records)]
    assert specs.index("001") < specs.index("999$b"), (
        "a field on every record identifies better than one on two thirds")


def test_a_field_on_a_single_record_is_not_offered_at_all():
    """
    One record carrying it means one value, and one value is a label.

    Ranking it below the others would still put it on screen as something to
    choose, and choosing it would leave every other row unfindable.
    """
    from marc_serials.records import identifier_candidates

    records = [_record(mms="a1", control="c1"), _record(control="c2"),
               _record(control="c3")]
    assert [c["spec"] for c in identifier_candidates(records)] == ["001"]


# --- changing it without re-uploading --------------------------------------

def test_choosing_a_field_takes_effect_without_re_uploading(client):
    """
    The record list is built at upload, so the naive version of this setting
    would take effect "next time you upload" -- the lag the frequency and
    numbering controls already have, and not worth a third of.
    """
    upload_marc(client, _as_file(_record(mms="991000485469603731",
                                         control="h120583-01usc_inst")))
    got = client.post("/api/identifier", json={"spec": "001"}).get_json()
    assert got["spec"] == "001"
    assert got["found"] is True
    assert got["identifiers"][0]["identifier"] == "h120583-01usc_inst"


def test_the_choice_survives_the_next_file(client):
    """
    It describes the library's ILS, not this upload. The next export from the
    same institution wants the same field.
    """
    upload_marc(client, _as_file(_record(mms="991", control="c1")))
    client.post("/api/identifier", json={"spec": "001"})
    again = upload_marc(client, _as_file(_record(mms="992", control="c2"))).get_json()
    assert again["identifier_field"] == "001"
    assert again["records"][0]["identifier"] == "c2"


def test_showing_no_identifier_is_a_choice_and_is_remembered_as_one(client):
    """
    Distinct from never having chosen. A cataloguer who has said "none" must
    not be asked again on the next upload, which is what falling back to the
    default would do.
    """
    upload_marc(client, _as_file(_record(mms="991000485469603731")))
    got = client.post("/api/identifier", json={"spec": ""}).get_json()
    assert got["spec"] == "" and got["found"] is False

    again = upload_marc(client, _as_file(_record(mms="991000485469603731"))).get_json()
    assert again["identifier_field"] == "", (
        "'no identifier' fell back to the default, so the choice was lost")
    assert again["records"][0]["identifier"] == ""


def test_a_field_that_is_not_a_field_is_refused_rather_than_stored(client):
    """
    Storing a typo would show an empty column that looks like the file's
    fault. The two want different actions, so they must not look the same.
    """
    upload_marc(client, _as_file(_record(mms="991000485469603731")))
    bad = client.post("/api/identifier", json={"spec": "not-a-field"})
    assert bad.status_code == 400
    assert "not a MARC field" in bad.get_json()["error"]

    # And the working field it had before is still in force.
    still = upload_marc(client, _as_file(_record(mms="991000485469603731"))).get_json()
    assert still["identifier_field"] == DEFAULT_IDENTIFIER_SPEC
