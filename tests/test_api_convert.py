"""
The conversion routes, driven through the Flask test client.

Uploaded MARC lives on disk keyed by a uuid in the session cookie, so a fresh
test client is a fresh working set. Two of the tests below depend on that and
say so; the rest simply benefit from it.
"""

from __future__ import annotations

import io

import pytest
from pymarc import MARCReader

import marc_serials.store as store

from conftest import upload_marc


def _records(data: bytes) -> list:
    return [r for r in MARCReader(io.BytesIO(data)) if r is not None]


# ---------------------------------------------------------------------------
# Single-statement parsing
# ---------------------------------------------------------------------------

def test_parse_text_returns_a_preview(client):
    response = client.post("/api/parse-text",
                                     json={"text": "v.1:no.1(1990:Jan.)-v.5:no.4(1994:Dec.)"})
    assert response.status_code == 200

    body = response.get_json()
    assert body["parse"]["success"] is True
    assert body["preview"]["field_853"]
    assert body["preview"]["fields_863"]


def test_parse_text_requires_text(client):
    response = client.post("/api/parse-text", json={"text": ""})
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_parse_text_reports_rejected_convention_overrides(client):
    """
    A bad subfield code must come back as a warning rather than being applied.
    This route is the only place those rejections surface.
    """
    response = client.post("/api/parse-text", json={
        "text": "v.1(1990)-v.3(1992)",
        "convention": "standard",
        "subfields": {"vol": "z"},
    })
    assert response.status_code == 200
    warnings = response.get_json()["conversion"]["warnings"]
    assert any("$a-$m" in w for w in warnings)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def test_upload_lists_records(client, example_marc_bytes):
    response = upload_marc(client, example_marc_bytes)
    assert response.status_code == 200

    body = response.get_json()
    assert body["total"] == 5
    first = body["records"][0]
    assert set(first) >= {"index", "title", "issn", "location",
                          "fields_866", "has_853", "has_863"}
    assert first["title"] == "Journal of Imaginary Studies."


def test_upload_without_a_file_is_rejected(client):
    response = client.post("/api/upload-marc", data={},
                                     content_type="multipart/form-data")
    assert response.status_code == 400


def test_upload_of_non_marc_bytes_fails_as_json(client):
    """
    Even a hard failure has to come back as JSON -- the UI parses the response,
    and an HTML traceback page would surface as an unhelpful "unexpected token".
    """
    response = upload_marc(client, b"this is not a MARC file at all")
    assert response.status_code >= 400
    assert response.is_json
    assert "error" in response.get_json()


@pytest.mark.parametrize("route", ["/api/convert-record", "/api/preview-record",
                                   "/api/batch-convert"])
def test_conversion_routes_require_an_upload_first(client, route):
    response = client.post(route, json={"record_index": 0})
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_uploads_do_not_leak_between_clients(marc_app, example_marc_bytes,
                                             messy_marc_bytes, tmp_path, monkeypatch):
    """
    Each client carries its own cookie jar, so each gets its own session and its
    own file on disk. This is what lets the rest of the suite upload freely
    without tests treading on each other.
    """
    upload_dir = tmp_path / "shared-uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(store, "UPLOAD_DIR", str(upload_dir))
    marc_app.app.config.update(TESTING=True, SECRET_KEY="test-secret-key")

    # Not `with` blocks: two nested test-client contexts unwind out of order.
    # Plain clients are enough here, since nothing inspects the request context.
    first = marc_app.app.test_client()
    second = marc_app.app.test_client()

    upload_marc(first, example_marc_bytes)
    upload_marc(second, messy_marc_bytes)

    assert first.post("/api/batch-convert", json={}).get_json()["records_processed"] == 5
    # 11 records in the messy corpus, one of which carries no 866 and is skipped.
    assert second.post("/api/batch-convert", json={}).get_json()["records_processed"] == 10


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def test_preview_does_not_modify_stored_data(client, example_marc_bytes):
    """
    Preview promises to be read-only. If it ever wrote, a cataloguer clicking
    through records would silently accumulate conversions they never confirmed.
    """
    upload_marc(client, example_marc_bytes)
    before = client.get("/api/download-converted").data

    response = client.post("/api/preview-record", json={"record_index": 0})
    assert response.status_code == 200

    after = client.get("/api/download-converted").data
    assert after == before


def test_preview_pairs_each_statement_with_its_source(client, example_marc_bytes):
    upload_marc(client, example_marc_bytes)
    body = client.post("/api/preview-record",
                                 json={"record_index": 0}).get_json()
    assert body["previews"]
    for preview in body["previews"]:
        assert preview["source_866"]


# ---------------------------------------------------------------------------
# Batch conversion and download
# ---------------------------------------------------------------------------

def test_batch_convert_summarises_every_record(client, example_marc_bytes):
    upload_marc(client, example_marc_bytes)
    body = client.post("/api/batch-convert",
                                 json={"convention": "standard"}).get_json()

    assert body["success"] is True
    assert body["records_processed"] == 5
    # Record 3 converts two of its three statements. "34 no 3, 4 (Summer, Autumn
    # 1990)" is a discontinuous list and now converts to two 863s; the third,
    # "v. 58 Suppl. (Sep 2003)", is beyond the parser and keeps its 866.
    assert [s["converted_fields"] for s in body["summary"]] == [2, 1, 2, 2, 2]


def test_the_headline_does_not_count_skipped_records(client, example_marc_bytes):
    """
    A skipped record has a row in the summary, and the headline used to count
    rows. Skipping three of five read "5 records converted" beside "3 records
    skipped", although those three came out exactly as they went in.
    """
    upload_marc(client, example_marc_bytes)
    body = client.post("/api/batch-convert",
                       json={"skip_records": [0, 1, 2]}).get_json()

    assert body["skipped_records"] == 3
    assert body["records_processed"] == 2
    assert body["records_processed"] == len(body["converted_indexes"])


def test_download_returns_valid_marc(client, example_marc_bytes):
    upload_marc(client, example_marc_bytes)
    client.post("/api/batch-convert", json={"convention": "standard"})

    response = client.get("/api/download-converted")
    assert response.status_code == 200
    assert response.mimetype == "application/marc"
    assert "holdings_converted.mrc" in response.headers["Content-Disposition"]

    records = _records(response.data)
    assert len(records) == 5
    assert records[0].get_fields("853")
    assert records[0].get_fields("863")


def test_download_before_upload_is_not_found(client):
    assert client.get("/api/download-converted").status_code == 404


def test_batch_convert_is_idempotent(client, example_marc_bytes):
    """
    Converting a second time must not stack another set of 863s on top of the
    first. Byte equality is the strongest form of this and currently holds.
    """
    upload_marc(client, example_marc_bytes)
    client.post("/api/batch-convert", json={"convention": "standard"})
    first = client.get("/api/download-converted").data

    client.post("/api/batch-convert", json={"convention": "standard"})
    second = client.get("/api/download-converted").data

    assert first == second


def test_keeping_the_source_866_is_possible(client, example_marc_bytes):
    upload_marc(client, example_marc_bytes)
    client.post("/api/batch-convert",
                          json={"convention": "standard", "remove_866": False})

    records = _records(client.get("/api/download-converted").data)
    assert records[0].get_fields("866")
    assert records[0].get_fields("853")


def test_messy_corpus_converts_without_error(client, messy_marc_bytes):
    """The awkward corpus must survive the whole pipeline, warnings and all."""
    upload_marc(client, messy_marc_bytes)
    body = client.post("/api/batch-convert", json={}).get_json()

    assert body["success"] is True
    # Ten of eleven: "Index of Absent Holdings" carries no 866 at all and is
    # skipped before conversion rather than summarised as a zero-field record.
    assert body["records_processed"] == 10
    # Every record still comes back, including the one that was skipped --
    # nothing is dropped from the file just because it had nothing to convert.
    assert len(_records(client.get("/api/download-converted").data)) == 11


# ---------------------------------------------------------------------------
# Per-statement 866 stripping (0.5.2)
#
# Stripping used to be decided for the whole record, which destroyed holdings
# the parser could not read. These pin the per-statement rule from both routes.
# ---------------------------------------------------------------------------

def test_batch_keeps_the_866_of_an_unconverted_statement(client,
                                                         messy_marc_bytes):
    """
    Messy record 5 carries three statements: "?: 16" and "? 106" are held for
    review, "2016?" converts. Only the converted one's 866 may be removed.

    remove_866 is asked for explicitly. The retired standalone converter
    stripped by default; the application keeps the originals unless told
    otherwise, which is the safer default and the one the workbench has used
    since 0.6.x -- so a test about the stripping rules has to turn stripping on.
    """
    upload_marc(client, messy_marc_bytes)
    client.post("/api/batch-convert", json={"remove_866": True})

    record = _records(client.get("/api/download-converted").data)[5]
    remaining = sorted((f["a"] or "") for f in record.get_fields("866"))

    assert remaining == ["? 106", "?: 16"]
    assert record.get_fields("863")          # the converted one did convert


def test_single_record_route_keeps_unconverted_866s(client,
                                                    example_marc_bytes):
    """
    The single-statement route used to strip every 866 before conversion had
    even run, so it destroyed review statements the batch route protected.

    Each statement asks for its own 866 to go, which is how the screen sends
    them. The retired standalone converter defaulted that to on; the application
    keeps the original unless told otherwise.
    """
    upload_marc(client, example_marc_bytes)
    response = client.post("/api/convert-record", json={
        "record_index": 3,
        "conversions": [{"text": "34 no 3, 4 (Summer, Autumn 1990)",
                         "remove_866": True},
                        {"text": "39 no 1 (Spring 1995)", "remove_866": True},
                        {"text": "v. 58 Suppl. (Sep 2003)", "remove_866": True}],
    })
    assert response.status_code == 200

    # The statements that converted have their 866s removed; the one that did
    # not keeps its own. Asserting which field survived rather than how many
    # says what the route is actually for.
    record = _records(client.get("/api/download-converted").data)[3]
    surviving = [(f["a"] or "").strip() for f in record.get_fields("866")]
    assert surviving == ["v. 58 Suppl. (Sep 2003)"]


def test_an_edited_statement_never_deletes_an_866(client,
                                                  example_marc_bytes):
    """
    Statement text arrives from the client and may have been edited in the UI.
    A spec matching no 866 on the record must leave every field alone rather
    than guessing which one it meant.
    """
    upload_marc(client, example_marc_bytes)
    client.post("/api/convert-record", json={
        "record_index": 0,
        "conversions": [{"text": "v.99(2099)-v.100(2100)"}],   # not on the record
    })

    record = _records(client.get("/api/download-converted").data)[0]
    assert len(record.get_fields("866")) == 2


# ---------------------------------------------------------------------------
# Encoding level: reported, never rewritten
# ---------------------------------------------------------------------------

def test_a_file_whose_leader_disagrees_is_reported_once_not_per_record(
        client, example_marc_bytes):
    """
    Replaces a check that fired on every row.

    It used to compare each record's Leader/17 against the declared level and
    mark the row when they differed. On a real 372-record Alma export -- every
    record declaring level 3, a library recording at level 4 -- that marked 371
    of them, and pushed all 371 into "Needs attention". The cataloguer who hit
    it said a signal on almost every record takes away the value it is supposed
    to provide, and was right: that comparison is a fact about the file, and no
    per-row marker can carry one.

    It is now counted once. The records stay reachable through a filter, which
    is what serves the other file -- the one where three records disagree and
    finding those three is the whole job.
    """
    upload_marc(client, example_marc_bytes)
    body = client.post("/api/review-index", json={}).get_json()

    summary = body["encoding_level"]
    assert summary, "a file declaring level 3 throughout must say so once"
    assert summary["declared"] == "4"
    assert summary["records"] == summary["total"] == len(body["records"])
    assert summary["levels"] == {"3": summary["records"]}

    assert [r for r in body["records"] if r.get("leader_note")] == [], (
        "a file-wide fact must not be a marker on every row")
    assert all(r["leader_mismatch"] for r in body["records"]), (
        "the records must stay findable even without a marker")


def test_recording_at_level_3_marks_the_records_that_are_not_summary(
        client, example_marc_bytes):
    """
    The per-record question, which genuinely varies.

    Level 3 is summary holdings -- "only the highest levels (first-order
    designators)", Z39.71 4.3. An 863 carrying a volume, an issue, a year and a
    month is not that, and saying so about the records where it is true is
    worth a marker. On the export above this is 242 records of 371; the other
    129 are summary and are left alone.
    """
    upload_marc(client, example_marc_bytes)
    rows = client.post("/api/review-index",
                       json={"holdings_level": "3"}).get_json()["records"]

    noted = [r for r in rows if r.get("leader_note")]
    assert noted, "no record was reported as carrying more than level 3"
    assert len(noted) < len(rows), (
        "every record flagged is the defect this replaced, not a finding")
    assert "level 3" in noted[0]["leader_note"]


def test_recording_at_level_4_marks_nothing_because_nothing_can_exceed_it(
        client, example_marc_bytes):
    """
    Level 4 is "the most specific levels (including all hierarchical levels)",
    so no amount of detail contradicts it -- and a serial numbered by volume
    alone is not under-reporting by having one level. The default therefore
    marks no records at all, which is what makes the marker mean something
    when it does appear.
    """
    upload_marc(client, example_marc_bytes)
    rows = client.post("/api/review-index", json={}).get_json()["records"]
    assert [r for r in rows if r.get("leader_note")] == []


def test_the_leader_is_not_rewritten(client, example_marc_bytes):
    """
    The other half of the same decision, and the one worth a test of its own:
    whatever the note says, the bytes that come back must carry the Leader the
    file arrived with.
    """
    import io
    from pymarc import MARCReader

    before = [str(r.leader) for r in MARCReader(io.BytesIO(example_marc_bytes))
              if r is not None]
    upload_marc(client, example_marc_bytes)
    client.post("/api/batch-convert", json={"convention": "standard"})
    data = client.get("/api/download-converted").data
    after = [str(r.leader) for r in MARCReader(io.BytesIO(data)) if r is not None]

    assert len(after) == len(before)
    for index, (was, now) in enumerate(zip(before, after)):
        # Leader/00-04 is the record length and /12-16 the base address; both
        # are recomputed when pymarc writes the record out and are not ours.
        assert now[5:12] == was[5:12], f"record {index}: Leader/05-11 changed"
        assert now[17:] == was[17:], f"record {index}: Leader/17 onward changed"


def _one_record_file(leader: str, statement: str) -> bytes:
    """A single synthetic record, for pinning what the Leader check says."""
    from pymarc import Record, Field, Subfield, MARCWriter
    import io

    buf = io.BytesIO()
    writer = MARCWriter(buf)
    rec = Record()
    rec.leader = leader
    rec.add_field(Field(tag="001", data="lvltest"))
    rec.add_field(Field(tag="245", indicators=["0", "0"],
                        subfields=[Subfield(code="a", value="Level Test Serial.")]))
    rec.add_field(Field(tag="866", indicators=[" ", "0"],
                        subfields=[Subfield(code="a", value=statement)]))
    writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def test_a_record_already_at_the_declared_level_is_not_reported(client):
    """
    The guard on the guard: flagging every record would flag nothing.

    A record declaring level 4, converted by a library reporting at level 4 --
    the default -- has nothing to be told. Note that what matters is the two
    levels agreeing, not how much detail the statement happens to carry: the
    level is a declaration of practice, not a measurement of a field. Which is
    what the 129 LC examples establish: four subfield shapes are marked both
    ways, covering 89 of them, so no rule derived from content can hold. See
    CORPUS-FINDINGS.
    """
    # /17 = 4: the same leader as the fixtures but declaring detailed holdings.
    data = _one_record_file("00522cy  a22001454n 4500", "v.1(1990)-v.10(1999)")
    upload_marc(client, data)
    rows = client.post("/api/review-index", json={}).get_json()["records"]
    assert [r for r in rows if r.get("leader_note")] == []


def test_declaring_the_level_a_record_already_says_silences_the_summary(client):
    """
    The other side of it, and the reason the setting exists. A file of records
    declaring level 3 has nothing to report once the library says it records
    at level 3 -- and their 863s then carry 3 too, so each record agrees with
    itself throughout.
    """
    data = _one_record_file("00522cy  a22001453n 4500", "v. 1 no. 2 (1990)")
    upload_marc(client, data)

    default = client.post("/api/review-index", json={}).get_json()
    assert default["encoding_level"], (
        "with the default level 4 this file should be reported once")

    declared3 = client.post("/api/review-index",
                            json={"holdings_level": "3"}).get_json()
    assert declared3["encoding_level"] is None, (
        "declaring level 3 should agree with a file that says 3")
    assert not any(r["leader_mismatch"] for r in declared3["records"])

    preview = client.post("/api/preview-records",
                          json={"indices": [0], "holdings_level": "3"}).get_json()
    fields = preview["records"][0]["previews"][0]["fields_863"]
    assert fields[0].startswith("863 3"), fields[0]


def test_the_declared_level_reaches_the_downloaded_file(client):
    """
    The setting has to survive as far as the file, not just the preview.

    The screen is where a cataloguer checks the level; the download is what
    reaches the catalogue. Those are two code paths, and a setting honoured on
    one and dropped on the other would look right and load wrong.
    """
    from pymarc import MARCReader

    upload_marc(client, _one_record_file("00522cy  a22001453n 4500",
                                         "v. 1 no. 2 (1990)"))
    res = client.post("/api/batch-convert", json={"holdings_level": "3"})
    assert res.status_code == 200, res.get_data()

    got = client.get("/api/download-converted")
    assert got.status_code == 200
    records = list(MARCReader(got.data))
    fields = records[0].get_fields("863")
    assert fields, "conversion produced no 863 to check"
    for field in fields:
        assert field.indicator1 == "3", (
            f"downloaded 863 says level {field.indicator1}, not the declared 3")


def test_the_default_level_is_what_the_tool_wrote_before_the_setting(client):
    """
    Nothing moves for a cataloguer who never opens Conversion settings.

    The first indicator was the constant "4" before this was a choice, so the
    default has to produce that, and an unusable value has to fall back to it
    rather than write a level nobody declared. MARC has no "unspecified" here:
    whatever goes in the indicator is a claim about the holdings.
    """
    from pymarc import MARCReader

    upload_marc(client, _one_record_file("00522cy  a22001453n 4500",
                                         "v. 1 no. 2 (1990)"))

    for payload in ({}, {"holdings_level": ""}, {"holdings_level": "9"},
                    {"holdings_level": None}, {"holdings_level": "detailed"}):
        res = client.post("/api/batch-convert", json=payload)
        assert res.status_code == 200, (payload, res.get_data())
        records = list(MARCReader(client.get("/api/download-converted").data))
        fields = records[0].get_fields("863")
        assert fields, (payload, "conversion produced no 863 to check")
        for field in fields:
            assert field.indicator1 == "4", (
                f"{payload} produced level {field.indicator1}, not the default 4")


def test_a_single_part_coding_contradicted_by_its_own_holdings_is_counted(client):
    """
    Leader/06 = x is "Single-part item holdings" -- complete in one piece. A
    record whose holdings name a volume is not that.

    Counted for the file rather than marked per row, for the reason 0.16.1
    settled: on a file migrated from an ILS that kept no MARC holdings this is
    true of almost every record, and a marker on almost every row carries
    nothing. Measured on a real 372-record export: 334 coded x, 331 of them
    contradicted.

    What it should be instead is not decided here -- v is multipart and y is
    serial, and no holdings statement settles which.
    """
    from pymarc import Field, MARCWriter, Record, Subfield
    import io

    def one(leader06: str, statement: str) -> Record:
        rec = Record()
        rec.leader = f"00522c{leader06}  a22001453n 4500"
        rec.add_field(Field(tag="866", indicators=[" ", "0"],
                            subfields=[Subfield(code="a", value=statement)]))
        return rec

    buf = io.BytesIO()
    writer = MARCWriter(buf)
    writer.write(one("x", "v. 1-5 (1990-1994)"))   # contradicted: numbered parts
    writer.write(one("x", "(2010)"))               # left alone: could be one part
    writer.write(one("y", "v. 1-5 (1990-1994)"))   # already coded as a serial
    writer.close(close_fh=False)

    upload_marc(client, buf.getvalue())
    body = client.post("/api/review-index", json={}).get_json()

    assert body["single_part"] == 1, (
        "only the record coded x whose holdings name numbered parts counts")
    flagged = [r for r in body["records"] if r["single_part"]]
    assert len(flagged) == 1 and flagged[0]["index"] == 0

    # And it is counted, not marked: nothing new appears beside a row.
    assert all(not r.get("leader_note") for r in body["records"])


def test_holdings_beyond_the_declared_level_are_counted_not_marked(
        client, example_marc_bytes):
    """
    The third time this shape came up, and the last: a majority is not a signal.

    Recording at level 3 against a file of detailed holdings marked 242 of 371
    rows. The cataloguer who hit it said it still felt like too many, and was
    right -- 65% of a file is a property of the file, not a flag on a record.
    It is counted in a line above the list, where it can be read once and acted
    on in the catalogue.

    The count reaches the screen, so the number is visible somewhere. Before
    this it existed only as markers spread over twenty-five pages of ten rows,
    and the one place a total appeared was a filter chip that also gathered the
    unrelated Leader/06 records -- so the figure shown was neither count.
    """
    upload_marc(client, example_marc_bytes)
    body = client.post("/api/review-index",
                       json={"holdings_level": "3"}).get_json()

    assert body["beyond_level"] > 0, "nothing was found to count"
    assert body["beyond_level"] < body["with_holdings"], (
        "every record counted is the defect this replaced, not a finding")
    assert body["declared_level"] == "3"

    # Still carried per record, so the filter can gather exactly those.
    noted = [r for r in body["records"] if r.get("leader_note")]
    assert len(noted) == body["beyond_level"]


def test_the_default_level_counts_nothing_beyond_itself(client,
                                                        example_marc_bytes):
    """Level 4 is every level, so nothing can exceed it and nothing is said."""
    upload_marc(client, example_marc_bytes)
    body = client.post("/api/review-index", json={}).get_json()
    assert body["beyond_level"] == 0


def test_generated_fields_are_written_in_tag_order(client):
    """
    A record read in as 852, 866, 999 must not come back as 852, 866, 999,
    853, 863.

    Appending is valid MARC and wrong to every eye that reads it: the field
    defining the pattern ends up after the textual holdings it explains, and
    after the local numbers a system puts at the end. Reported from use, after
    a download was opened and read.

    pymarc inserts before the first higher tag and scans past equal ones, so
    an 853 lands before its 863s and linked 863s keep the sequence they were
    generated in -- which is the part that would be silently wrong if the
    insert sorted equal tags among themselves.
    """
    import io
    from pymarc import Field, MARCReader, MARCWriter, Record, Subfield

    buf = io.BytesIO()
    writer = MARCWriter(buf)
    rec = Record()
    rec.leader = "00522cy  a22001453n 4500"
    rec.add_field(Field(tag="001", data="order-test"))
    rec.add_field(Field(tag="852", indicators=["8", " "],
                        subfields=[Subfield(code="b", value="MAIN")]))
    rec.add_field(Field(tag="866", indicators=[" ", "0"],
                        subfields=[Subfield(code="a",
                                            value="v. 1 no. 1 (1990)-v. 3 no. 4 (1992)")]))
    # The local field a system appends, which is what the new fields were
    # landing after.
    rec.add_field(Field(tag="999", indicators=[" ", " "],
                        subfields=[Subfield(code="b", value="991000000000001")]))
    writer.write(rec)
    writer.close(close_fh=False)

    upload_marc(client, buf.getvalue())
    assert client.post("/api/batch-convert", json={}).status_code == 200

    with client.get("/api/download-converted") as got:
        converted = list(MARCReader(io.BytesIO(got.data)))[0]

    tags = [f.tag for f in converted.get_fields()]
    assert tags == sorted(tags), tags
    assert tags.index("853") > tags.index("852")
    assert tags.index("853") < tags.index("863") < tags.index("866")
    assert tags.index("866") < tags.index("999")


def test_a_record_already_out_of_order_is_not_quietly_reordered(client):
    """
    Two records of the 372-record file this was reported from carry their
    control fields out of order -- 008 before 007, 008 before 005 -- in the
    source, before this tool sees them.

    The new fields go where they belong; the existing ones are left exactly as
    found. Tidying them would be a change nobody asked for, made to a record
    somebody else's system wrote, and hidden inside a conversion.
    """
    import io
    from pymarc import Field, MARCReader, MARCWriter, Record, Subfield

    buf = io.BytesIO()
    writer = MARCWriter(buf)
    rec = Record()
    rec.leader = "00522cy  a22001453n 4500"
    rec.add_field(Field(tag="001", data="unordered"))
    rec.add_field(Field(tag="008", data="x" * 32))
    rec.add_field(Field(tag="005", data="20200331173704.0"))   # after 008
    rec.add_field(Field(tag="852", indicators=["8", " "],
                        subfields=[Subfield(code="b", value="MAIN")]))
    rec.add_field(Field(tag="866", indicators=[" ", "0"],
                        subfields=[Subfield(code="a", value="v.1-3 (1990-1992)")]))
    writer.write(rec)
    writer.close(close_fh=False)

    upload_marc(client, buf.getvalue())
    client.post("/api/batch-convert", json={})
    with client.get("/api/download-converted") as got:
        converted = list(MARCReader(io.BytesIO(got.data)))[0]

    tags = [f.tag for f in converted.get_fields()]
    assert tags.index("008") < tags.index("005"), (
        "the source order of existing fields was changed: " + str(tags))
    assert tags.index("852") < tags.index("853") < tags.index("866"), tags
