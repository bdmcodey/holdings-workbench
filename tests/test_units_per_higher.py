"""
853 $u -- how many parts of a level make one of the level above it.

MARC 21 853-855: "Number (or the code var or und) that specifies the total
number of parts that comprise the next higher level of enumeration. May be
used with each level of enumeration except the first level (subfield $a or $g)
because there is no higher level." The standard's own illustration is that a
quarterly publication requires 4 issues to make 1 volume.

Declared rather than derived, for the reason D18 settled for the holdings
level: it is a fact about the publication, not about the statement.
"v.1-5 (1990-1994)" is equally true of a monthly and a quarterly, and the
frequency does not settle it either -- a monthly with two volumes a year has
six issues to a volume, not twelve.
"""

from __future__ import annotations

import pytest

from marc_serials.converter import convert_holdings, resolve_units_per_higher
from marc_serials.parser import parse_866


def _853(statement: str, **kwargs) -> str:
    result = convert_holdings(parse_866(statement), **kwargs)
    field = result.field_853
    if field is None:
        return ""
    return " ".join(f"${sf.code} {sf.value}" for sf in field.subfields)


TWO_LEVEL = "v. 1 no. 1 (1990)-v. 5 no. 4 (1994)"
ONE_LEVEL = "v.1-10 (1963-1968)"


@pytest.mark.parametrize("raw, expected", [
    ("12", "12"), ("4", "4"), (" 6 ", "6"), ("999", "999"),
    ("var", "var"), ("UND", "und"),
    ("", ""), (None, ""), ("abc", ""), ("0", ""), ("1000", ""),
    # "Because subfield $u is variable in length, no leading zero is used for
    # a single-character number."
    ("04", ""),
])
def test_only_a_count_or_the_standards_two_codes_are_written(raw, expected):
    assert resolve_units_per_higher(raw) == expected


def test_it_sits_on_the_second_level_between_the_caption_and_the_continuity():
    """
    The standard's examples read "$bno.$u12$vr": caption, then $u, then $v.

    Position is the whole meaning here. $u after $b says how many issues make
    a volume; the same number after $a would say how many volumes make the
    thing above a volume, which does not exist.
    """
    got = _853(TWO_LEVEL, numbering_continuity="r", units_per_higher="12")
    assert "$a v. $b no. $u 12 $v r" in got, got


# "Series 1, v. 6 no. 1 (Summer/Fall 1992)" -- the one statement of the 112 the
# corpus produces an 853 for that goes three levels deep.
THREE_LEVEL = "Series 1, v. 6 no. 1 (Summer/Fall 1992)"


def test_on_three_levels_it_names_the_second_and_leaves_the_third_alone():
    """
    A single declared number answers one question, and it is not the deepest.

    "$a ser. $b v. $c no." asks two different things: how many volumes make a
    series, and how many issues make a volume. The cataloguer typed one
    number, and it means the level below the top -- volumes per series here.
    Putting it on $c instead would answer the other question with it, and
    putting it on both would state a number nobody gave twice.

    This is the case that separates "second level" from "last level"; on the
    two-level statements that are 89 of the 112, they are the same subfield
    and any test using one would pass either way.
    """
    got = _853(THREE_LEVEL, units_per_higher="12")
    assert "$a ser. $b v. $u 12 $c no." in got, got
    assert got.count("$u") == 1, got


def test_a_serial_numbered_by_volume_alone_never_takes_one():
    """
    "Not used with subfield $a or $g ... because there is no higher level."

    18 of the 117 corpus statements are one level deep. Writing $u on them
    would claim a level above the volume that the record does not have.
    """
    got = _853(ONE_LEVEL, numbering_continuity="r", units_per_higher="12")
    assert "$u" not in got, got


def test_declaring_nothing_writes_nothing():
    """
    The default has to leave output exactly as previous versions produced it:
    a $u nobody declared is a publication pattern nobody verified.
    """
    assert _853(TWO_LEVEL, numbering_continuity="r") == \
           _853(TWO_LEVEL, numbering_continuity="r", units_per_higher="")
    assert "$u" not in _853(TWO_LEVEL, numbering_continuity="r")


def test_an_unusable_value_writes_no_u_rather_than_a_wrong_one():
    """A malformed count would make the claim wrongly rather than not at all."""
    assert "$u" not in _853(TWO_LEVEL, numbering_continuity="r",
                            units_per_higher="1 a year")


def test_the_codes_the_standard_defines_are_written_as_themselves():
    got = _853(TWO_LEVEL, numbering_continuity="r", units_per_higher="var")
    assert "$u var" in got, got


def test_it_reaches_the_converted_file(client):
    """The screen is where it is checked; the file is what reaches the catalogue."""
    import io
    from pymarc import Field, MARCReader, MARCWriter, Record, Subfield
    from conftest import upload_marc

    buf = io.BytesIO()
    writer = MARCWriter(buf)
    rec = Record()
    rec.leader = "00522cy  a22001453n 4500"
    rec.add_field(Field(tag="001", data="u-test"))
    rec.add_field(Field(tag="866", indicators=[" ", "0"],
                        subfields=[Subfield(code="a", value=TWO_LEVEL)]))
    writer.write(rec)
    writer.close(close_fh=False)

    upload_marc(client, buf.getvalue())
    assert client.post("/api/batch-convert",
                       json={"units_per_higher": "12",
                             "numbering_continuity": "r"}).status_code == 200

    with client.get("/api/download-converted") as got:
        records = list(MARCReader(got.data))
    fields = records[0].get_fields("853")
    assert fields, "no 853 was written"
    codes = [sf.code for sf in fields[0].subfields]
    assert "u" in codes, codes
    assert fields[0].get("u") == "12"
    # Immediately after the caption it describes, before $v.
    assert codes.index("u") == codes.index("b") + 1, codes
