"""
Lists of months or seasons with no numbering, and lists of volumes paired with
lists of years.

"(Mar, May, Jul 1995)" states its year once, at the end, for every month in
it -- as "v. 19 nos. 1, 3, 5 (Jan, Mar, May 1915)" does, which has been read
since the distributed-list work. Without numbering in front, until 0.40.0 the
list was held with a reason that misdescribed it ("not something a year
subfield can hold"): 9 statements of the real export. And "v. 4-6, 9
(1951-53, 1956/57)" pairs runs of volumes with runs of years, but a year
written short, "1951-53", stopped the list being read at all.

The statements here are made up, in the shapes the export has.
"""

from __future__ import annotations

import pytest

from marc_serials.converter import convert_holdings
from marc_serials.parser import parse_866


def _863s(statement):
    rc = convert_holdings(parse_866(statement))
    return [" ".join(f"${sf.code} {sf.value}" for sf in f.subfields if sf.code != "8")
            for f in rc.fields_863], rc


@pytest.mark.parametrize("statement, expected", [
    ("(Mar, May, Jul 1995)",
     ["$i 1995 $j 03 $w g", "$i 1995 $j 05 $w g", "$i 1995 $j 07"]),
    ("(Jan, Mar-May, Sep, Oct 1982)",
     ["$i 1982 $j 01 $w g", "$i 1982 $j 03-05 $w g", "$i 1982 $j 09", "$i 1982 $j 10"]),
    ("(Jan-May, Sep-Nov 1983)", ["$i 1983 $j 01-05 $w g", "$i 1983 $j 09-11"]),
    ("(Spring, Winter 2004)", ["$i 2004 $j 21 $w g", "$i 2004 $j 24"]),
    # A year of its own on each part still wins over the one carried back.
    ("(Nov, Dec 1915, Jan 1916)", ["$i 1915 $j 11", "$i 1915 $j 12", "$i 1916 $j 01"]),
])
def test_a_year_stated_once_is_every_runs_year(statement, expected):
    fields, rc = _863s(statement)
    assert fields == expected
    assert not rc.needs_review and not rc.flagged


def test_no_gap_is_written_between_months_that_follow_on():
    # Sep then Oct, Nov then Dec, Dec then Jan of the next year: nothing between.
    fields, _ = _863s("(Jan, Mar-May, Sep, Oct 1982)")
    assert fields[2] == "$i 1982 $j 09"
    fields, _ = _863s("(Nov, Dec 1915, Jan 1916)")
    assert not any("$w" in f for f in fields)


def test_months_and_seasons_in_one_list_are_still_held():
    rc = convert_holdings(parse_866("(May, Jul, Spring 1994)"))
    assert rc.needs_review and rc.fields_863 == []
    assert rc.chron_switch["where"] == "within"


@pytest.mark.parametrize("statement", [
    "(Apr 18, 1996)",            # one date, written the American way
    "(Oct 1969-May/Jun 1984)",   # one run, no comma
])
def test_one_date_is_not_a_list(statement):
    assert len(parse_866(statement).ranges) == 1


def test_months_in_no_year_are_still_not_written():
    rc = convert_holdings(parse_866("(Feb, Jun, Aug)"))
    assert rc.needs_review and rc.fields_863 == []


@pytest.mark.parametrize("statement, expected", [
    ("v. 4-6, 9, 12-14, 20-35 (1951-53, 1956/57, 1960-62, 1968-83)",
     ["$a 4-6 $i 1951-1953 $w g", "$a 9 $i 1956/1957 $w g",
      "$a 12-14 $i 1960-1962 $w g", "$a 20-35 $i 1968-1983"]),
    ("v. 1-3, 5 (1990-92, 1994)", ["$a 1-3 $i 1990-1992 $w g", "$a 5 $i 1994"]),
])
def test_runs_of_volumes_pair_with_runs_of_years_written_short(statement, expected):
    fields, rc = _863s(statement)
    assert fields == expected
    assert not rc.needs_review


@pytest.mark.parametrize("statement", [
    # Four volume runs against three year runs: not understood, so nothing.
    "v. 1-3, 5, 7-9, 11 (1990-92, 1994, 1996-98)",
    # A comma missing between two volumes: the list is not a list.
    "v. 49-54, 57-59 61, 63 (1949-53, 1956-58, 1960)",
])
def test_a_list_that_does_not_pair_is_not_read(statement):
    rc = convert_holdings(parse_866(statement))
    assert rc.fields_863 == []
