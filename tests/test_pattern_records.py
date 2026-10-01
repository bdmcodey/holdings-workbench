"""
From a pattern to its records, and its expression off the screen.

Asked for by the cataloguer: the detected patterns said too little to review,
with each expression three clicks in and no way to copy it, and there was no
way to go from a pattern to the records it touches.

"The records a pattern runs on" is two sets, and the screen offers both where
they differ: the records *with this shape* (what the card's count describes,
known from detection) and the records a confirmed pattern *converts* (known
from the review index, which already records which pattern read each record).
On the real 372-record export one pattern converted 8 of the 18 records with
its shape -- larger patterns claim the rest first -- and another converted 31
against 29, because an expression can match a neighbouring shape too.
"""

from __future__ import annotations

import io
import re

from pymarc import Field, MARCWriter, Record, Subfield

from conftest import REPO_ROOT, upload_marc


def _file(*statements) -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for n, statement in enumerate(statements):
        rec = Record()
        rec.leader = "00522cy  a22001453n 4500"
        rec.add_field(Field(tag="001", data=f"shape-{n}"))
        rec.add_field(Field(tag="866", indicators=[" ", "0"],
                            subfields=[Subfield("a", statement)]))
        writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def _groups(client):
    return client.post("/api/detect", json={}).get_json()["groups"]


def test_every_record_with_the_shape_is_listed_not_only_the_first(client):
    """
    Detection used to remember one record per statement, for its examples. The
    same statement on three records is three records to show.
    """
    upload_marc(client, _file("v.1(1990)-v.3(1992)", "v. 9 (1998)",
                              "v.1(1990)-v.3(1992)", "V. 4 (1980)-v. 6 (1982)",
                              "v.1(1990)-v.3(1992)"))
    by_label = {g["human_label"]: g for g in _groups(client)}

    assert by_label["VOL(YEAR) — VOL(YEAR)"]["records"] == [0, 2, 3, 4]
    assert by_label["VOL(YEAR)"]["records"] == [1]


def test_a_split_statement_counts_its_record_once(client):
    upload_marc(client, _file("v.1(1990)-v.3(1992), v.5(1994)-v.7(1996)"))
    group = next(g for g in _groups(client)
                 if g["human_label"] == "VOL(YEAR) — VOL(YEAR)")
    assert group["records"] == [0]


def test_the_examples_do_not_carry_the_whole_list(client):
    """The example provenance stays what it was; the list is the group's."""
    upload_marc(client, _file("v.1(1990)-v.3(1992)", "v.1(1990)-v.3(1992)"))
    group = _groups(client)[0]
    assert all("records" not in (src or {}) for src in group["example_sources"])


def _page() -> str:
    return (REPO_ROOT / "marc_serials" / "templates" / "tool.html").read_text(
        encoding="utf-8")


def test_the_card_shows_its_expression_and_can_copy_it():
    """The screen half: the expression is outside the folded body, with Copy."""
    page = _page()
    card = re.search(r"function buildPatternCard.*?\n}\n", page, re.S).group(0)
    head, body = card.split('<div class="pc-body" hidden>', 1)
    assert 'class="pc-expr"' in head and "pc-copy" in head
    assert "btn-copy-all-regex" in page


def test_the_pattern_filter_reads_the_right_set_for_each_mode():
    page = _page()
    matcher = re.search(r"case 'one-pattern':.*?: patternFilter\.indexes\.has\(index\);",
                        page, re.S)
    assert matcher, "the one-pattern filter has moved or been renamed"
    assert "patternFilter.mode === 'converted'" in matcher.group(0)
    assert "entry.sources" in matcher.group(0)


def test_a_run_from_pasted_statements_shows_its_patterns_open():
    """
    Pasted statements have no Convert step, so the patterns are all there is to
    see: a run from the text box leaves step 2 and its folds open. A run from a
    file still folds when nothing asks a decision, to put Convert in view.
    """
    run = re.search(r"async function runDetect.*?\n}\n", _page(), re.S).group(0)
    assert "const fromPaste = sourceMode === 'paste';" in run
    assert "patternFolds.confirmed = patternFolds.readable" in run
    assert "setPatternsCollapsed(!fromPaste && !partitionGroups" in run


def test_the_source_is_a_file_or_pasted_statements_never_both():
    """
    Asked for by the cataloguer: patterns found from pasted text while Convert
    worked on a file were two sources on one screen. The last one chosen wins.
    "Use these statements" sets the file aside -- still loaded, with its
    records and decisions, but out of play -- and "Back to <file>" brings it
    back without a second upload.
    """
    page = _page()
    upload = re.search(r"async function uploadMarcFile.*?\n}\n", page, re.S).group(0)
    assert "sourceMode    = 'file';" in upload and "fileName      = file.name;" in upload
    use = re.search(r"getElementById\('btn-use-text'\)\.addEventListener.*?\n}\);", page, re.S).group(0)
    assert "if (sourceMode === 'file') setFileAside();" in use
    aside = re.search(r"function setFileAside\(\).*?\n}\n", page, re.S).group(0)
    assert "allRecords" not in aside, "setting a file aside must keep it"
    back = re.search(r"function useFileAgain\(\).*?\n}\n", page, re.S).group(0)
    assert "sourceMode = 'file';" in back and "renderPatterns(fileDetect)" in back
    detect = re.search(r"function statementsForDetection\(\).*?\n}\n", page, re.S).group(0)
    assert "sourceMode === 'paste' ? pastedStatements() : allStatements" in detect
    reveal = re.search(r"function revealSteps\(\).*?\n}\n", page, re.S).group(0)
    assert "sourceMode === 'paste'" in reveal


def test_pasted_statements_are_linked_to_no_record(client):
    """
    With a file loaded, a pasted statement that reads the same as one in the
    file was credited to that record. Pasted statements come from no record.
    """
    upload_marc(client, _file("v.1(1990)-v.3(1992)"))
    from_file = client.post("/api/detect", json={
        "statements": ["v.1(1990)-v.3(1992)"]}).get_json()["groups"][0]
    pasted = client.post("/api/detect", json={
        "statements": ["v.1(1990)-v.3(1992)"], "pasted": True}).get_json()["groups"][0]
    assert from_file["records"] == [0]
    assert pasted["records"] == []


def test_settings_that_change_nothing_are_greyed_out():
    """
    Asked for by the cataloguer: on a pattern the parser reads in full, every
    setting was live and none changed the output. Measured: where the parser
    reads all but a caption, only bare numbers ("…_num") change anything; where
    it reads the statement in full, nothing does. Those rows are disabled.
    """
    page = _page()
    fixed = re.search(r"function roleIsFixed\(group, role\).*?\n}\n", page, re.S).group(0)
    assert "group.decides === 'nothing'" in fixed
    assert "group.decides === 'caption'" in fixed and "BARE_NUMBER_RE" in fixed
    assert "const BARE_NUMBER_RE = /(^|_)num(_\\d+)?$/;" in page
    rows = re.search(r"function renderRoleRows.*?\n}\n", page, re.S).group(0)
    assert rows.count("${off}") == 4          # boundary, meaning, caption, level
    assert "edit the 866 on its record" in page


def test_which_settings_change_the_output_is_what_the_screen_says(client):
    """The server's 'decides' is what the greying keys on; pin the three cases."""
    for statement, decides in (("v. 1 (1990)", "nothing"),
                               ("39 no. 1 (1990)", "caption"),
                               ("?: 16", "reading")):
        [group] = client.post("/api/detect", json={
            "statements": [statement], "pasted": True}).get_json()["groups"]
        assert group["decides"] == decides, statement
