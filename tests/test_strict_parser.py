"""
The strict setting: the standard parser writes only what it reads in full.

Asked for with portability in mind. The parser follows MARC 21 and Z39.71
conventions, and on a statement that goes beyond them it converts what it can
and names what it left out. For the collection it was built on that is the
right trade; for another library's holdings, a partial reading is a guess
nobody asked for. Strict holds those statements instead -- nothing written,
866 kept, the reason in the log -- and leaves alone anything a confirmed
pattern matches, because that shape is one the cataloguer has already vouched
for.

Measured when it was added (default -> strict, statements converted):

    main corpus           112 -> 90 of 117   (22 converted with a warning)
    LC examples             5 -> 4 of 7
    real 372-record file 1055 -> 931 of 1057, nearly all of the 124 held for
                         one end of a range giving a month or level the other
                         does not
"""

from __future__ import annotations

import io

from pymarc import Field, MARCReader, MARCWriter, Record, Subfield

from conftest import upload_marc
from marc_serials.bridge import (PARSER_SOURCE, STRICT_FALLBACK, apply_patterns,
                                 infer_roles)
from marc_serials.library import ConfirmedPattern
from marc_serials.converter import convert_holdings
from marc_serials.detector import detect_patterns


PARTIAL = "no.56(2003:Dec./2004:Jan.)"     # the year is read, then refused
WHOLE = "v. 36-49 (1961-1974)"


def test_a_partial_reading_is_held_and_says_why():
    result, source = apply_patterns(PARTIAL, [], STRICT_FALLBACK)
    assert source == PARSER_SOURCE
    assert result.ranges == [] and result.needs_review
    assert result.warnings[0].startswith("Held by the strict setting")
    assert any("2003:Dec./2004:Jan." in w for w in result.warnings[1:])


def test_a_whole_reading_converts_as_before():
    strict, _ = apply_patterns(WHOLE, [], STRICT_FALLBACK)
    default, _ = apply_patterns(WHOLE, [], True)
    assert [str(f) for f in convert_holdings(strict).fields_863] == \
           [str(f) for f in convert_holdings(default).fields_863] != []


def test_without_strict_the_partial_reading_still_converts():
    result, _ = apply_patterns(PARTIAL, [], True)
    assert convert_holdings(result).fields_863


def test_a_statement_nothing_was_read_from_keeps_its_own_words():
    result, _ = apply_patterns("?: 16", [], STRICT_FALLBACK)
    assert not any(w.startswith("Held by the strict") for w in result.warnings)


def test_a_confirmed_pattern_is_not_second_guessed():
    group = detect_patterns([PARTIAL])[0]
    pattern = ConfirmedPattern(id="p1", label=group.human_label, regex=group.regex,
                               roles=infer_roles(group.named_groups))
    result, source = apply_patterns(PARTIAL, [pattern], STRICT_FALLBACK)
    assert source == "p1"
    assert convert_holdings(result).fields_863


def _file(*statements) -> bytes:
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for n, statement in enumerate(statements):
        rec = Record()
        rec.leader = "00522cy  a22001453n 4500"
        rec.add_field(Field(tag="001", data=f"strict-{n}"))
        rec.add_field(Field(tag="866", indicators=["4", "1"],
                            subfields=[Subfield("a", statement)]))
        writer.write(rec)
    writer.close(close_fh=False)
    return buf.getvalue()


def test_the_file_keeps_the_held_866_and_the_log_says_why(client):
    upload_marc(client, _file(WHOLE, PARTIAL))
    client.post("/api/batch-convert", json={"parser_strict": True,
                                            "remove_866": True})
    with client.get("/api/download-converted") as got:
        whole, partial = list(MARCReader(got.data))

    assert whole.get_fields("863") and not whole.get_fields("866")
    assert not partial.get_fields("863")
    assert [f.get("a") for f in partial.get_fields("866")] == [PARTIAL]

    log = client.get("/api/download-log").get_data(as_text=True)
    assert "Held by the strict setting" in log


def test_strict_means_nothing_with_the_parser_off(client):
    upload_marc(client, _file(WHOLE))
    client.post("/api/batch-convert", json={
        "parser_fallback": False, "parser_strict": True})
    with client.get("/api/download-converted") as got:
        assert not list(MARCReader(got.data))[0].get_fields("863")
