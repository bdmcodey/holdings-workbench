"""
Correcting an 866 in the Workbench rather than before it.

A typo in a hand-written statement used to mean leaving the Workbench,
fixing the record in the ILS or MarcEdit, exporting again and starting over.
On the real 372-record export two statements show the two ways a typo costs:
"(Fal 1995-Fall 1999)" converts, flagged, without its season, and
"57-59 61, 63, 65-66-(...)" converts to nothing at all.

An edit is a decision like the others: kept with the session, forgotten on a
new upload, and applied where records are read -- so the list, both
conversions and the downloaded file carry the corrected 866. The cataloguer
chose that the corrected text goes into the file, and that what was changed
is said on the record, for the log a session will one day keep.
"""

from __future__ import annotations

import io

from pymarc import Field, MARCReader, MARCWriter, Record, Subfield

from conftest import upload_marc


TYPO = "v. 5 no. 1-v. 8 no. 2 (Fal 1995-Fall 1999)"
FIXED = "v. 5 no. 1-v. 8 no. 2 (Fall 1995-Fall 1999)"


def _file(*fields_866) -> bytes:
    rec = Record()
    rec.leader = "00522cy  a22001453n 4500"
    rec.add_field(Field(tag="001", data="edit-test"))
    for subfields in fields_866:
        rec.add_field(Field(tag="866", indicators=[" ", "0"],
                            subfields=[Subfield(c, v) for c, v in subfields]))
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def _edit(client, field_index=0, code="a", value="", revert=False):
    return client.post("/api/edit-866", json={
        "record_index": 0, "field_index": field_index, "code": code,
        "value": value, "revert": revert})


def _preview(client, field_index=0):
    body = client.post("/api/preview-record", json={"record_index": 0}).get_json()
    return next(p for p in body["previews"] if p["field_index"] == field_index)


def _downloaded(client):
    with client.get("/api/download-converted") as got:
        return list(MARCReader(got.data))[0]


def test_a_corrected_statement_is_converted_as_corrected(client):
    upload_marc(client, _file([("a", "v. 3 (1993)")], [("a", TYPO)]))
    before = _preview(client, 1)
    assert before["flagged"], "the typo should have cost the season"

    body = _edit(client, 1, "a", FIXED).get_json()
    after = _preview(client, 1)

    assert not after["flagged"]
    assert "$j 23-23" in after["fields_863"][0]
    assert body["fields_866"][1]["a"] == FIXED
    assert FIXED in body["statements"] and TYPO not in body["statements"]


def test_the_downloaded_record_carries_the_corrected_866_and_says_so(client):
    upload_marc(client, _file([("a", TYPO)]))
    _edit(client, 0, "a", FIXED)

    summary = client.post("/api/batch-convert", json={}).get_json()["summary"][0]
    record = _downloaded(client)

    assert [f["a"] for f in record.get_fields("866")] == [FIXED]
    assert summary["edited"] and TYPO in summary["edited"][0]
    assert summary["warnings"][0] == summary["edited"][0]


def test_an_edit_after_converting_reaches_the_file_without_converting_again(client):
    upload_marc(client, _file([("a", TYPO)]))
    client.post("/api/batch-convert", json={})
    _edit(client, 0, "a", FIXED)

    record = _downloaded(client)
    assert [f["a"] for f in record.get_fields("866")] == [FIXED]
    assert record.get_fields("863")[0].get("j") == "23-23"


def test_the_list_marks_an_edited_record_without_calling_it_a_problem(client):
    upload_marc(client, _file([("a", TYPO)]))
    _edit(client, 0, "a", FIXED)

    row = client.post("/api/review-index", json={}).get_json()["records"][0]
    assert row["edited"]
    assert row["record_notes"] == [], "an edit is attention given, not wanted"


def test_notes_can_be_added_and_changed_and_reach_the_863(client):
    upload_marc(client, _file([("a", "v. 41-71 (1943-1973)"), ("z", "Incomplet")]))
    _edit(client, 0, "z", "Incomplete")
    _edit(client, 0, "x", "Checked against shelf 2026")
    client.post("/api/batch-convert", json={})

    f863 = _downloaded(client).get_fields("863")[0]
    assert f863.get_subfields("z") == ["Incomplete"]
    assert f863.get_subfields("x") == ["Checked against shelf 2026"]


def test_putting_it_back_forgets_the_correction(client):
    upload_marc(client, _file([("a", TYPO)]))
    _edit(client, 0, "a", FIXED)
    body = _edit(client, 0, "a", revert=True).get_json()

    assert body["fields_866"][0]["a"] == TYPO
    assert body["edited"] == []
    row = client.post("/api/review-index", json={}).get_json()["records"][0]
    assert row["edited"] == []


def test_the_holdings_statement_cannot_be_emptied_or_anything_else_edited(client):
    upload_marc(client, _file([("a", TYPO)]))
    assert _edit(client, 0, "a", "   ").status_code == 400
    assert _edit(client, 0, "8", "1").status_code == 400
    assert _edit(client, 5, "a", FIXED).status_code == 400


def test_a_new_upload_forgets_every_edit(client):
    upload_marc(client, _file([("a", TYPO)]))
    _edit(client, 0, "a", FIXED)
    upload_marc(client, _file([("a", TYPO)]))

    row = client.post("/api/review-index", json={}).get_json()["records"][0]
    assert row["edited"] == []
    assert _preview(client)["source_866"] == TYPO
