"""
The Library of Congress's own 866 examples, read as an outside collection.

Every other statement the tool is measured against comes from the library it
was built for. These come from the MARC 21 holdings pages under docs/marc/, and
they are kept in data/lc_holdings_examples.txt, apart from the main corpus, so
that how the parser does on statements it was not shaped around can be read on
its own. Seven statements: four convert cleanly, one converts and says what it
left out, and two are in the US Newspaper Program's notation and convert to
nothing -- held, not misread.
"""

from __future__ import annotations

import sys

import pytest

from conftest import REPO_ROOT
from marc_serials.converter import convert_holdings
from marc_serials.parser import parse_866

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from corpus_report import Outcome, load_corpus  # noqa: E402

LC = REPO_ROOT / "data" / "lc_holdings_examples.txt"


def test_every_tag_still_describes_what_happens():
    """The file's tags are the baseline the drift check reads; keep them true."""
    entries = load_corpus(LC)
    assert len(entries) == 7
    for entry in entries:
        observed = Outcome(entry).status
        expected = entry.status or "ok"
        if expected == "known":
            continue
        assert observed == expected, (entry.statement, observed)


@pytest.mark.parametrize("statement, fields", [
    ("v. 1-4 (1941-1943), v. 6-86 (1945-1987)",
     ["$a 1-4 $i 1941-1943 $w g", "$a 6-86 $i 1945-1987"]),
    ("1974-1981", ["$i 1974-1981"]),
    ("v. 37-52", ["$a 37-52"]),
    ("v. 36-49 (1961-1974)", ["$a 36-49 $i 1961-1974"]),
])
def test_the_plain_forms_convert_cleanly(statement, fields):
    rc = convert_holdings(parse_866(statement))
    assert [" ".join(f"${sf.code} {sf.value}" for sf in f.subfields if sf.code != "8")
            for f in rc.fields_863] == fields
    assert rc.warnings == []


def test_an_issue_spanning_two_years_says_what_it_left_out():
    """D29: no subfield holds "2003:Dec./2004:Jan.", and the record says so."""
    rc = convert_holdings(parse_866("no.56(2003:Dec./2004:Jan.)"))
    assert rc.fields_863 and rc.flagged
    assert any("2003:Dec./2004:Jan." in w for w in rc.warnings)


@pytest.mark.parametrize("statement", [
    "m,s=[1955:8:11-1956:11:22][1960:10:20-1984:2:2]",
    "[1844:7:10][1850:2:16]",
])
def test_newspaper_program_notation_is_held_not_misread(statement):
    """D30: a different notation scheme, declared by its $2. Nothing is guessed."""
    assert convert_holdings(parse_866(statement)).fields_863 == []
