"""
Round the loop with the ILS: convert, regenerate the 866, convert again.

Asked for by the cataloguer as the check that closes the circle. Holdings are
exported from Alma, converted here, loaded back; Alma regenerates every 866
from the new 853/863s in Z39.71's form. Exported and converted again, those
866s must give the same 863s -- drift means a bug.

marc_serials.display imitates Alma's 866. It was written against the 48 866s
in a real export that Alma generated from hand-entered 863s, and reproduces
every one; the shapes below are theirs. Running the loop over the real
1,057-statement export first found (0.28.0):

    42 statements   "2003:Aug.-2004:Dec."  Z39.71 chronology, read by nothing
     9              an 863 with nothing in it but $8, written anyway
     2              "1986-1988," a gap after bare years, refused whole
     1              "$a 1 - 55", spaces kept inside a range
     1              "$j 10-10" beside "$j 10" -- equal months, one year

all fixed here, and one statement left: the "$b 1-3-10-12" the cataloguer
reported, which is its own decision.
"""

from __future__ import annotations

import sys

import pytest
from pymarc import Field, Subfield

from conftest import REPO_ROOT
from marc_serials.converter import convert_holdings
from marc_serials.display import (CAPTION_ONLY, DRIFT, NOT_CONVERTED, SAME,
                                  render_866, round_trip)
from marc_serials.parser import parse_866, _looks_like_block

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from corpus_report import load_corpus  # noqa: E402


def _field(tag, ind, text):
    subs = [Subfield(part[0], part[1:]) for part in text.split("$")[1:]]
    return Field(tag=tag, indicators=list(ind), subfields=subs)


def _863s(statement):
    rc = convert_holdings(parse_866(statement))
    return [" ".join(f"${sf.code} {sf.value}" for sf in f.subfields if sf.code != "8")
            for f in rc.fields_863]


# -- what Alma writes -----------------------------------------------------------

@pytest.mark.parametrize("f853, f863, alma", [
    # Shapes from the real export, each reproduced exactly.
    ("$81$av.$bno.$i(year)$j(month)", "$81.1$a44$b3$i1987$j05/06$wg",
     "v.44:no.3(1987:May/June),"),
    ("$81$av.$i(year)", "$81.3$a3$i1987-1988", "v.3(1987)-v.3(1988)"),
    ("$81$av.$i(year)$j(month)", "$81.1$a3-5$i1980-1982$j03-12$wg",
     "v.3(1980:Mar.)-v.5(1982:Dec.),"),
    ("$81$av.$bno.$i(year)$j(month)", "$81.3$a4$b9$i1993$j09$wg",
     "v.4:no.9(1993:Sept.),"),
    ("$82$a(year)$b(month)", "$82.1$a1986-1994", "1986-1994"),
    ("$82$av.$bno.$i(year)$j(season)", "$82.2$a24-84$b1-2$i1940-1991",
     "v.24:no.1(1940)-v.84:no.2(1991)"),
])
def test_the_866_is_written_as_alma_writes_it(f853, f863, alma):
    assert render_866(_field("853", "20", f853), _field("863", "40", f863)) == alma


# -- what the parser reads back -------------------------------------------------

@pytest.mark.parametrize("statement, fields", [
    ("1990:Jan.-1994:Dec.", ["$i 1990-1994 $j 01-12"]),
    ("1994:Winter/Spring-1999:Spring/Summer", ["$i 1994-1999 $j 24/21-21/22"]),
    ("2000:Spring/Summer", ["$i 2000 $j 21/22"]),
    ("1990:Jan.-", ["$i 1990- $j 01-"]),
    ("2014:Nov. 7", ["$i 2014 $j 11 $k 7"]),
    ("1986-1988,", ["$i 1986-1988 $w g"]),
    ("v.37-v.52,", ["$a 37-52 $w g"]),
])
def test_z39_71_forms_are_read(statement, fields):
    assert _863s(statement) == fields


def test_the_year_first_grammar_no_longer_claims_z39_71_chronology():
    assert not _looks_like_block("1990:Jan.-1994:Dec.")
    assert _looks_like_block("1993: (1 [Feb])")
    assert _looks_like_block("1949: 1 (1-6 [Apr-Sep])")


def test_a_run_with_nothing_writable_is_held_not_written_empty():
    rc = convert_holdings(parse_866("(Feb, Jun, Aug 1998)"))
    assert rc.fields_863 == [] and rc.needs_review
    assert any("no 863 was written" in w for w in rc.warnings)


def test_spaces_inside_a_range_are_not_written():
    assert _863s("v. 1 - 55 no. 3 (1927-1982)")[0].startswith("$a 1-55 ")


@pytest.mark.parametrize("statement, month", [
    ("v. 31 nos. 19-20 (Oct 7-Oct 21, 1993)", "$j 10 $k 7-21"),   # one year
    ("v. 1 (Jan 1956)-v. 2 (Jan 1957)", "$j 01-01"),              # D15: years range
])
def test_equal_months_collapse_only_where_the_year_does_not_range(statement, month):
    assert month in _863s(statement)[0]


# -- the loop ---------------------------------------------------------------------

@pytest.mark.parametrize("statement", [
    "v.1:no.1(1990:Jan.)-v.5:no.4(1994:Dec.)",
    "Vol. 1, No. 1 (Spring 1990)-Vol. 5, No. 4 (Winter 1994)",
    "v.1(1990)-v.3(1992), v.5(1994)-",
    "(Aug 2003-Dec 2004)",
    "(1986-1988, 1993-1994)",
    "v. 34 no. 8/9-v. 35 no. 23/24 (Apr 1996-Dec 1997)",
])
def test_a_statement_comes_back_as_it_went(statement):
    assert round_trip(statement)["outcome"] == SAME


def test_a_level_named_without_a_value_is_reported_apart():
    trip = round_trip("v. 1 (1973)-v. 11 no. 9 (Sep 1983)")
    assert trip["outcome"] == CAPTION_ONLY
    assert trip["first"][1] == trip["second"][1]


def test_the_lc_examples_do_not_drift():
    lc = load_corpus(REPO_ROOT / "data" / "lc_holdings_examples.txt")
    assert {round_trip(e.statement)["outcome"] for e in lc} <= {SAME, NOT_CONVERTED}


def test_corpus_drift_is_only_where_a_level_has_no_caption():
    """
    Five corpus statements do not come back: every one records a level with no
    caption, "(*)" in its 853 -- year-first statements and "8,13,15,...". The
    regenerated 866 is bare numbers, and nothing says what they count; the
    parser refuses to guess, as it should. A caption confirmed on the pattern
    closes the loop. Anything else drifting is new, and a bug.
    """
    drifted = []
    for entry in load_corpus():
        trip = round_trip(entry.statement)
        if trip["outcome"] == DRIFT:
            drifted.append(entry.statement)
            assert any(v == "(*)" for _, values in trip["first"][0]
                       for _, v in values), entry.statement
    assert len(drifted) == 5, drifted
