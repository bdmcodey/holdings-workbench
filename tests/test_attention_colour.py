"""
Which warning asks for a decision.

Asked for by the cataloguer, from a record with two statements: one converted
and flagged "to check" (a range inside one end), the other converted with a
warning said only for the log (a month at one end). Both warnings were the
same yellow, so the record said "1 to check" and nothing said which. The
converter now lists the warnings that are why a statement is flagged, and the
screen shows those in orange, headed "To check:".
"""

from __future__ import annotations

import io
import re

from pymarc import Field, MARCWriter, Record, Subfield

from conftest import REPO_ROOT, upload_marc
from marc_serials.converter import convert_holdings
from marc_serials.parser import parse_866

FLAGGED = "v. 87 no. 3-v. 89 no. 3-4 (1991-1993)"
LOG_ONLY = "v. 71 no. 1-v. 87 no. 1 (Feb 1975-1991)"


def test_the_warning_that_flags_a_statement_is_named():
    rc = convert_holdings(parse_866(FLAGGED))
    assert rc.flagged
    assert rc.attention and rc.attention[0].startswith("'3-4' ('no.' level) is a range")
    assert set(rc.attention) <= set(rc.warnings)


def test_a_warning_for_the_log_asks_nothing():
    rc = convert_holdings(parse_866(LOG_ONLY))
    assert rc.warnings and not rc.flagged
    assert rc.attention == []


def test_every_way_of_flagging_names_its_warning():
    for statement in (FLAGGED, "v. 4 (1990), lacks 7", "v.1 (Late Summer 1990)"):
        rc = convert_holdings(parse_866(statement))
        assert rc.flagged == bool(rc.attention), statement


def test_the_preview_carries_it_to_the_screen(client):
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    rec = Record()
    rec.leader = "00522cy  a22001453n 4500"
    rec.add_field(Field(tag="001", data="both"))
    for statement in (LOG_ONLY, FLAGGED):
        rec.add_field(Field(tag="866", indicators=[" ", "0"],
                            subfields=[Subfield("a", statement)]))
    writer.write(rec)
    writer.close(close_fh=False)
    upload_marc(client, buf.getvalue())
    previews = client.post("/api/preview-record",
                           json={"record_index": 0}).get_json()["previews"]
    by_source = {p["source_866"]: p for p in previews}
    assert by_source[FLAGGED]["attention"]
    assert by_source[LOG_ONLY]["attention"] == []


def test_the_page_colours_by_it():
    page = (REPO_ROOT / "marc_serials" / "templates" / "tool.html").read_text(
        encoding="utf-8")
    helper = re.search(r"function warningHtml.*?\n}\n", page, re.S).group(0)
    assert "pv.attention" in helper and "alert-attention" in helper
    assert "To check:" in helper
    css = (REPO_ROOT / "marc_serials" / "shared" / "ui.css").read_text(encoding="utf-8")
    # Defined for the light theme and both ways of asking for the dark one.
    assert css.count("--attention:") == 3


def test_a_held_statement_shows_every_reason():
    """
    "v.1// 1982//" is held with "No recognisable holdings ranges found" and
    then "Read 'v.1' but could not account for '// 1982//'". Only the first
    was shown, and it is the second that says what to clean up.
    """
    page = (REPO_ROOT / "marc_serials" / "templates" / "tool.html").read_text(
        encoding="utf-8")
    assert "pv.warnings[0]" not in page
    assert page.count("${heldReasonHtml(pv)}") == 2
    warnings = parse_866("v.1// 1982//").warnings
    assert any("could not account for '// 1982//'" in w for w in warnings)
