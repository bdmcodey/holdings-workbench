"""
An open end is kept or refused, never dropped.

"v.35 (2025-)" writes its open end inside the parentheses. The date reader
had nothing after the hyphen and dropped it without a word: "$a 35 $i 2025",
a closed holding, for a title still being received. Found while reading the
other library's catalogue (0.30.0) and fixed in 0.30.1. None of the 1,137
statements in the corpora and the real export is written this way, and none
of them converts differently.
"""

from __future__ import annotations

import pytest

from marc_serials.converter import convert_holdings
from marc_serials.display import SAME, round_trip
from marc_serials.parser import parse_866


def _fields(statement):
    rc = convert_holdings(parse_866(statement))
    return [" ".join(f"${sf.code} {sf.value}" for sf in f.subfields if sf.code != "8")
            for f in rc.fields_863], rc.warnings


@pytest.mark.parametrize("statement, fields", [
    ("v.35 (2025-)", ["$a 35- $i 2025-"]),
    ("v.35 (2025- )", ["$a 35- $i 2025-"]),
    ("(2025-)", ["$i 2025-"]),
    ("v.1 (Jan. 2025-)", ["$a 1- $i 2025- $j 01-"]),
    ("v.35:no.1 (2025:Jan.-)", ["$a 35- $b 1- $i 2025- $j 01-"]),
])
def test_an_open_end_inside_the_parentheses_is_kept(statement, fields):
    """The same fields as the hyphen written after the parentheses."""
    got, warnings = _fields(statement)
    assert got == fields
    assert warnings == []
    assert round_trip(statement)["outcome"] == SAME


@pytest.mark.parametrize("statement", [
    "v.1-3 (1990-)",        # the volumes open from 3, or the holding from 1990?
    "v.1-3 (1990)-",        # used to write "$a 1-3-"
    "v.1 (1990-1992)-",     # used to write "$i 1990-1992-"
])
def test_a_run_left_open_is_held_and_says_why(statement):
    got, warnings = _fields(statement)
    assert got == []
    assert any("gives a run and then leaves it open" in w for w in warnings)


def test_an_open_end_inside_the_end_unit_is_held():
    """'v.1(1990)-v.5(1994-)' has nowhere to put the hyphen."""
    got, warnings = _fields("v.1(1990)-v.5(1994-)")
    assert got == []
    assert any("leaves its dates open inside the parentheses" in w for w in warnings)


def test_the_ordinary_open_end_is_unchanged():
    assert _fields("v.6(1995)-")[0] == ["$a 6- $i 1995-"]
    assert _fields("1990-")[0] == ["$i 1990-"]
