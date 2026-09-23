"""
One record the tool cannot handle is said on its own row, not the whole file.

Found through a real one: an 866 with no $a raised KeyError in the review
row, /api/review-index answered 500 for all 372 records, and the screen --
holding no index -- showed "0 match" under every filter but All. That cause
is fixed; this is the guard against the next one, whatever it is.
"""

from __future__ import annotations

import io

from pymarc import Field, MARCReader, MARCWriter, Record, Subfield

from conftest import upload_marc
import marc_serials.webapp as webapp


BAD = "v. 13 (2013)"


def _file() -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for n, statement in enumerate(("v. 1-5 (1990-1994)", BAD, "v. 7 (1996)")):
        rec = Record()
        rec.leader = "00522cy  a22001453n 4500"
        rec.add_field(Field(tag="001", data=f"rec{n}"))
        rec.add_field(Field(tag="866", indicators=[" ", "0"],
                            subfields=[Subfield("a", statement)]))
        writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def _break_one_record(monkeypatch):
    real = webapp.convert_record

    def failing(parsed, *args, **kwargs):
        if any(p.raw == BAD for p in parsed):
            raise ValueError("simulated failure")
        return real(parsed, *args, **kwargs)
    monkeypatch.setattr(webapp, "convert_record", failing)


def test_the_list_still_reads_every_other_record(client, monkeypatch):
    upload_marc(client, _file())
    _break_one_record(monkeypatch)

    response = client.post("/api/review-index", json={})
    assert response.status_code == 200, response.get_data()
    rows = response.get_json()["records"]
    assert [r["sources"] for r in rows] == [["parser"], [], ["parser"]]
    assert rows[1]["unreadable"] is True
    assert "simulated failure" in rows[1]["record_notes"][0]

    preview = client.post("/api/preview-record", json={"record_index": 1})
    assert preview.status_code == 200


def test_convert_all_leaves_that_record_as_it_was_and_says_so(client, monkeypatch):
    upload_marc(client, _file())
    _break_one_record(monkeypatch)

    body = client.post("/api/batch-convert", json={"remove_866": True}).get_json()
    assert body["unreadable"] == 1
    assert body["converted_indexes"] == [0, 2]
    assert "could not be checked" in body["summary"][1]["warnings"][0]

    with client.get("/api/download-converted") as got:
        records = list(MARCReader(got.data))
    assert records[1].get_fields("863") == []
    assert [f.get("a") for f in records[1].get_fields("866")] == [BAD]
    assert records[0].get_fields("863") and records[2].get_fields("863")
