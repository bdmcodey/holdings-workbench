"""
From a pattern to its records, and its expression off the screen.

Asked for by the cataloguer: the detected patterns said too little to review,
with each expression three clicks in and no way to copy it, and there was no
way to go from a pattern to the records it touches.

"The records a pattern runs on" is two sets, and the screen offers both where
they differ: the records *with this shape* (what the card's count describes,
known from detection) and the records a confirmed pattern *converts* (known
from the review index, which already records which pattern read each record).
On the real 372-record export one pattern converted 8 of the 18 records with
its shape -- larger patterns claim the rest first -- and another converted 31
against 29, because an expression can match a neighbouring shape too.
"""

from __future__ import annotations

import io
import re

from pymarc import Field, MARCWriter, Record, Subfield

from conftest import REPO_ROOT, upload_marc


def _file(*statements) -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for n, statement in enumerate(statements):
        rec = Record()
        rec.leader = "00522cy  a22001453n 4500"
        rec.add_field(Field(tag="001", data=f"shape-{n}"))
        rec.add_field(Field(tag="866", indicators=[" ", "0"],
                            subfields=[Subfield("a", statement)]))
        writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def _groups(client):
    return client.post("/api/detect", json={}).get_json()["groups"]


def test_every_record_with_the_shape_is_listed_not_only_the_first(client):
    """
    Detection used to remember one record per statement, for its examples. The
    same statement on three records is three records to show.
    """
    upload_marc(client, _file("v.1(1990)-v.3(1992)", "v. 9 (1998)",
                              "v.1(1990)-v.3(1992)", "V. 4 (1980)-v. 6 (1982)",
                              "v.1(1990)-v.3(1992)"))
    by_label = {g["human_label"]: g for g in _groups(client)}

    assert by_label["VOL(YEAR) — VOL(YEAR)"]["records"] == [0, 2, 3, 4]
    assert by_label["VOL(YEAR)"]["records"] == [1]


def test_a_split_statement_counts_its_record_once(client):
    upload_marc(client, _file("v.1(1990)-v.3(1992), v.5(1994)-v.7(1996)"))
    group = next(g for g in _groups(client)
                 if g["human_label"] == "VOL(YEAR) — VOL(YEAR)")
    assert group["records"] == [0]


def test_the_examples_do_not_carry_the_whole_list(client):
    """The example provenance stays what it was; the list is the group's."""
    upload_marc(client, _file("v.1(1990)-v.3(1992)", "v.1(1990)-v.3(1992)"))
    group = _groups(client)[0]
    assert all("records" not in (src or {}) for src in group["example_sources"])


def _page() -> str:
    return (REPO_ROOT / "marc_serials" / "templates" / "tool.html").read_text(
        encoding="utf-8")


def test_the_card_shows_its_expression_and_can_copy_it():
    """The screen half: the expression is outside the folded body, with Copy."""
    page = _page()
    card = re.search(r"function buildPatternCard.*?\n}\n", page, re.S).group(0)
    head, body = card.split('<div class="pc-body" hidden>', 1)
    assert 'class="pc-expr"' in head and "pc-copy" in head
    assert "btn-copy-all-regex" in page


def test_the_pattern_filter_reads_the_right_set_for_each_mode():
    page = _page()
    matcher = re.search(r"case 'one-pattern':.*?: patternFilter\.indexes\.has\(index\);",
                        page, re.S)
    assert matcher, "the one-pattern filter has moved or been renamed"
    assert "patternFilter.mode === 'converted'" in matcher.group(0)
    assert "entry.sources" in matcher.group(0)
