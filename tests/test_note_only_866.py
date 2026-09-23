"""
An 866 with no $a -- a note on its own, "$z Current issues in reading room" --
is ordinary in an ILS export, and it took the whole file down.

pymarc raises KeyError for field["a"] when there is no $a. The upload read
866s with .get() and was fine, so the list appeared and "All" showed every
record; but the review index, the previews and "Convert all" read field["a"],
failed on that record, and failed the file with it. The screen showed "0
match" under every filter but All, and the failure went only to the console.
"""

from __future__ import annotations

import io

from pymarc import Field, MARCReader, MARCWriter, Record, Subfield

from conftest import upload_marc


def _file() -> bytes:
    rec = Record()
    rec.leader = "00522cy  a22001453n 4500"
    rec.add_field(Field(tag="001", data="note-only"))
    rec.add_field(Field(tag="866", indicators=[" ", "0"],
                        subfields=[Subfield("z", "Current issues in reading room")]))
    rec.add_field(Field(tag="866", indicators=[" ", "0"],
                        subfields=[Subfield("a", "v. 1-5 (1990-1994)")]))
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def test_a_note_only_866_does_not_stop_the_record_being_read(client):
    upload_marc(client, _file())

    index = client.post("/api/review-index", json={})
    assert index.status_code == 200, index.get_data()
    assert index.get_json()["records"][0]["sources"] == ["parser"]

    for route, body in (("/api/preview-records", {"indices": [0]}),
                        ("/api/preview-record", {"record_index": 0})):
        response = client.post(route, json=body)
        assert response.status_code == 200, (route, response.get_data())


def test_it_is_converted_around_and_kept(client):
    upload_marc(client, _file())
    response = client.post("/api/batch-convert", json={"remove_866": True})
    assert response.status_code == 200, response.get_data()

    with client.get("/api/download-converted") as got:
        record = list(MARCReader(got.data))[0]
    assert [f.get("a") for f in record.get_fields("863")] == ["1-5"]
    assert [f.get_subfields("z") for f in record.get_fields("866")] == [
        ["Current issues in reading room"]], "the note-only 866 is kept as it was"
