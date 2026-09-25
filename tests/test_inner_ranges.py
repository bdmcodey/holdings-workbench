"""
A range inside one end of the holdings.

Reported by the cataloguer:

    866 0  $a v. 6 nos. 1-3-v. 14 nos. 10-12 (Mar 1978-Oct-Dec 1986)
    863 40 $8 1.1 $a 6-14 $b 1-3-10-12 $i 1978

"$b 1-3-10-12" pairs with nothing, and the chronology was split at its first
hyphen, so the end year and every month went. MARC settles the first: a
compressed 863 holds the first part held and the last, one hyphen to a
subfield (LC's own example: "$a7 $b3-9 $i1979 $j03-12"), and Z39.71 writes a
combined part with a slash, a range with a hyphen. So "nos. 1-3" at the start
is issues 1 through 3, the run begins at no. 1, and the 863 is
"$a 6-14 $b 1-12 $i 1978-1986 $j 03-12". The one reading the notation cannot
settle -- a combined issue written with the wrong mark -- is the cataloguer's,
so the record is marked to check and says how to change it.

On the real 1,057-statement export this took the round trip from 1 drifting
statement to none, and gave two more statements their end years and months:
"(May 1992-Mar-Jun 1995)" and "(January-March 1963 - December/January 1984)".
"""

from __future__ import annotations

import sys

import pytest

from conftest import REPO_ROOT
from marc_serials.converter import convert_holdings
from marc_serials.display import SAME, round_trip
from marc_serials.parser import parse_866

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from corpus_report import load_corpus  # noqa: E402

REPORTED = "v. 6 nos. 1-3-v. 14 nos. 10-12 (Mar 1978-Oct-Dec 1986)"


def _convert(statement):
    rc = convert_holdings(parse_866(statement))
    fields = [" ".join(f"${sf.code} {sf.value}" for sf in f.subfields if sf.code != "8")
              for f in rc.fields_863]
    return fields, rc


def test_the_reported_statement_records_its_outer_ends_and_says_so():
    fields, rc = _convert(REPORTED)
    assert fields == ["$a 6-14 $b 1-12 $i 1978-1986 $j 03-12"]
    assert rc.flagged
    assert any("'1-3' and '10-12'" in w and "slash" in w for w in rc.warnings)


def test_combined_issues_written_with_a_slash_are_kept_whole():
    fields, rc = _convert("v. 6 nos. 1/3-v. 14 nos. 10/12 (Mar 1978-Oct/Dec 1986)")
    assert fields == ["$a 6-14 $b 1/3-10/12 $i 1978-1986 $j 03-10/12"]
    assert not rc.flagged


def test_the_same_range_at_both_ends_is_unchanged():
    """D15's case: "3-4" at each end is already the first and last part."""
    fields, rc = _convert("v. 23 no. 3-4-v. 29 no. 3-4 (Fall 1985-Fall/Winter 1991)")
    assert fields[0].startswith("$a 23-29 $b 3-4 ")
    assert not rc.flagged


def test_a_range_at_one_end_only():
    fields, rc = _convert("v. 87 no. 3-v. 89 no. 3-4 (1991-1993)")
    assert fields == ["$a 87-89 $b 3-4 $i 1991-1993"]
    assert rc.flagged


@pytest.mark.parametrize("statement, chronology", [
    ("v. 10 no. 5-v. 13 no. 3 (May 1992-Mar-Jun 1995)", "$i 1992-1995 $j 05-06"),
    ("v. 2 no. 1 - v. 23 no. 6 (January-March 1963 - December/January 1984)",
     "$i 1963-1984 $j 01-12/01"),
])
def test_a_date_range_at_one_end_no_longer_costs_the_other_end(statement, chronology):
    fields, rc = _convert(statement)
    assert fields[0].endswith(chronology)
    assert rc.flagged


def test_a_list_of_month_runs_is_still_held():
    """Two runs with a gap between are not one range; nothing is invented."""
    fields, rc = _convert("(Jan-May, Sep-Nov 1983)")
    assert fields == [] and rc.needs_review


def test_the_reported_statement_now_closes_the_loop():
    assert round_trip(REPORTED)["outcome"] == SAME


def test_no_subfield_anywhere_holds_two_ranges():
    for path in ("textual_holdings_corpus.txt", "lc_holdings_examples.txt",
                 "outside_catalog_examples.txt"):
        for entry in load_corpus(REPO_ROOT / "data" / path):
            for f in convert_holdings(parse_866(entry.statement)).fields_863:
                for sf in f.subfields:
                    assert sf.value.rstrip("-").count("-") <= 1, (entry.statement, sf)
