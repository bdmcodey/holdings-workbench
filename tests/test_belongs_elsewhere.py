"""
Supplements and indexes, and wording a confirmed pattern writes nowhere.

MARC 21 keeps supplementary material (854/864/867) and indexes (855/865/868)
apart from the basic run (853/863/866). An 866 saying "Suppl." or "Index" is
describing one of those, and 867/868 are out of scope for now -- so such a
statement is held, for a reason of its own that the screen and the log name.

Found in a demo dry run, October 2026: confirming the pre-filled pattern for
"v. 58 Suppl. (Sep 2003)" -- one click, nothing to decide -- wrote
"863 $a 58 $i 2003 $j 09". The record said "3 converted" and the log had no
line for it: "Suppl." was gone with nothing on screen to say so.
"""

from __future__ import annotations

import csv
import io
import re

import pytest
from pymarc import Field, MARCWriter, Record, Subfield

from conftest import REPO_ROOT, upload_marc
from marc_serials.bridge import (KIND_ENUM, KIND_UNRESOLVED, build_parse_result,
                                 infer_roles)
from marc_serials.converter import convert_holdings
from marc_serials.detector import detect_patterns
from marc_serials.parser import belongs_elsewhere, parse_866


def _confirmed(statement: str):
    """The statement's own pattern, every undecided value answered "enumeration"."""
    group = detect_patterns([statement])[0]
    compiled = re.compile(group.regex)
    roles = infer_roles(list(compiled.groupindex))
    for role in roles:
        if role.kind == KIND_UNRESOLVED:
            role.kind = KIND_ENUM
        role.suggested = False
    return compiled, roles


# ---------------------------------------------------------------------------
# Which statements
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, tag", [
    ("v. 58 Suppl. (Sep 2003)", "867"),
    ("v. 19 no. 2 Suppl. (1998)", "867"),
    ("Special Issue (October/November 1995)", "867"),
    ("v.1 Special no. 2 (1999)", "867"),
    ("Supplementary v.3 (2001)", "867"),
    ("v.1 suppl 2 (1999)", "867"),
    ("v.1-10 Index (1990-1999)", "868"),
    ("Indexes v.1-20", "868"),
    # An index to the supplements is an index.
    ("Suppl. index v.1-5", "868"),
])
def test_a_supplement_or_an_index_is_held_for_its_own_field(text, tag):
    result = parse_866(text)
    assert result.ranges == []
    assert result.success is False
    assert result.belongs_in == tag
    assert result.warnings[0].startswith("'"), "the reason to act on comes first"
    assert tag in result.warnings[0]


@pytest.mark.parametrize("text", [
    "v.1(1990)",
    "supplied v.1",                 # a word that begins like one
    "v.1(1990) {Index in v.5}",     # a note is a note, and is read around
])
def test_other_statements_are_not_taken_for_one(text):
    assert belongs_elsewhere(text.split("{")[0]) is None
    assert parse_866(text).belongs_in is None


def test_where_the_parser_stopped_is_still_said():
    """
    The supplement note is the reason to act on, but "Read 'v. 58' but could
    not account for 'Suppl. (Sep 2003)'" still says what the parser made of
    it, and the general "No recognisable holdings ranges found" line, which
    says less than either, is left off.
    """
    result = parse_866("v. 58 Suppl. (Sep 2003)")
    assert any("Read 'v. 58'" in w for w in result.warnings)
    assert not any(w.startswith("No recognisable holdings") for w in result.warnings)


# ---------------------------------------------------------------------------
# A confirmed pattern
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "v. 58 Suppl. (Sep 2003)",
    "v. 19 no. 2 Suppl. (1998)",
    "Special Issue (October/November 1995)",
])
def test_a_confirmed_pattern_does_not_convert_a_supplement(text):
    compiled, roles = _confirmed(text)
    result = build_parse_result(text, compiled, roles)
    assert result is not None and result.ranges == []
    conversion = convert_holdings(result)
    assert conversion.fields_863 == []
    assert conversion.belongs_in == "867"


@pytest.mark.parametrize("text, word", [
    ("?: 16", "?"),
    ("v.1// 1982//", "//"),
    ("2016 ed.", "ed."),
    ("1.1 9-12 1-4 2006-2009 Ceased with v.12 no.4 (2009)", "Ceased with"),
])
def test_wording_a_pattern_writes_nowhere_is_to_check(text, word):
    """
    A pattern spans free text with an anonymous slot, so a statement can match
    while words in it reach no field. Converted, and named as something to
    check -- never left to vanish.
    """
    compiled, roles = _confirmed(text)
    result = build_parse_result(text, compiled, roles)
    conversion = convert_holdings(result)
    assert conversion.fields_863
    assert conversion.flagged
    assert any(f"'{word}'" in w for w in conversion.attention), conversion.attention


def test_a_stray_full_stop_is_not_wording():
    compiled, roles = _confirmed("3.1 46-62 2001-2010 .")
    result = build_parse_result("3.1 46-62 2001-2010 .", compiled, roles)
    assert result.attention == []


# ---------------------------------------------------------------------------
# On screen and in the log
# ---------------------------------------------------------------------------

def _file() -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for n, statements in enumerate([["v. 1-5 (1990-1994)", "v. 58 Suppl. (Sep 2003)"],
                                    ["v.1-10 Index (1990-1999)"]]):
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


def test_the_record_says_where_it_belongs_and_needs_attention(client):
    upload_marc(client, _file())
    rows = client.post("/api/review-index", json={}).get_json()["records"]
    first, second = rows[0], rows[1]
    assert first["converted"] == 1 and first["held"] == 0
    assert first["elsewhere"] == ["867"]
    assert second["elsewhere"] == ["868"]


def test_the_log_names_the_field_to_move_it_to(client):
    upload_marc(client, _file())
    assert client.post("/api/batch-convert", json={}).status_code == 200
    response = client.get("/api/download-log")
    rows = list(csv.reader(io.StringIO(response.data.decode("utf-8-sig"))))
    what = {(r[4], r[3]) for r in rows[1:]}
    assert ("v. 58 Suppl. (Sep 2003)", "Supplement: belongs in 867") in what
    assert ("v.1-10 Index (1990-1999)", "Index: belongs in 868") in what


def test_a_pattern_of_supplements_asks_nothing(client):
    groups = client.post("/api/detect", json={
        "statements": ["v. 58 Suppl. (Sep 2003)"]}).get_json()["groups"]
    assert groups[0]["decides"] == "elsewhere"
    assert groups[0]["belongs_in"] == "867"
    assert groups[0]["needs_decision"] is False


def test_the_page_never_confirms_one_unasked_and_files_them_apart():
    page = (REPO_ROOT / "marc_serials" / "templates" / "tool.html").read_text(
        encoding="utf-8")
    assert "g.decides !== 'elsewhere'" in page, \
        "auto-confirm must not confirm a pattern that is held whatever is said"
    assert "parts.elsewhere.push(entry)" in page
    assert "(entry.elsewhere || []).length > 0" in page, \
        "a record holding one belongs under Needs attention"
    assert "${elsewhereHtml(elsewhere)}" in page
