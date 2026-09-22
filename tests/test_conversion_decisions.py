"""
The converted file is built from every decision, not from the last click.

Before 0.18.0 each conversion route reloaded the *uploaded* file, applied the
one thing it had been sent and saved the result over the previous save. So a
cataloguer working through their file a record at a time ended up with a
download containing the last record they had converted and no sign that the
rest had been dropped: the Download button was lit the whole time, and the
per-record Convert buttons reported success on every record.

Measured on data/example_holdings.mrc before the change -- (853s, 863s) per
record in the downloaded file:

    after upload            0,0   0,0   0,0   0,0   0,0
    convert record 0        1,2   0,0   0,0   0,0   0,0
    convert record 1        0,0   1,1   0,0   0,0   0,0
                            ^^^ record 0 back as it came in

These tests are that table, and the rules that follow from rebuilding instead.
"""

from __future__ import annotations

import io

from pymarc import MARCReader, MARCWriter

from conftest import upload_marc


def _records(data: bytes) -> list:
    return [r for r in MARCReader(io.BytesIO(data)) if r is not None]


def _to_bytes(records: list) -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for record in records:
        writer.write(record)
    writer.close(close_fh=False)
    return buf.getvalue()


def _downloaded(client) -> list:
    return _records(client.get("/api/download-converted").data)


def _generated(record) -> tuple:
    """How many of each generated field the record carries."""
    return len(record.get_fields("853")), len(record.get_fields("863"))


def _convert_record(client, records, index, **extra):
    """Convert one record the way the screen does: every 866 on it at once."""
    payload = {
        "record_index": index,
        "conversions": [{"text": f["a"]}
                        for f in records[index].get_fields("866") if f["a"]],
    }
    for conversion in payload["conversions"]:
        conversion.update(extra.pop("per_statement", {}))
    payload.update(extra)
    response = client.post("/api/convert-record", json=payload)
    assert response.status_code == 200, response.data
    return response.get_json()


# ---------------------------------------------------------------------------
# One record at a time
# ---------------------------------------------------------------------------

def test_converting_a_second_record_does_not_undo_the_first(
        client, example_marc_bytes):
    """The defect above, in one assertion."""
    upload_marc(client, example_marc_bytes)
    source = _records(example_marc_bytes)

    _convert_record(client, source, 0)
    first = _generated(_downloaded(client)[0])
    assert first != (0, 0), "record 0 was not converted at all"

    _convert_record(client, source, 1)
    after = _downloaded(client)
    assert _generated(after[0]) == first, (
        "converting record 1 threw away the conversion of record 0")
    assert _generated(after[1]) != (0, 0)


def test_a_record_converted_twice_produces_the_same_file(
        client, example_marc_bytes):
    """
    Re-converting a record replaces its decision rather than stacking on it.

    This is why the rebuild reads each record fresh from the upload: applying a
    decision to a record that has already had it applied would write the 863s
    again.
    """
    upload_marc(client, example_marc_bytes)
    source = _records(example_marc_bytes)

    _convert_record(client, source, 2)
    once = client.get("/api/download-converted").data
    _convert_record(client, source, 2)
    assert client.get("/api/download-converted").data == once


def test_every_record_converted_on_its_own_is_in_the_file(
        client, example_marc_bytes):
    upload_marc(client, example_marc_bytes)
    source = _records(example_marc_bytes)

    for index in (0, 1, 2, 4):
        body = _convert_record(client, source, index)
    assert body["records_with_decisions"] == 4

    downloaded = _downloaded(client)
    assert [i for i, r in enumerate(downloaded)
            if _generated(r) != (0, 0)] == [0, 1, 2, 4]
    # Record 3 was never converted and must be untouched, not emptied.
    assert len(downloaded[3].get_fields("866")) == 3


# ---------------------------------------------------------------------------
# The run over the whole file, afterwards
# ---------------------------------------------------------------------------

def test_convert_all_keeps_the_settings_a_record_was_converted_with(
        client, example_marc_bytes):
    """
    A cataloguer's decision about one record outranks the settings on the run
    over everything, because they made it about that record.

    Removing the 866 is the visible difference: the record converted on its own
    asked for it, the run over the file did not.
    """
    upload_marc(client, example_marc_bytes)
    source = _records(example_marc_bytes)

    _convert_record(client, source, 1, per_statement={"remove_866": True})
    response = client.post("/api/batch-convert",
                           json={"remove_866": False})
    assert response.status_code == 200
    body = response.get_json()
    assert body["own_decisions"] == 1

    downloaded = _downloaded(client)
    assert downloaded[1].get_fields("866") == [], (
        "the run over the file redid a record its cataloguer had already "
        "converted, and undid the removal they asked for")
    # Everything else keeps its 866, which is what the run was told to do.
    assert downloaded[0].get_fields("866")
    assert _generated(downloaded[0]) != (0, 0)


def test_a_skipped_record_is_left_alone_even_when_converted_on_its_own(
        client, example_marc_bytes):
    """
    Skipping is the stronger instruction -- it is the one that means "I am
    cataloguing this by hand" -- but it must say what it is overriding.
    """
    upload_marc(client, example_marc_bytes)
    source = _records(example_marc_bytes)

    _convert_record(client, source, 0)
    response = client.post("/api/batch-convert", json={"skip_records": [0]})
    body = response.get_json()

    assert body["skipped_own_decisions"] == 1, (
        "a skip that quietly discards a conversion the cataloguer ran by hand "
        "is exactly the silence this rebuild exists to remove")
    assert _generated(_downloaded(client)[0]) == (0, 0)
    assert 0 not in body["converted_indexes"]


def test_clearing_the_skip_brings_the_held_decision_back(
        client, example_marc_bytes):
    """
    The decision is set aside by a skip, not thrown away.

    Asked with a setting only the held decision carries -- it removed the 866,
    and neither run over the file does -- so a record the second run merely
    converted from scratch could not pass this.
    """
    upload_marc(client, example_marc_bytes)
    source = _records(example_marc_bytes)

    _convert_record(client, source, 0, per_statement={"remove_866": True})
    assert _downloaded(client)[0].get_fields("866") == []

    client.post("/api/batch-convert",
                json={"skip_records": [0], "remove_866": False})
    restored = _downloaded(client)[0]
    assert _generated(restored) == (0, 0)
    assert len(restored.get_fields("866")) == 2

    client.post("/api/batch-convert",
                json={"skip_records": [], "remove_866": False})
    back = _downloaded(client)[0]
    assert _generated(back) != (0, 0)
    assert back.get_fields("866") == [], (
        "the run over the file reconverted record 0 from scratch instead of "
        "restoring the decision held for it")


def test_a_new_upload_forgets_every_decision(client, example_marc_bytes,
                                             messy_marc_bytes):
    """
    A decision is keyed by position in the file, and a position means nothing
    once the file behind it has changed.
    """
    upload_marc(client, example_marc_bytes)
    _convert_record(client, _records(example_marc_bytes), 0)
    assert _generated(_downloaded(client)[0]) != (0, 0)

    upload_marc(client, messy_marc_bytes, filename="messy.mrc")
    downloaded = _downloaded(client)
    assert len(downloaded) == len(_records(messy_marc_bytes))
    # 863 rather than 853: two records in this fixture carry an 853 of their
    # own, and what a conversion leaves behind is the 863.
    assert not any(r.get_fields("863") for r in downloaded), (
        "a decision made about the last file was applied to this one")


# ---------------------------------------------------------------------------
# One record, downloaded on its own
# ---------------------------------------------------------------------------

def test_one_record_downloads_on_its_own_converted(client, example_marc_bytes):
    upload_marc(client, example_marc_bytes)
    _convert_record(client, _records(example_marc_bytes), 2)

    response = client.get("/api/download-record?index=2")
    assert response.status_code == 200
    only = _records(response.data)
    assert len(only) == 1
    assert _generated(only[0]) != (0, 0)
    assert only[0]["852"].value() == _records(example_marc_bytes)[2]["852"].value()


def test_a_record_downloaded_before_any_conversion_is_the_one_uploaded(
        client, example_marc_bytes):
    """No conversion yet is not an error: it is the record as it stands."""
    upload_marc(client, example_marc_bytes)
    response = client.get("/api/download-record?index=1")
    assert response.status_code == 200
    only = _records(response.data)
    assert len(only) == 1
    assert _generated(only[0]) == (0, 0)


def test_the_download_is_named_after_the_identifier(client, example_marc_bytes):
    """
    The cataloguer looks records up by their identifier, so that is what they
    will look for in their downloads folder.
    """
    client.post("/api/identifier", json={"spec": "001"})
    upload_marc(client, example_marc_bytes)

    response = client.get("/api/download-record?index=3")
    assert "holdings_exmpl0004.mrc" in \
        response.headers["Content-Disposition"]


def test_a_record_with_no_identifier_is_named_by_its_place_in_the_file(
        client, example_marc_bytes):
    """The fixture has no 999 $b, which is the default field."""
    upload_marc(client, example_marc_bytes)
    response = client.get("/api/download-record?index=3")
    assert "holdings_record_4.mrc" in response.headers["Content-Disposition"]


def test_an_identifier_cannot_name_the_file_whatever_it_contains(client):
    """
    The identifier comes out of the cataloguer's MARC file, so it is reduced to
    characters that are safe in a filename rather than trusted.
    """
    from pymarc import Field, Record, Subfield

    record = Record()
    record.leader = "00000ny  a2200000 n 4500"
    record.add_field(Field(tag="001", data="../../etc/passwd"))
    record.add_field(Field(tag="852", indicators=["8", " "],
                           subfields=[Subfield("h", "Journals")]))
    record.add_field(Field(tag="866", indicators=[" ", "0"],
                           subfields=[Subfield("a", "v.1(1990)")]))

    client.post("/api/identifier", json={"spec": "001"})
    upload_marc(client, _to_bytes([record]))

    disposition = client.get(
        "/api/download-record?index=0").headers["Content-Disposition"]
    assert "/" not in disposition.split("filename=")[-1]
    assert "holdings_.._.._etc_passwd.mrc" in disposition


def test_an_out_of_range_record_is_refused(client, example_marc_bytes):
    upload_marc(client, example_marc_bytes)
    assert client.get("/api/download-record?index=99").status_code == 404
    assert client.get("/api/download-record?index=-1").status_code == 404
    assert client.get("/api/download-record").status_code == 400
    assert client.get("/api/download-record?index=two").status_code == 400


def test_a_record_cannot_be_downloaded_with_no_file(client):
    assert client.get("/api/download-record?index=0").status_code == 404
