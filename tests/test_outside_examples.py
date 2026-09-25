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

from conftest import REPO_ROOT
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
