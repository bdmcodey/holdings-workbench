"""
The 853 settings chosen for one record: its $w, and captions for the levels its
statements leave blank.

How often a serial is published differs from title to title and no holdings
statement says it, so a file-wide $w was wrong for most of a file -- and until
0.33.0 the setting began at Annual, so every 853 said "$w a". A caption given
for one record reaches every statement on it, whatever its shape, which is what
lets two shapes of one serial share an 853 without deciding anything for any
other record.
"""

from __future__ import annotations

import csv
import io

import pymarc
from pymarc import Field, MARCWriter, Record, Subfield

from conftest import REPO_ROOT, upload_marc
from marc_serials.bridge import fill_record_captions, uncaptioned_levels
from marc_serials.converter import convert_record
from marc_serials.parser import parse_866


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------

def test_two_shapes_of_one_serial_share_an_853_once_captioned():
    results = [parse_866("34 no 3, 4 (Summer, Autumn 1990)"),
               parse_866("39 no 1 (Spring 1995)")]
    assert uncaptioned_levels(results) == [0]
    fill_record_captions(results, {"0": "v."})
    rc = convert_record(results)
    displays = {r.field_853.display() for r in rc.results if r.field_853}
    assert len(displays) == 1
    assert "$a v. $b no." in displays.pop()


def test_a_printed_caption_is_never_replaced():
    results = [parse_866("vol. 1 (1990)")]
    assert uncaptioned_levels(results) == []
    fill_record_captions(results, {"0": "no."})
    assert results[0].ranges[0].start.enum[0].caption == "v."   # as read, not "no."


# ---------------------------------------------------------------------------
# On screen, in the file and in the log
# ---------------------------------------------------------------------------

def _file() -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for n, statements in enumerate([
            ["34 no 3, 4 (Summer, Autumn 1990)", "39 no 1 (Spring 1995)"],
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


def _set(client, **body):
    return client.post("/api/record-853", json=body)


def _preview(client, index):
    return client.post("/api/preview-record", json={"record_index": index}).get_json()


def test_the_settings_reach_this_record_and_no_other(client):
    upload_marc(client, _file())
    before = _preview(client, 0)
    assert before["uncaptioned_levels"] == [0]
    assert "$a (*)" in before["previews"][0]["field_853"]

    response = _set(client, record_index=0, frequency="q", captions={"0": "v."})
    assert response.status_code == 200, response.get_json()

    after = _preview(client, 0)
    assert after["record_853"] == {"frequency": "q", "captions": {"0": "v."}}
    assert after["uncaptioned_levels"] == [0], "a level given a caption is still offered"
    for preview in after["previews"]:
        assert "$a v." in preview["field_853"] and "$w q" in preview["field_853"]

    other = _preview(client, 1)
    assert "$w" not in other["previews"][0]["field_853"]


def test_the_converted_file_and_the_log_carry_them(client):
    upload_marc(client, _file())
    _set(client, record_index=0, frequency="m", captions={"0": "v."})
    assert client.post("/api/batch-convert", json={}).status_code == 200

    out = list(pymarc.MARCReader(io.BytesIO(
        client.get("/api/download-converted").data)))
    f853 = out[0].get_fields("853")
    assert len(f853) == 1
    assert f853[0].get("a") == "v." and f853[0].get("w") == "m"
    assert out[1].get_fields("853")[0].get("w") is None

    log = list(csv.reader(io.StringIO(
        client.get("/api/download-log").data.decode("utf-8-sig"))))
    # No 999$b in this file, so no identifier.
    assert ["1", "", "Journal 1", "853 set by you", "",
            "$w m (Monthly); level 1 caption v."] in log


def test_going_back_to_the_file_setting_forgets_them(client):
    upload_marc(client, _file())
    _set(client, record_index=0, frequency="q", captions={"0": "v."})
    response = _set(client, record_index=0, frequency=None, captions={"0": ""})
    assert response.get_json()["record_853"] == {}
    assert _preview(client, 0)["record_853"] == {}


def test_not_specified_is_a_choice_of_its_own(client):
    upload_marc(client, _file())
    _set(client, record_index=0, frequency="")
    preview = _preview(client, 0)
    assert preview["record_853"] == {"frequency": ""}
    assert "$w" not in preview["previews"][0]["field_853"]


def test_what_is_not_an_853_setting_is_refused(client):
    upload_marc(client, _file())
    assert _set(client, record_index=0, frequency="x").status_code == 400
    assert _set(client, record_index=0, captions={"6": "v."}).status_code == 400
    assert _set(client, record_index=0, captions={"0": "$a v."}).status_code == 400
    assert _set(client, record_index=0, captions={"0": "x" * 21}).status_code == 400
    assert _set(client, record_index=9, frequency="q").status_code == 400
    assert _preview(client, 0)["record_853"] == {}


def test_the_file_setting_begins_at_not_specified(client):
    page = client.get("/").get_data(as_text=True)
    assert '<option value="" selected>(not specified)</option>' in page
    assert '<option value="a" >Annual</option>' in page


def test_the_record_shows_its_853_settings():
    page = (REPO_ROOT / "marc_serials" / "templates" / "tool.html").read_text(
        encoding="utf-8")
    assert "${record853Html(idx, about)}" in page
    assert "postJson('api/record-853'" in page
