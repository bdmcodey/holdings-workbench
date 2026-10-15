"""
A serial that changes from months to seasons, or back (D49, 0.37.0).

An 853's second level of chronology is "(month)" or "(season)", and the codes
under it mean one or the other. MARC 21 (853-855, Field Repeatability): "The
853-855 fields are repeated when the contents of the subfields varies." So a
change of kind needs a second 853, and one 863 -- which links to one 853 --
cannot straddle it.

Three things went wrong before 0.37.0, all found from the cataloguer's real
statement "v. 19 no. 3-v. 20 no. 4 (September 1986-Winter 1987)":

* inside one statement, the 863 mixed the kinds: "$j 09-24" under "(season)";
* a season left out because only one end of a range gave it made the statement
  look like a month statement with less detail, and it was merged into the
  next statement's month 853 -- the fixture record exmpl0003 did exactly this;
* the same statement was filed under a month 853 already on the record.

The cataloguer's decisions: a change inside one statement is held, because
only they know which issue it falls at; a change between statements is
converted and flagged, to confirm it falls there; and a split of one 866 into
several, made on the Workbench, is how they say where -- after which that
change is said, and not asked again.
"""

from __future__ import annotations

import io

import pytest
from pymarc import Field, MARCReader, MARCWriter, Record, Subfield

from conftest import EXAMPLE_MRC, upload_marc
from marc_serials.converter import convert_record
from marc_serials.parser import (chronology_kinds, chronology_switch,
                                 parse_866, statement_chron_kind)
from marc_serials.records import (MAX_SPLIT_PARTS, apply_866_edits,
                                  edit_notes, summarise_866)

REAL = "v. 19 no. 3-v. 20 no. 4 (September 1986-Winter 1987)"
SPLIT = ["v. 19 no. 3-6 (Sept.-Dec. 1986)", "v. 20 no. 1-4 (Winter-Fall 1987)"]
MONTHS = "v. 4 no. 1-v. 6 no. 12 (Jan. 1984-Dec. 1986)"
MONTH_853 = [("8", "1"), ("a", "v."), ("b", "no."), ("i", "(year)"),
             ("j", "(month)")]


def _convert(*statements, existing=None, split_from=None):
    ex = None
    if existing:
        ex = [Field(tag="853", indicators=["2", "0"],
                    subfields=[Subfield(c, v) for c, v in existing])]
    return convert_record([parse_866(s) for s in statements],
                          existing_853s=ex, split_from=split_from)


def _shown(fields):
    return [f.display() for f in fields]


# ── Reading which kind a statement counts by ─────────────────────────────────

def test_kinds_in_order_including_a_season_left_out():
    assert chronology_kinds(parse_866(REAL)) == [("month", "09"), ("season", "24")]
    # "Fall" is left out of the 863 -- one end only -- but the statement still
    # counts by season, which is what decides its 853.
    assert chronology_kinds(parse_866("v. 1-3 (1981-Fall 1983)")) == [("season", "23")]
    assert statement_chron_kind(parse_866("v. 1-3 (1981-Fall 1983)")) == "season"
    assert statement_chron_kind(parse_866("v. 1-3 (1981-1983)")) is None


@pytest.mark.parametrize("statement, switch", [
    (REAL, ("month", "09", "season", "24")),
    ("v. 19 no. 1-v. 20 no. 2 (Spring 1986-March 1987)",
     ("season", "21", "month", "03")),
    ("v.1 (Jan.-Dec. 1981), v.2 (Spring-Fall 1982)",
     ("month", "12", "season", "21")),
    ("v. 1 no. 1 (Spring 1981)-v. 3 no. 4 (Winter 1983)", None),
    ("v. 1 no. 1 (Jan. 1981)-v. 3 no. 12 (Dec. 1983)", None),
])
def test_where_a_statement_changes_kind(statement, switch):
    assert chronology_switch(parse_866(statement)) == switch


# ── Inside one statement: held ───────────────────────────────────────────────

def test_the_real_statement_is_held_with_its_reason():
    rc = _convert(REAL)
    result = rc.results[0]
    assert result.needs_review and not result.fields_863 and not rc.fields_853
    assert result.chron_switch["where"] == "within"
    note = result.chron_switch["note"]
    assert note == result.warnings[0] and note in result.attention
    assert "from months to seasons within this statement" in note
    assert "(September … Winter)" in note and "Split this 866" in note


def test_a_list_of_runs_changing_kind_is_held_too():
    rc = _convert("v.1 (Jan.-Dec. 1981), v.2 (Spring-Fall 1982)")
    assert rc.results[0].needs_review
    assert rc.results[0].chron_switch["where"] == "within"


# ── Between statements: two 853s, flagged ────────────────────────────────────

def test_a_season_left_out_keeps_its_own_853():
    """The fixture's exmpl0003 shape: merged into the month 853 before 0.37.0."""
    rc = _convert("v. 1-3 (1981-Fall 1983)", MONTHS)
    assert _shown(rc.fields_853) == [
        "853 31 $8 1 $a v. $i (year) $j (season)",
        "853 31 $8 2 $a v. $b no. $i (year) $j (month)"]
    first, second = rc.results
    assert not first.flagged
    assert second.flagged and second.chron_switch["where"] == "between"
    assert "from seasons to months between the statement before and this one" \
        in second.chron_switch["note"]
    assert "(Fall … January)" in second.chron_switch["note"]


def test_the_fixture_record_that_showed_it(client):
    record = next(r for r in MARCReader(EXAMPLE_MRC.read_bytes())
                  if r["001"].data == "exmpl0003")
    rc = convert_record([parse_866(f["a"]) for f in record.get_fields("866")])
    assert len(rc.fields_853) == 2
    assert {f.display().split("$j ")[-1] for f in rc.fields_853} == \
        {"(season)", "(month)"}
    assert rc.results[1].flagged


def test_a_change_between_whole_statements_is_flagged():
    rc = _convert("v. 1 no. 1 (Spring 1981)-v. 3 no. 4 (Winter 1983)", MONTHS)
    assert len(rc.fields_853) == 2
    assert [r.flagged for r in rc.results] == [False, True]


def test_a_year_only_statement_between_is_no_evidence_either_way():
    rc = _convert("v. 1 no. 1 (Spring 1981)-v. 2 no. 4 (Winter 1982)",
                  "v. 3 (1983)", MONTHS)
    assert [r.flagged for r in rc.results] == [False, False, True]


def test_one_kind_throughout_is_not_flagged():
    rc = _convert("v. 1 no. 1 (Jan. 1981)-v. 3 no. 12 (Dec. 1983)", MONTHS)
    assert not any(r.flagged for r in rc.results)
    assert len(rc.fields_853) == 1


def test_a_season_statement_is_not_filed_under_a_month_853_on_the_record():
    rc = _convert("v. 1 (1981)-v. 3 (Fall 1983)", MONTHS, existing=MONTH_853)
    season, month = rc.results
    assert not season.conformed
    assert _shown(rc.fields_853) == ["853 31 $8 2 $a v. $i (year) $j (season)"]
    assert season.flagged
    assert "already on this record ($8 1) gives months" in season.chron_switch["note"]
    # The month statement does belong under it, and is flagged for the change
    # from the season statement before it.
    assert month.conformed and month.flagged


# ── Split by the cataloguer: said, not asked ─────────────────────────────────

def test_a_split_converts_to_two_853s_and_is_not_asked_again():
    rc = _convert(*SPLIT, split_from=[0, 0])
    assert _shown(rc.fields_853) == [
        "853 31 $8 1 $a v. $b no. $i (year) $j (month)",
        "853 31 $8 2 $a v. $b no. $i (year) $j (season)"]
    assert _shown(rc.fields_863) == [
        "863 40 $8 1.1 $a 19 $b 3-6 $i 1986 $j 09-12",
        "863 40 $8 2.1 $a 20 $b 1-4 $i 1987 $j 24-23"]
    assert not any(r.flagged for r in rc.results)
    assert rc.results[1].chron_switch["where"] == "split"
    assert rc.results[1].chron_switch["note"] in rc.results[1].warnings


def test_parts_of_different_splits_are_still_asked_about():
    rc = _convert(*SPLIT, split_from=[0, 1])
    assert rc.results[1].flagged


# ── Splitting an 866, in the record ──────────────────────────────────────────

def _record(*statements, link=None):
    rec = Record()
    rec.leader = "00522cy  a22001453n 4500"
    rec.add_field(Field(tag="001", data="switch-test"))
    for text in statements:
        subfields = ([Subfield("8", link)] if link else []) + [Subfield("a", text)]
        rec.add_field(Field(tag="866", indicators=[" ", "0"], subfields=subfields))
    rec.add_field(Field(tag="999", indicators=[" ", " "],
                        subfields=[Subfield("b", "after")]))
    return rec


def test_apply_puts_the_parts_in_place_and_in_order():
    rec = _record(REAL, MONTHS, link="0")
    rec.get_fields("866")[0].add_subfield("z", "Public note")
    apply_866_edits(rec, {"0": {"split": {"values": SPLIT, "was": REAL}}})
    fields = rec.get_fields("866")
    assert [f["a"] for f in fields] == SPLIT + [MONTHS]
    # The first part keeps the field's notes; every part keeps its $8.
    assert fields[0].get("z") == "Public note" and fields[1].get("z") is None
    assert [f.get("8") for f in fields] == ["0", "0", "0"]
    # Still before the field that followed them.
    assert [f.tag for f in rec.fields][-1] == "999"
    shown = [summarise_866(f) for f in fields]
    assert [(s["position"], s["split_part"]) for s in shown] == \
        [(0, 0), (0, 1), (1, None)]
    # And it writes as MARC.
    assert rec.as_marc()


def test_the_split_is_said_on_the_record():
    notes = edit_notes({"0": {"split": {"values": SPLIT, "was": REAL}}})
    assert notes == [f'You split 866 no. 1, which read "{REAL}", into 2: '
                     f'"{SPLIT[0]}"; "{SPLIT[1]}".']


# ── Through the application ──────────────────────────────────────────────────

def _file(*statements) -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    writer.write(_record(*statements))
    writer.close(close_fh=False)
    return buf.getvalue()


def _split(client, field_index=0, parts=SPLIT, revert=False):
    return client.post("/api/split-866", json={
        "record_index": 0, "field_index": field_index, "parts": parts,
        "revert": revert})


def _previews(client):
    return client.post("/api/preview-record",
                       json={"record_index": 0}).get_json()["previews"]


def test_split_then_convert_and_undo(client):
    upload_marc(client, _file(REAL))
    before = _previews(client)
    assert before[0]["needs_review"]
    assert before[0]["chron_switch"]["where"] == "within"

    body = _split(client).get_json()
    assert [f["a"] for f in body["fields_866"]] == SPLIT
    assert SPLIT[1] in body["statements"] and REAL not in body["statements"]
    assert body["edited"][0].startswith("You split 866 no. 1")

    after = _previews(client)
    assert [p["field_853"].split("$j ")[-1] for p in after] == ["(month)", "(season)"]
    assert not any(p["flagged"] for p in after)

    # From either part, the split is undone whole.
    body = _split(client, field_index=1, revert=True).get_json()
    assert [f["a"] for f in body["fields_866"]] == [REAL]
    assert _previews(client)[0]["needs_review"]


def test_the_downloaded_file_and_the_log_carry_the_split(client):
    upload_marc(client, _file(REAL, "v. 21 no. 1-4 (Spring-Winter 1988)"))
    _split(client)
    client.post("/api/batch-convert", json={"remove_866": False})
    with client.get("/api/download-converted") as got:
        record = list(MARCReader(got.data))[0]
    assert [f["a"] for f in record.get_fields("866")] == SPLIT + [
        "v. 21 no. 1-4 (Spring-Winter 1988)"]
    log = client.get("/api/download-log").get_data(as_text=True)
    assert "Edited by you" in log and "Split by you: months and seasons" in log


def test_the_log_names_a_held_change_and_a_flagged_one(client):
    upload_marc(client, _file(REAL, "v. 1-3 (1981-Fall 1983)", MONTHS))
    client.post("/api/batch-convert", json={})
    log = client.get("/api/download-log").get_data(as_text=True)
    assert "Held: months and seasons in one 866" in log
    assert "Check: months and seasons change" in log


def test_edit_after_a_split_reaches_the_right_866(client):
    """A split moves every later 866 along; Edit counts them as shown."""
    upload_marc(client, _file(REAL, MONTHS))
    _split(client)
    fixed = MONTHS.replace("Dec. 1986", "Nov. 1986")
    body = client.post("/api/edit-866", json={
        "record_index": 0, "field_index": 2, "code": "a",
        "value": fixed}).get_json()
    assert [f["a"] for f in body["fields_866"]] == SPLIT + [fixed]


def test_a_split_statement_is_changed_with_split_not_edit(client):
    upload_marc(client, _file(REAL))
    _split(client)
    for index, code in ((0, "a"), (1, "a"), (1, "z")):
        response = client.post("/api/edit-866", json={
            "record_index": 0, "field_index": index, "code": code,
            "value": "v. 1"})
        assert response.status_code == 400
        assert "Split" in response.get_json()["error"]
    # A note on the field the first part kept is still an ordinary edit.
    assert client.post("/api/edit-866", json={
        "record_index": 0, "field_index": 0, "code": "z",
        "value": "Note"}).status_code == 200


@pytest.mark.parametrize("parts, why", [
    (["v. 1"], "at least two"),
    (["v. 1", "   "], "at least two"),
    ([f"v. {n}" for n in range(MAX_SPLIT_PARTS + 1)], f"At most {MAX_SPLIT_PARTS}"),
    (["v. 1", "v. " + "9" * 600], "at most"),
    ("v. 1", "Send the statements"),
])
def test_a_split_that_cannot_be_made_is_refused(client, parts, why):
    upload_marc(client, _file(REAL))
    response = _split(client, parts=parts)
    assert response.status_code == 400
    assert why in response.get_json()["error"]


# ── Measured on the corpora ──────────────────────────────────────────────────

def test_the_corpora_hold_exactly_the_four_measured():
    """Counted at 0.37.0: the four statements tagged fail:D49."""
    from conftest import DATA_DIR
    held = []
    for name in ("textual_holdings_corpus.txt", "lc_holdings_examples.txt",
                 "outside_catalog_examples.txt"):
        for line in (DATA_DIR / name).read_text(encoding="utf-8").splitlines():
            text = line.split("  #")[0].strip()
            if not text or text.startswith(("#", "[")):
                continue
            if chronology_switch(parse_866(text)):
                held.append(text)
                assert "fail:D49" in line, text
    assert len(held) == 4
