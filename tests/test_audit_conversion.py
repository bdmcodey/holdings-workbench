"""
The audit that reads a file and asks what went missing.

Its own risk is the one every checker has: passing because it looks at
nothing. These tests give it a conversion that really does lose something and
require it to say so, and a clean one and require it to stay quiet.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "audit_conversion.py"


@pytest.fixture(scope="module")
def audit_module():
    spec = importlib.util.spec_from_file_location("audit_conversion", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_conversion"] = module
    spec.loader.exec_module(module)
    return module


def test_a_statement_that_converts_whole_is_quiet(audit_module):
    found = audit_module.audit("v. 1-5 (1990-1994)")
    assert found["produced"] is True
    assert found["missing"] == [], found


def test_an_abbreviation_is_not_reported_as_a_loss(audit_module):
    """
    The false positive that cost this script its first run.

    "1960-66" is written out as "1960-1966", so a search for a bare "66" finds
    nothing and reports a correct conversion as a loss. Nine of them, all
    correct. The audit expands the statement the same way the converter does,
    by calling the converter's own function rather than keeping a copy of the
    rule that is free to drift.
    """
    for statement in ("v. 1-7 (1960-66)", "v. 12 no. 4 (Winter 1996/97)",
                      "(1999-00)"):
        assert audit_module.audit(statement)["missing"] == [], statement


def test_a_real_loss_is_reported(audit_module):
    """
    The test that keeps the audit honest: a checker that never fails is a
    checker nobody should trust.

    Rather than wait for a defect, this hands `accounted_for` the shape of one
    directly -- a value in the statement, absent from the fields, absent from
    every warning.
    """
    assert audit_module.accounted_for("1986", "1986-1988", "") is True
    assert audit_module.accounted_for("1987", "1986-1988", "") is True, (
        "a span covers the years between its ends")
    assert audit_module.accounted_for("1993", "1986-1988", "") is False
    assert audit_module.accounted_for("1993", "", "could not encode 1993") is True


def test_the_link_number_cannot_account_for_a_holding(audit_module):
    """
    $8 is the tool's own bookkeeping -- "1.1", "1.12" -- and counting its
    digits as output would let an 863 linked 1.12 account for a volume 12 that
    was never written.
    """
    assert "8" in audit_module.BOOKKEEPING_SUBFIELDS


def test_the_committed_corpus_passes(audit_module):
    """
    Not a formality: the corpus is the material every other measurement in the
    project is taken against, so a loss in it would undermine all of them.
    """
    pairs = audit_module.statements_from(REPO_ROOT / "data" /
                                         "textual_holdings_corpus.txt")
    assert len(pairs) > 100
    silent = [s for _, s in pairs
              if audit_module.audit(s)["produced"]
              and audit_module.audit(s)["missing"]
              and not audit_module.audit(s)["warned"]]
    assert silent == [], silent
