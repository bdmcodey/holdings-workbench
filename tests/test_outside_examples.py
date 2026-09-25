"""
Another library's catalogue, read as an outside collection.

42 statements from a catalogue other than the one the tool was built on, kept
in data/outside_catalog_examples.txt apart from the main corpus and from LC's
examples. What matters most here is that nothing is misread: a statement the
parser cannot read in full is held and named, never converted in part or into
the wrong subfields.
"""

from __future__ import annotations

import sys

import pytest

from conftest import REPO_ROOT
from marc_serials.converter import convert_holdings
from marc_serials.parser import parse_866
from marc_serials.display import CAPTION_ONLY, NOT_CONVERTED, SAME, round_trip

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from corpus_report import Outcome, load_corpus  # noqa: E402

OUTSIDE = REPO_ROOT / "data" / "outside_catalog_examples.txt"


def test_every_tag_still_describes_what_happens():
    entries = load_corpus(OUTSIDE)
    assert len(entries) == 42
    for entry in entries:
        observed = Outcome(entry).status
        expected = entry.status or "ok"
        if expected == "known":
            continue
        assert observed == expected, (entry.statement, observed)


def test_nothing_converted_is_lost_silently():
    assert not [e.statement for e in load_corpus(OUTSIDE)
                if Outcome(e).status == "loss"]


def test_the_loop_with_the_ils_closes():
    outcomes = {e.statement: round_trip(e.statement)["outcome"]
                for e in load_corpus(OUTSIDE)}
    assert set(outcomes.values()) <= {SAME, CAPTION_ONLY, NOT_CONVERTED}, [
        s for s, o in outcomes.items() if o not in (SAME, CAPTION_ONLY, NOT_CONVERTED)]


# ── Dates without parentheses (D32, 0.30.0) ──────────────────────────────────

def _fields(statement):
    rc = convert_holdings(parse_866(statement))
    return [" ".join(f"${sf.code} {sf.value}" for sf in f.subfields if sf.code != "8")
            for f in rc.fields_863], rc.warnings


@pytest.mark.parametrize("statement, fields", [
    ("v.3-36 1963-1995", ["$a 3-36 $i 1963-1995"]),
    ("v.21-26 1997-2002.", ["$a 21-26 $i 1997-2002"]),
    ("v.40 no.4-6 2003.", ["$a 40 $b 4-6 $i 2003"]),
    ("no. 33-34 1993-1995", ["$a 33-34 $i 1993-1995"]),
    ("v.1-10 1985/86-1995", ["$a 1-10 $i 1985/1986-1995"]),
    ("v.6 no.2 1990", ["$a 6 $b 2 $i 1990"]),
    ("v.12 no.3 Mar. 1990", ["$a 12 $b 3 $i 1990 $j 03"]),
    ("v.1 Fall/Winter 1990", ["$a 1 $i 1990 $j 23/24"]),
    ("v.35 2025-", ["$a 35- $i 2025-"]),
    ("v.1-3 1990-1992, v.5-7 1994-1996",
     ["$a 1-3 $i 1990-1992 $w g", "$a 5-7 $i 1994-1996"]),
])
def test_dates_after_the_numbering_are_read_as_if_in_parentheses(statement, fields):
    """The same fields the statement gives with its dates in parentheses."""
    got, warnings = _fields(statement)
    assert got == fields
    assert warnings == []
    assert round_trip(statement)["outcome"] == SAME


@pytest.mark.parametrize("statement", [
    "v.1 2000 copies",      # a word that is not a month or season: not a date
    "v.1-3 1990-",          # is the run of volumes open, or the holding?
    "v.1 1990 no.3",        # the year is not at the end
    "v.1// 1982//",         # a closed run (D34), not read
    "2016 ed.",             # no numbering
])
def test_what_is_not_plainly_numbering_then_dates_is_still_held(statement):
    got, warnings = _fields(statement)
    assert got == []
    assert warnings
