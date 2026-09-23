"""
A cataloguer's own note on a record: for the log, never for the file.

Asked for by the cataloguer as a reminder to themselves or a colleague -- why
a record was skipped, what to check when it is opened in the ILS -- and
deliberately not $x or $z, which are written into the record. A record with a
note is in the log even when nothing else is wrong with it, and the note is
its first line there.
"""

from __future__ import annotations

import csv
import io
import re

from pymarc import Field, MARCReader, MARCWriter, Record, Subfield

from conftest import REPO_ROOT, upload_marc


def _file() -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for n, statement in enumerate(("v. 1-5 (1990-1994)", "v. 9 (1998)")):
        rec = Record()
        rec.leader = "00522cy  a22001453n 4500"
        rec.add_field(Field(tag="001", data=f"id-{n + 1}"))
        rec.add_field(Field(tag="866", indicators=[" ", "0"],
                            subfields=[Subfield("a", statement)]))
        writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def _note(client, index, text):
    return client.post("/api/record-note", json={"record_index": index, "note": text})


def _log(client) -> list:
    with client.get("/api/download-log") as got:
        assert got.status_code == 200, got.get_data()
        return list(csv.reader(io.StringIO(got.data.decode("utf-8-sig"))))[1:]


def test_a_note_rides_on_the_row_and_leads_the_record_in_the_log(client):
    upload_marc(client, _file())
    _note(client, 0, "Confirm the 1990 volume is on the shelf.")
    _note(client, 1, "Skipped: successor title, check in Alma first.")

    rows = client.post("/api/review-index", json={}).get_json()["records"]
    assert rows[0]["note"] == "Confirm the 1990 volume is on the shelf."

    client.post("/api/batch-convert", json={"skip_records": [1]})
    log = _log(client)

    # Record 1 converts cleanly and would have no line; the note gives it one.
    assert [r[3] for r in log if r[0] == "1"] == ["Your note"]
    assert [r[3] for r in log if r[0] == "2"] == ["Your note", "Skipped"]
    assert log[0][5] == "Confirm the 1990 volume is on the shelf."


def test_a_note_never_reaches_the_file(client):
    upload_marc(client, _file())
    _note(client, 0, "A reminder only.")
    client.post("/api/batch-convert", json={})

    with client.get("/api/download-converted") as got:
        record = list(MARCReader(got.data))[0]
    assert "A reminder only." not in str(record)


def test_an_empty_note_removes_it_and_a_new_upload_forgets_them(client):
    upload_marc(client, _file())
    _note(client, 0, "first")
    assert _note(client, 0, "   ").get_json()["note"] == ""
    assert client.post("/api/review-index", json={}).get_json()["records"][0]["note"] == ""

    _note(client, 0, "second")
    upload_marc(client, _file())
    assert client.post("/api/review-index", json={}).get_json()["records"][0]["note"] == ""


def test_a_note_for_a_record_that_is_not_there_is_refused(client):
    upload_marc(client, _file())
    assert _note(client, 9, "nowhere").status_code == 400


def test_ticking_skip_leaves_the_cursor_where_it_was():
    """
    0.25.0 opened a skipped record at its note box. The cataloguer found it got
    in the way of skipping several records in a row, and under "Needs
    attention" the record leaves the list, so there was nothing to open. The
    note is written from the record's detail, or from the Skipped filter.
    """
    script = (REPO_ROOT / "marc_serials" / "templates" / "tool.html").read_text(
        encoding="utf-8")
    handler = re.search(r"skipRecords\.add\(idx\).*?\}\)\);", script, re.S)
    assert handler, "the Skip handler has moved or been renamed"
    body = handler.group(0)
    assert ".focus()" not in body and "selectRecord(" not in body
