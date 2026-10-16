"""
A list of runs written with a mistake in it, and what each reader does.

Reported on 0.40.0 with a statement from the real export, a list of volume
runs and year runs with a comma missing between two volume runs, a hyphen
after a closed last run, and a year run out of order. The parser refused it,
rightly -- but the Patterns card said "100% matched", and confirming its
pattern would have written one 863 with the wrong end year and set the other
four runs aside as "Not encoded". With splitting on, the pattern for the first
run converted that run alone. Either way "Remove each 866" would then take the
866, and the runs not written with it.

The statement here is made up, with the same three mistakes.
"""

from __future__ import annotations

import re

import pytest

from marc_serials.bridge import build_parse_result, split_statement
from marc_serials.converter import convert_holdings
from marc_serials.detector import detect_patterns
from marc_serials.bridge import infer_roles
from marc_serials.parser import parse_866

MISTAKES = "v. 21-26, 29-31 33, 35, 37-38-(1921-25,1938-41,1932,1935,1937-38)"


def _863s(statement):
    rc = convert_holdings(parse_866(statement))
    return [" ".join(f"${sf.code} {sf.value}" for sf in f.subfields if sf.code != "8")
            for f in rc.fields_863], rc


# -- the parser -------------------------------------------------------------

def test_the_statement_as_written_is_not_read():
    fields, rc = _863s(MISTAKES)
    assert fields == []


def test_a_refused_run_gives_its_own_reason():
    # Comma put back: the list is now a list, and its last run is what stops it.
    fields, rc = _863s("v. 21-26, 29-31, 33, 35, 37-38-(1921-25,1928-30,1932,1935,1937-38)")
    assert fields == []
    assert any("'v. 37-38 (1937-38)-' gives a run and then leaves it open" in w
               for w in rc.warnings)


def test_years_that_go_backwards_convert_and_are_marked_to_check():
    fields, rc = _863s("v. 21-26, 29-31, 33, 35, 37-38 (1921-25,1938-41,1932,1935,1937-38)")
    assert fields[1] == "$a 29-31 $i 1938-1941 $w g"
    assert rc.flagged and not rc.needs_review
    (note,) = rc.attention
    assert "'v. 29-31 (1938-41)' runs to 1941" in note
    assert "'v. 33 (1932)', begins in 1932" in note


def test_years_in_order_ask_nothing():
    fields, rc = _863s("v. 21-26, 29-31, 33, 35, 37-38 (1921-25,1928-30,1932,1935,1937-38)")
    assert len(fields) == 5 and not rc.flagged


def test_a_list_of_dates_alone_that_goes_backwards_is_marked_too():
    _, rc = _863s("(1990, 1985)")
    assert rc.flagged


@pytest.mark.parametrize("statement", [
    "v. 1-3, 5-(1990-92, 1994-)",    # open on both sides
    "v. 1-3, 5 (1990-92, 1994-)",    # open in the years only
    "v. 1-3, 5-(1990-92, 1994)",     # open in the volumes only, as before
])
def test_the_last_run_of_a_list_can_be_left_open(statement):
    fields, rc = _863s(statement)
    assert fields == ["$a 1-3 $i 1990-1992 $w g", "$a 5- $i 1994-"]
    assert not rc.needs_review and not rc.flagged


def test_one_open_year_for_several_runs_is_still_not_shared():
    fields, rc = _863s("v. 1, 3 (1994-)")
    assert fields == ["$a 1 $w g", "$a 3"]
    assert rc.left_out


# -- a pattern --------------------------------------------------------------

def _patterns(statement, split):
    # As the Workbench detects: split into pieces first, or not.
    pieces = split_statement(statement) if split else [statement]
    return [g for g in detect_patterns(pieces) if g.regex]


@pytest.mark.parametrize("split", [False, True])
def test_no_pattern_converts_part_of_the_statement(split):
    for group in _patterns(MISTAKES, split):
        roles = infer_roles(list(re.compile(group.regex).groupindex))
        result = build_parse_result(MISTAKES, re.compile(group.regex, re.I),
                                    roles, split=split, fallback=True)
        if result is None:
            continue
        rc = convert_holdings(result)
        assert rc.fields_863 == [] and rc.needs_review, (group.human_label, rc.warnings)


def test_the_whole_list_pattern_says_what_it_would_set_aside():
    (group,) = _patterns(MISTAKES, split=False)
    roles = infer_roles(list(re.compile(group.regex).groupindex))
    result = build_parse_result(MISTAKES, re.compile(group.regex, re.I), roles,
                                split=False)
    note = result.attention[0]
    assert note.startswith("This statement lists several runs, and a pattern "
                           "describes only one: it would set aside '29', '31'")
    assert "comma missing between runs" in note


def test_a_list_of_one_runs_levels_is_not_a_list():
    # "Vol. 1, No. 1" has a caption after its comma: one run's levels.
    from marc_serials.bridge import _lists_runs
    assert not _lists_runs("Vol. 1, No. 1 (Spring 1990)-Vol. 5, No. 4 (Winter 1994)")
    assert _lists_runs("v. 21-26, 29-31 33, 35")
