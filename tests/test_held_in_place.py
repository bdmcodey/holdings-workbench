"""
Held statements where they come, and a card that says so while folded.

Raised on 0.41.0, testing with the real export:

- A card whose statement the standard parser cannot read -- a list with a
  comma missing -- showed nothing yellow while folded, so nothing said there
  was a statement to look at.
- In a card's preview of the record, held statements were gathered into a
  "Held for review" block after everything else, with no Edit or Split.
- Editing from a card folded step 2 away once its last question was
  answered, mid-task.

The statements here are made up.
"""

from __future__ import annotations

import io

from pymarc import Field, MARCWriter, Record, Subfield

from conftest import REPO_ROOT, upload_marc

BROKEN = "v. 21-26, 29-31 33, 35, 37-38-(1921-25,1928-30,1932,1935,1937-38)"
PAGE = (REPO_ROOT / "marc_serials" / "templates" / "tool.html").read_text(encoding="utf-8")


def test_a_card_counts_what_the_parser_cannot_read(client):
    data = client.post("/api/detect", json={"statements": [BROKEN, "v. 1 (1990)"],
                                            "pasted": True,
                                            "split_multi_range": False}).get_json()
    by_example = {g["examples"][0]: g for g in data["groups"]}
    assert by_example[BROKEN]["unread"] == 1
    assert by_example["v. 1 (1990)"]["unread"] == 0
    # Where reading stopped is in the outcome, for the note on the card.
    (outcome,) = by_example[BROKEN]["example_outcomes"]
    assert any("could not account for" in w for w in outcome["warnings"])


def test_the_folded_card_says_it_and_where_reading_stopped():
    assert "${group.unread} not read</span>" in PAGE
    assert "${unreadNoteHtml(group)}" in PAGE
    assert "such as a comma missing '" in PAGE


def _file():
    rec = Record()
    rec.leader = "00522cy  a22001453n 4500"
    rec.add_field(Field(tag="001", data="held-in-place"))
    for text in ["v. 1 no. 1-v. 3 no. 4 (Jan 1990-Dec 1992)", "(Sep 1993 - Winter 1993)",
                 "v. 5 no. 1-v. 6 no. 4 (Jan 1994-Dec 1995)"]:
        rec.add_field(Field(tag="866", indicators=[" ", "0"],
                            subfields=[Subfield("a", text)]))
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def test_a_cards_preview_says_which_866_each_statement_is(client):
    upload_marc(client, _file())
    data = client.post("/api/pattern-preview", json={
        "regex": r"(?i)^\(\s*(?P<start_month>[A-Za-z]+)\s*(?P<start_year>\d{4})\s*-\s*"
                 r"(?P<end_month>[A-Za-z]+)\s*(?P<end_year>\d{4})\s*\)$",
        "roles": [{"group": "start_month", "boundary": "start", "kind": "month"},
                  {"group": "start_year", "boundary": "start", "kind": "year"},
                  {"group": "end_month", "boundary": "end", "kind": "month"},
                  {"group": "end_year", "boundary": "end", "kind": "year"}],
        "record_index": 0, "field_index": 1,
        "statements": ["(Sep 1993 - Winter 1993)"]}).get_json()
    assert data["scope"] == "record"
    assert [pv["field_index"] for pv in data["previews"]] == [0, 1, 2]
    held = data["previews"][1]
    assert held["needs_review"] and held["is_example"]


def test_held_statements_come_where_they_are_with_edit_and_split():
    assert "Held for review</span>" not in PAGE
    # One renderer for the card's preview and step 3's record, in 866 order.
    assert "inRecordOrder(data.previews).map(" in PAGE   # the card's preview
    assert "inRecordOrder(previews).map(" in PAGE        # the record, in step 3
    held = PAGE[PAGE.index("function heldRowsHtml("):PAGE.index("function heldAction(")]
    assert "onclick=\"heldAction(this, 'edit')\"" in held
    assert "onclick=\"heldAction(this, 'split')\"" in held


def test_an_edit_or_split_leaves_step_two_as_it_was():
    after = PAGE[PAGE.index("async function after866Change("):]
    assert "await runDetect({ keepFold: true });" in after[:1200]
    assert "if (!keepFold) {" in PAGE
