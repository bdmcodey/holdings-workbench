"""
Values read correctly and left out because MARC has no place for them.

"v. 8 no. 3-v. 10 no. 2 (1981-Fall 1983)": the parser reads the Fall, and a
compressed 863 cannot say a season at one end of a range only, so it is left
out. Until 0.34.0 that was a yellow note among notes -- the same as a brace note
set aside -- and on a pasted statement it was folded away under "nothing to
decide". It is its own kind of thing: not lost in conversion, not misread, but
dropped to conform. The screen and the log now call it "left out to fit MARC",
and a setting decides whether such a statement converts, is held, or leaves its
whole record as uploaded.
"""

from __future__ import annotations

import csv
import io

import pytest
from pymarc import Field, MARCWriter, MARCReader, Record, Subfield

from conftest import REPO_ROOT, upload_marc
from marc_serials.converter import convert_holdings
from marc_serials.parser import LeftOut, parse_866

FALL = "v. 8 no. 3-v. 10 no. 2 (1981-Fall 1983)"


# ---------------------------------------------------------------------------
# Which warnings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    FALL,                                      # a season at one end only
    "2016?",                                   # a qualifier an 863 cannot hold
    "v. 1 (1973)-v. 11 no. 9 (Sep 1983)",      # a level at one end only
    "v. 40-45 no. 4 (1974-Apr 1979)",          # a level under a range
])
def test_a_value_read_and_left_out_is_named_as_such(text):
    conversion = convert_holdings(parse_866(text))
    assert conversion.fields_863
    assert conversion.left_out
    assert all(isinstance(w, LeftOut) and w in conversion.warnings
               for w in conversion.left_out)


@pytest.mark.parametrize("text", [
    "1993: {Memorial Issue} (1 [Feb])",        # a note, set aside as a note
    "N 1994: (2 [Mar])",                       # a marker nobody can read
    "v.1(1990)-v.5(1994)",                     # nothing left out at all
])
def test_notes_and_unread_markers_are_not(text):
    assert convert_holdings(parse_866(text)).left_out == []


def test_wording_a_coded_subfield_cannot_hold_is_both():
    """Left out, and still a decision: "Late Summer" may be its own issue."""
    conversion = convert_holdings(parse_866("no.56(2003:Dec./2004:Jan.)"))
    assert conversion.left_out
    assert set(conversion.left_out) <= set(conversion.attention)


# ---------------------------------------------------------------------------
# The setting
# ---------------------------------------------------------------------------

def _file() -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for n, statements in enumerate([[FALL, "v. 27 no. 4-v. 31 no. 4 (April 1992-April 1996)"],
                                    ["v. 1-5 (1990-1994)"]]):
        rec = Record()
        rec.leader = "00522cy  a22001453n 4500"
        rec.add_field(Field(tag="001", data=f"id-{n + 1}"))
        rec.add_field(Field(tag="245", indicators=["0", "0"],
                            subfields=[Subfield("a", f"Journal {n + 1}")]))
        for text in statements:
            rec.add_field(Field(tag="866", indicators=[" ", "0"],
                                subfields=[Subfield("a", text)]))
        writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def _row(client, policy):
    return client.post("/api/review-index",
                       json={"left_out_policy": policy}).get_json()["records"][0]


def _converted(client, policy):
    assert client.post("/api/batch-convert",
                       json={"left_out_policy": policy}).status_code == 200
    out = list(MARCReader(io.BytesIO(client.get("/api/download-converted").data)))
    log = list(csv.reader(io.StringIO(
        client.get("/api/download-log").data.decode("utf-8-sig"))))
    return out, log


def test_by_default_it_converts_and_says_so(client):
    upload_marc(client, _file())
    row = _row(client, "convert")
    assert row["converted"] == 2 and row["left_out"] == 1
    out, log = _converted(client, "convert")
    assert len(out[0].get_fields("863")) == 2
    assert any(r[3] == "Converted, part left out" and r[4] == FALL for r in log)


def test_holding_the_statement_converts_the_rest_without_a_gap(client):
    upload_marc(client, _file())
    row = _row(client, "statement")
    assert row["converted"] == 1 and row["held"] == 1 and row["left_out"] == 0
    out, log = _converted(client, "statement")
    f863 = out[0].get_fields("863")
    assert [f.get("8") for f in f863] == ["1.1"], "linking numbers run on"
    assert [f.get("a") for f in out[0].get_fields("866")] == [
        FALL, "v. 27 no. 4-v. 31 no. 4 (April 1992-April 1996)"]
    assert any(r[3] == "Not converted" and r[4] == FALL
               and "Held by your setting" in r[5] for r in log)


def test_leaving_the_record_writes_nothing_to_it(client):
    uploaded = _file()
    upload_marc(client, uploaded)
    row = _row(client, "record")
    assert row["left_as_uploaded"] and row["left_as_uploaded"][0]["text"] == FALL
    out, log = _converted(client, "record")
    original = list(MARCReader(io.BytesIO(uploaded)))
    assert out[0].as_marc() == original[0].as_marc()
    assert out[1].get_fields("863"), "the other record still converts"
    assert any(r[3] == "Left as uploaded" and r[4] == FALL for r in log)


def test_a_pattern_group_says_how_many_lose_something(client):
    groups = client.post("/api/detect", json={"statements": [FALL]}).get_json()["groups"]
    assert groups[0]["left_out"] == 1


def test_the_page_carries_the_setting_and_says_it():
    page = (REPO_ROOT / "marc_serials" / "templates" / "tool.html").read_text(
        encoding="utf-8")
    assert "left_out_policy: document.getElementById('opt-left-out').value" in page
    assert "<strong>Left out to fit MARC:</strong>" in page
    assert 'data-filter="leftout"' in page
    assert "(entry.left_as_uploaded || []).length > 0" in page
