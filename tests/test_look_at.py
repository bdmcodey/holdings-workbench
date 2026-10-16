"""
Statements to look at: listed on the card, every one, and filtered by kind.

Raised on 0.42.0, testing with the real export: a card read "224 statements,
6 held", and the six could not be found from it -- a card shows its first 25
examples, and the list of outcomes was for pasted statements only. "If they
are called out at this step, the fix needs to be able to be applied at this
step." And the line counting them across the step was hard to read. The
statements here are made up.
"""

from __future__ import annotations

import io

from pymarc import Field, MARCWriter, Record, Subfield

from conftest import REPO_ROOT, upload_marc

PAGE = (REPO_ROOT / "marc_serials" / "templates" / "tool.html").read_text(encoding="utf-8")
HELD = "v. 9 no. 1 - v. 12 no. 4 (Jan 1971 - Fall 1974)"   # months to seasons


def _plain(n):
    return f"v. {n} no. 1 - v. {n} no. 4 (Jan {1900 + n} - Dec {1900 + n})"


def _file(statements):
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for n, text in enumerate(statements):
        rec = Record()
        rec.leader = "00522cy  a22001453n 4500"
        rec.add_field(Field(tag="001", data=f"look-{n}"))
        rec.add_field(Field(tag="866", indicators=[" ", "0"], subfields=[Subfield("a", text)]))
        writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def test_a_held_statement_past_the_examples_shown_is_listed_with_its_record(client):
    statements = [_plain(n) for n in range(30)] + [HELD]
    upload_marc(client, _file(statements))
    data = client.post("/api/detect", json={"statements": statements,
                                            "split_multi_range": False}).get_json()
    (group,) = [g for g in data["groups"] if HELD in g["examples"]]
    assert group["examples_shown"] == 25 and group["examples"].index(HELD) >= 25
    (row,) = group["to_look_at"]
    assert row["text"] == HELD and row["kinds"] == ["held"]
    assert row["source"]["record_index"] == 30 and row["source"]["field_index"] == 0
    assert row["records"] == [30]
    assert group["look_at_records"] == [30]
    assert group["held"] == 1


def test_every_statement_is_counted_not_the_first_two_hundred(client):
    statements = [_plain(n) for n in range(210)] + [HELD]
    data = client.post("/api/detect", json={"statements": statements,
                                            "split_multi_range": False}).get_json()
    (group,) = [g for g in data["groups"] if HELD in g["examples"]]
    assert group["held"] == 1


def test_one_statement_can_be_listed_under_two_kinds(client):
    data = client.post("/api/detect", json={"statements": ["v. 15 (1998 Buyers Guide)"],
                                            "pasted": True}).get_json()
    (row,) = data["groups"][0]["to_look_at"]
    assert row["kinds"] == ["to_check", "left_out"]


def test_the_card_lists_them_with_edit_and_split():
    assert "${lookAtHtml(group, idx)}" in PAGE
    row = PAGE[PAGE.index("function lookRowHtml("):PAGE.index("function lookAction(")]
    assert "onclick=\"lookAction(this, 'edit')\"" in row
    assert "onclick=\"lookAction(this, 'split')\"" in row
    # Left out is a filter, not something to look at by default.
    assert "lookFilter === 'all' ? ['held', 'to_check', 'unread'] : [lookFilter]" in PAGE
    # And the card can narrow step 3 to the records to look at.
    assert "button('look', `Show the ${plural(look)} to look at`, look)" in PAGE


def test_the_step_has_buttons_by_kind_in_place_of_the_sentence():
    assert "function outcomeSentence(" not in PAGE
    assert "${lookChipsHtml(data.groups)}" in PAGE
    assert "if (lookFilter !== 'all') {" in PAGE
    assert "with statements to look at`" in PAGE
