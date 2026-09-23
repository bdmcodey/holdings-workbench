"""
Holdings already on a record are kept unless the cataloguer says otherwise.

Measured on a real 372-record export before 0.22.0, with default settings:

    records with 853 + 863 already       13   10 had 863s written over
    hand-entered 863s replaced           38   every $w g gap marker among them
    records with an 853 and no 863        2   kept -- but only because their
                                              statements happened to match it

and a synthetic record whose 853 matched nothing lost that 853 too, because the
new one took the same $8 and records.add_853() replaces by $8.

The rule is the cataloguer's: data already there is preferred, and only
"Clear existing 853 / 863 first" overwrites it. A record with 863s is kept
exactly as it is; an 853 its statements do not match gets a second 853 beside
it, with a note; and what is wrong with an existing 853 is said, never fixed.
"""

from __future__ import annotations

import io

from pymarc import Field, MARCReader, MARCWriter, Record, Subfield

from conftest import upload_marc
from marc_serials.converter import convert_record
from marc_serials.parser import parse_866


STATEMENT = "v. 1 no. 1 (1990)-v. 5 no. 4 (1994)"


def _record(*fields) -> Record:
    rec = Record()
    rec.leader = "00522cy  a22001453n 4500"
    rec.add_field(Field(tag="001", data="existing-test"))
    for tag, ind, subs in fields:
        rec.add_field(Field(tag=tag, indicators=list(ind),
                            subfields=[Subfield(c, v) for c, v in subs]))
    return rec


def _bytes(*records) -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for rec in records:
        writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def _downloaded(client) -> list:
    with client.get("/api/download-converted") as got:
        return list(MARCReader(got.data))


def _holdings(rec) -> list:
    return [str(f) for f in rec.get_fields("853", "863")]


HAND_853 = ("853", "20", [("8", "1"), ("a", "v."), ("b", "no."), ("i", "(year)")])
HAND_863 = ("863", "40", [("8", "1.1"), ("a", "1-3"), ("b", "1-4"),
                          ("i", "1990-1992"), ("w", "g")])
THE_866 = ("866", " 0", [("a", STATEMENT)])


def test_a_record_with_its_own_863s_is_kept_exactly_as_it_was(client):
    """The case that lost 38 fields: same pattern, 863s written over."""
    rec = _record(HAND_853, HAND_863, THE_866)
    upload_marc(client, _bytes(rec))

    body = client.post("/api/batch-convert", json={}).get_json()

    assert _holdings(_downloaded(client)[0]) == _holdings(rec)
    assert body["kept_existing"] == 1
    assert body["records_processed"] == 0
    assert 0 not in body["converted_indexes"]
    assert "already has 1 863 field" in body["summary"][0]["warnings"][0]


def test_it_is_kept_when_converted_on_its_own_too(client):
    rec = _record(HAND_853, HAND_863, THE_866)
    upload_marc(client, _bytes(rec))

    body = client.post("/api/convert-record", json={
        "record_index": 0,
        "conversions": [{"text": STATEMENT}]}).get_json()

    assert body["kept_existing"] is True
    assert _holdings(_downloaded(client)[0]) == _holdings(rec)


def test_clearing_is_the_instruction_that_overwrites(client):
    rec = _record(HAND_853, HAND_863, THE_866)
    upload_marc(client, _bytes(rec))

    body = client.post("/api/batch-convert",
                       json={"clear_existing_853_863": True}).get_json()

    assert body["kept_existing"] == 0
    assert _holdings(_downloaded(client)[0]) != _holdings(rec)


def test_the_list_and_the_preview_say_so_before_anything_is_converted(client):
    upload_marc(client, _bytes(_record(HAND_853, HAND_863, THE_866)))

    index = client.post("/api/review-index", json={}).get_json()
    assert index["kept_existing"] == 1
    assert index["records"][0]["kept_existing"] is True

    preview = client.post("/api/preview-record",
                          json={"record_index": 0}).get_json()
    assert preview["kept_existing"] is True
    assert preview["previews"] == []

    cleared = client.post("/api/preview-record", json={
        "record_index": 0, "clear_existing_853_863": True}).get_json()
    assert cleared["kept_existing"] is False
    assert cleared["previews"]


def test_an_853_the_holdings_do_not_match_gets_a_second_853_beside_it(client):
    """
    It used to be written over: the new 853 took $8 1, which was already the
    existing one's, and add_853() replaces by $8.
    """
    theirs = ("853", "20", [("8", "1"), ("a", "v."), ("i", "(year)")])
    rec = _record(theirs, THE_866)
    upload_marc(client, _bytes(rec))

    body = client.post("/api/batch-convert", json={}).get_json()
    fields = _downloaded(client)[0].get_fields("853")

    assert str(rec.get_fields("853")[0]) in [str(f) for f in fields], (
        "the 853 that was already on the record is gone")
    assert len(fields) == 2
    assert sorted(f.get("8") for f in fields) == ["1", "2"]
    assert any("A second 853 was added as $8 2" in w
               for w in body["summary"][0]["warnings"])


def test_an_853_the_holdings_do_match_takes_them_without_a_note(client):
    rec = _record(HAND_853, THE_866)
    upload_marc(client, _bytes(rec))

    body = client.post("/api/batch-convert", json={}).get_json()
    out = _downloaded(client)[0]

    assert [str(f) for f in out.get_fields("853")] == [str(rec.get_fields("853")[0])]
    assert [f.get("8") for f in out.get_fields("863")] == ["1.1"]
    assert not any("second 853" in w for w in body["summary"][0]["warnings"])


def test_what_is_wrong_with_an_existing_853_is_said_and_left(client):
    """
    Both shapes are from the real export: an 853 coded "X" and blank, sharing
    $8 1 with the record's actual pattern.
    """
    odd = ("853", "X ", [("8", "1"), ("a", "39"), ("b", "1"), ("i", "2018")])
    rec = _record(HAND_853, odd, THE_866)
    upload_marc(client, _bytes(rec))

    body = client.post("/api/batch-convert", json={}).get_json()
    warnings = " ".join(body["summary"][0]["warnings"])

    assert 'indicators "X#"' in warnings
    assert "2 853s already on this record share $8 1" in warnings
    after = [str(f) for f in _downloaded(client)[0].get_fields("853")]
    assert after == [str(f) for f in rec.get_fields("853")]

    row = client.post("/api/review-index", json={}).get_json()["records"][0]
    assert len(row["record_notes"]) == 2


def test_new_links_step_around_every_853_already_there():
    """At the source: not only the 853s a statement conformed to."""
    theirs = Field(tag="853", indicators=["2", "0"],
                   subfields=[Subfield("8", "1"), Subfield("a", "v."),
                              Subfield("i", "(year)")])
    rc = convert_record([parse_866(STATEMENT)], existing_853s=[theirs])

    assert [f.subfields[0].value for f in rc.fields_853] == ["2"]
    assert all(f.subfields[0].value.startswith("2.") for f in rc.fields_863)
    assert rc.record_notes and "$8 1" in rc.record_notes[0]
