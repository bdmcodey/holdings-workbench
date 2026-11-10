"""
A date group where one side of the hyphen reads and the other does not.

"v.3 (1990--1995)" was written "$a 3 $i 1990": the group was divided at its
first hyphen, the end came out as "-1995", which reads as nothing, and the
start was kept on its own. The 1995 went with no warning, no flag and no hold,
and with "Remove each 866" ticked the 866 went too. A review before 0.50.0
found it on made-up statements; the shape is in none of the three corpora and
not in the real export, which is why every check had been green.

Now a group that is only half read goes back whole, as one that does not read
at all always has: the 863 has no year, the converter names the group and says
it could not hold it, and the record is marked to check -- what "v.3 (1990,
1995)" already did.

The statements here are made up.
"""

from __future__ import annotations

import re

import pytest

from marc_serials.converter import convert_holdings
from marc_serials.parser import parse_866


def _converted(statement):
    rc = convert_holdings(parse_866(statement))
    fields = [" ".join(f"${sf.code} {sf.value}" for sf in f.subfields if sf.code != "8")
              for f in rc.fields_863]
    return fields, rc


@pytest.mark.parametrize("statement, expected", [
    ("v.3 (1990--1995)", ["$a 3"]),
    ("v.3 (1990-1992 1995)", ["$a 3"]),
    ("v.41 1935-1938. 1910.", ["$a 41"]),
    # The run inside one end is read, and reduced to its outer ends with the
    # note that says so (0.29.0).
    ("v.10-12 (1990-1992-1995)", ["$a 10-12 $i 1990-1995"]),
])
def test_a_year_after_an_unread_hyphen_is_not_dropped_without_a_word(statement, expected):
    fields, rc = _converted(statement)
    assert fields == expected
    assert rc.flagged and not rc.needs_review
    written = " ".join(fields)
    said = " ".join(rc.warnings)
    for year in re.findall(r"\d{4}", statement):
        assert year in written or year in said, (statement, year)


@pytest.mark.parametrize("statement, expected", [
    ("v.5 (1990-)", ["$a 5- $i 1990-"]),
    ("v.5 (Jan-Jun 1984)", ["$a 5 $i 1984 $j 01-06"]),
    ("v.5 (1990-Dec. 1996)", ["$a 5 $i 1990-1996"]),
])
def test_a_group_whose_both_sides_read_is_unchanged(statement, expected):
    fields, _ = _converted(statement)
    assert fields == expected
