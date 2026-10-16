"""
Editing an 866 from the Patterns step.

Raised on 0.40.0: a statement's mistake -- a comma missing between runs, a
stray hyphen -- is seen on the Patterns step, and correcting it meant finding
the record again in step 3. The card now edits it in place, through the same
store step 3 uses. Asked of the cataloguer and answered: the edit is this
record's, with a box, unticked, to make it on the other records whose 866
reads exactly the same.
"""

from __future__ import annotations

import io

from pymarc import Field, MARCWriter, Record, Subfield

from conftest import REPO_ROOT, upload_marc

BROKEN = "v. 21-26, 29-31 33 (1921-25, 1928-30)"
FIXED = "v. 21-26, 29-31, 33 (1921-25, 1928-30, 1932)"


def _file(*statements_per_record) -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for n, statements in enumerate(statements_per_record):
        rec = Record()
        rec.leader = "00522cy  a22001453n 4500"
        rec.add_field(Field(tag="001", data=f"rec-{n}"))
        for text in statements:
            rec.add_field(Field(tag="866", indicators=[" ", "0"],
                                subfields=[Subfield("a", text)]))
        writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def _sources(client, text):
    data = client.post("/api/detect", json={"statements": [text],
                                            "split_multi_range": False}).get_json()
    for group in data["groups"]:
        for example, source in zip(group["examples"], group["example_sources"]):
            if example == text:
                return source
    raise AssertionError(f"{text!r} not found")


def test_a_card_knows_the_whole_866_and_how_many_records_share_it(client):
    upload_marc(client, _file([BROKEN], ["v. 1 (1990)", BROKEN], [BROKEN + " "]))
    source = _sources(client, BROKEN)
    assert source["record_index"] == 0 and source["field_index"] == 0
    assert source["source_866"] == BROKEN
    assert source["same_866"] == 2          # the other two records, spaces aside


def test_edit_changes_this_record_only_unless_asked(client):
    upload_marc(client, _file([BROKEN], ["v. 1 (1990)", BROKEN]))
    body = client.post("/api/edit-866", json={
        "record_index": 0, "field_index": 0, "code": "a", "value": FIXED}).get_json()
    assert "also" not in body
    assert body["fields_866"][0]["a"] == FIXED
    assert body["statements"].count(BROKEN) == 1


def test_edit_can_make_the_same_change_on_records_that_read_the_same(client):
    upload_marc(client, _file([BROKEN], ["v. 1 (1990)", BROKEN], ["v. 2 (1991)"]))
    body = client.post("/api/edit-866", json={
        "record_index": 0, "field_index": 0, "code": "a", "value": FIXED,
        "same_text": True}).get_json()
    (other,) = body["also"]
    assert other["record_index"] == 1
    assert [f["a"] for f in other["fields_866"]] == ["v. 1 (1990)", FIXED]
    assert BROKEN not in body["statements"]
    # Each is its own edit: listed on its record, and put back on its own.
    assert other["edited"]
    client.post("/api/edit-866", json={"record_index": 1, "field_index": 1,
                                       "code": "a", "revert": True})
    back = client.post("/api/detect", json={"split_multi_range": False}).get_json()
    examples = [e for g in back["groups"] for e in g["examples"]]
    assert BROKEN in examples and FIXED in examples


def test_an_edited_statement_still_leads_back_to_its_record(client):
    # Until 0.41.0 the Patterns step read the file as uploaded, so a corrected
    # statement had no record behind it on its card.
    upload_marc(client, _file(["v. 1 (1990)"], [BROKEN]))
    client.post("/api/edit-866", json={"record_index": 1, "field_index": 0,
                                       "code": "a", "value": FIXED})
    source = _sources(client, FIXED)
    assert source["record_index"] == 1 and source["source_866"] == FIXED


def test_the_card_offers_edit_and_the_box_starts_unticked():
    page = (REPO_ROOT / "marc_serials" / "templates" / "tool.html").read_text(
        encoding="utf-8")
    assert 'class="btn btn-secondary btn-sm ex-edit"' in page
    assert '<input type="checkbox" class="ex-edit-same"' in page
    assert 'class="ex-edit-same" checked' not in page
    assert "value, same_text: !!(same && same.checked) });" in page
