"""
The session log: what a session found, for the cataloguer to take back to
the ILS or MarcEdit, where the Workbench's row numbers mean nothing.

One line per thing to look at, each naming the record by position, by the
identifier chosen at upload and by title, with the statement concerned and
what was said. Built from the run summary, so it describes the file the
Download button hands over. A CSV with a byte-order mark, because it is
meant to be opened in Excel and Excel on Windows misreads UTF-8 without one.
"""

from __future__ import annotations

import csv
import io

from pymarc import Field, MARCWriter, Record, Subfield

from conftest import upload_marc


def _file() -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    specs = [
        [("866", " 0", [("a", "v. 1-5 (1990-1994)")])],                     # clean
        [("866", " 0", [("a", "v. 5 no. 1-v. 8 no. 2 (Fal 1995-Fall 1999)")])],
        [("866", " 0", [("a", "nothing here to read")])],                   # not converted
        [("853", "20", [("8", "1"), ("a", "v."), ("i", "(year)")]),
         ("863", "40", [("8", "1.1"), ("a", "1"), ("i", "1990")]),
         ("866", " 0", [("a", "v. 1 (1990)")])],                            # kept
        [("866", " 0", [("a", "v. 9 (1998)")])],                            # skipped
    ]
    for n, fields in enumerate(specs):
        rec = Record()
        rec.leader = "00522cy  a22001453n 4500"
        rec.add_field(Field(tag="001", data=f"id-{n + 1}"))
        rec.add_field(Field(tag="245", indicators=["0", "0"],
                            subfields=[Subfield("a", f"Journal {n + 1} –")]))
        for tag, ind, subs in fields:
            rec.add_field(Field(tag=tag, indicators=list(ind),
                                subfields=[Subfield(c, v) for c, v in subs]))
        rec.add_field(Field(tag="999", indicators=[" ", " "],
                            subfields=[Subfield("b", f"99{n + 1}")]))
        writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def _log(client) -> list:
    response = client.get("/api/download-log")
    assert response.status_code == 200, response.get_data()
    assert response.data.startswith(b"\xef\xbb\xbf"), "Excel needs the BOM"
    assert "holdings_log_" in response.headers["Content-Disposition"]
    return list(csv.reader(io.StringIO(response.data.decode("utf-8-sig"))))


def test_there_is_no_log_before_anything_is_converted(client):
    upload_marc(client, _file())
    assert client.get("/api/download-log").status_code == 404


def test_every_kind_of_line_names_its_record(client):
    upload_marc(client, _file())
    client.post("/api/edit-866", json={"record_index": 1, "field_index": 0,
                                       "code": "a", "value": "v. 5 no. 1-v. 8 no. 2 (Fall 1995-Fall 1999)"})
    client.post("/api/batch-convert", json={"skip_records": [4],
                                            "indicators": ["9", "1"]})
    rows = _log(client)

    assert rows[0] == ["Record", "Identifier", "Title", "What", "866", "Details"]
    by_what = {}
    for row in rows[1:]:
        by_what.setdefault(row[3], []).append(row)

    assert set(by_what) == {"Setting refused", "Edited by you", "Not converted",
                            "Kept: already has 863s", "Skipped"}
    assert by_what["Setting refused"][0][:3] == ["", "", ""]
    assert by_what["Edited by you"][0][:3] == ["2", "992", "Journal 2 –"]
    assert by_what["Not converted"][0][4] == "nothing here to read"
    assert by_what["Kept: already has 863s"][0][0] == "4"
    assert by_what["Skipped"][0][0] == "5"
    assert not any(row[0] == "1" for row in rows[1:]), (
        "a record with nothing to say has no line")


def test_it_describes_what_the_download_holds_after_a_record_converted_alone(client):
    upload_marc(client, _file())
    client.post("/api/convert-record", json={
        "record_index": 2, "conversions": [{"text": "nothing here to read"}]})
    rows = _log(client)
    assert [r[3] for r in rows[1:]] == ["Not converted"]
    assert rows[1][0] == "3"
