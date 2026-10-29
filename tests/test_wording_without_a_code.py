"""
Wording MARC has no code for: what is still written, and what the cataloguer is told.

The cataloguer's position, which MARC 21 bears out: what to do with "Late
Summer", "Third Quarter" or "Buyers Guide" is theirs to decide -- keep the
866 to show it, or encode it by their own judgement. The standard allows a
month or season in words (863-865 $i-$m), has $o Title of unit for a named
issue ("annual buyer's guide" is its own example), and provides the 866 "in
addition to" the 863s for display (866-868).

Until 0.47.0 two things were wrong. The message said such a subfield "takes
MARC codes, not wording", which MARC 21 does not say. And wording beside the
year cost the 863 its year: "(1st Quarter 1980-4th Quarter 1981)" came out
with no $i, as did 4 of the 8 such statements on the real export, and MARC 21's
own example "no.56(2003:Dec./2004:Jan.)" came out "$a56" where LC writes
"$a56 $i2003/2004". Statements here are made up, in the shapes found.
"""

from __future__ import annotations

import pytest

from marc_serials.converter import convert_holdings
from marc_serials.parser import parse_866


def _863(statement):
    rc = convert_holdings(parse_866(statement))
    return rc, ["".join(f"${sf.code}{sf.value}" for sf in f.subfields
                        if sf.code != "8") for f in rc.fields_863]


@pytest.mark.parametrize("statement, written", [
    ("v. 2 no. 1-v. 3 no. 4 (1st Quarter 1980-4th Quarter 1981)", "$a2-3$b1-4$i1980-1981"),
    ("v. 9 no. 7 (July 2010 Addendum)", "$a9$b7$i2010"),
    ("v. 40 no. 1 (1st Quarter/Winter 1985)", "$a40$b1$i1985"),
    ("v.1:no.1(1907:1st quarter)-v.29:no.4(1935:4th quarter)", "$a1-29$b1-4$i1907-1935"),
    # Read before, and unchanged.
    ("v. 8 no. 3 (Third Quarter 1991)", "$a8$b3$i1991"),
    ("v. 15 (1998 Buyers Guide)", "$a15$i1998"),
])
def test_the_year_is_written_whatever_the_wording_beside_it(statement, written):
    rc, fields = _863(statement)
    assert fields == [written]
    assert rc.flagged, "the wording left out is still for the cataloguer to decide"


def test_marc_21s_own_example_across_two_years_is_written_as_lc_writes_it():
    rc, fields = _863("no.56(2003:Dec./2004:Jan.)")
    assert fields == ["$a56$i2003/2004"]
    assert rc.flagged
    assert any("one issue dated across two years" in w for w in rc.warnings)


@pytest.mark.parametrize("statement, written", [
    # Before 0.47.0: "$i1980" and "$i1985" -- one year for a run of three, or
    # of two, and nothing naming the years that went.
    ("v. 10 no. 1-v. 11 no. 2 (Spring 1980-Fall 1981/Winter 1982)",
     "$a10-11$b1-2$i1980-1981/1982"),
    ("v. 3 no. 2-v. 4 no. 1 (Fall 1984/Winter 1985-Summer/Fall 1985)",
     "$a3-4$b2-1$i1984/1985-1985"),
])
def test_a_run_ending_or_starting_across_two_years_keeps_all_its_years(statement, written):
    rc, fields = _863(statement)
    assert fields == [written]
    assert rc.flagged


def test_a_season_with_a_code_still_converts_as_it_did():
    assert _863("v. 30 no. 2 (Summer 2001)")[1] == ["$a30$b2$i2001$j22"]


def _message(statement):
    rc = convert_holdings(parse_866(statement))
    (note,) = [w for w in rc.warnings if "keep the 866" in w]
    return note


def test_the_message_no_longer_says_words_are_not_allowed():
    for statement in ("v. 4 no. 2 (Late Summer 1999)", "v. 8 no. 3 (Third Quarter 1991)",
                      "v. 15 (1998 Buyers Guide)"):
        note = _message(statement)
        assert "takes MARC codes, not wording" not in note
        assert "keep the 866 to show it as written" in note


def test_a_qualified_season_is_offered_its_code():
    note = _message("v. 4 no. 2 (Late Summer 1999)")
    assert "If it is the Summer issue, its code is 22" in note
    assert "in words" in note


def test_a_quarter_is_told_there_is_no_code():
    note = _message("v. 8 no. 3 (Third Quarter 1991)")
    assert "MARC 21 has no code for one" in note
    assert "issue number usually says which quarter" in note
    assert "Winter issue, its code is 24" in _message("v. 40 no. 1 (1st Quarter/Winter 1985)")


def test_a_named_issue_is_pointed_at_title_of_unit():
    note = _message("v. 15 (1998 Buyers Guide)")
    assert "$o, Title of unit" in note and "$z public note" in note


@pytest.mark.parametrize("statement", [
    "v. 4 no. 2 (Late Summer 1999)", "v. 8 no. 3 (Third Quarter 1991)",
    "v. 15 (1998 Buyers Guide)", "no.56(2003:Dec./2004:Jan.)",
])
def test_keeping_the_866_comes_with_its_caution(statement):
    # The workbench does not yet link a kept 866 to its 863s, and a system
    # that rebuilds 866s from the 863s -- Alma does -- may replace it. Until
    # the link can be tried in Alma, the advice says so wherever it is given.
    rc = convert_holdings(parse_866(statement))
    advice = [w for w in rc.warnings if "keep the 866" in w]
    assert advice and all("as Alma does, may replace it" in w for w in advice)
