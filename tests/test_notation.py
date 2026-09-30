"""
The notation an 866 declares, said and never acted on.

An 866's second indicator names the notation of its $a: 0 non-standard, 1
Z39.71 or ISO 10324, 2 Z39.42, 7 the one its $2 names ("usnp", the US
Newspaper Program's). Asked for by the cataloguer with one condition: a
declaration that disagrees with the text must not break anything. So the
declaration never decides what is read. A note goes to the log where it
helps -- another notation declared, or text that looks like the Newspaper
Program's without declaring it -- as a warning that asks no decision.
"""

from __future__ import annotations

import io

import pytest
from pymarc import Field, MARCWriter, Record, Subfield

from conftest import upload_marc
from marc_serials.records import notation_note

USNP_TEXT = "m,s=[1955:8:11-1956:11:22][1960:10:20-1984:2:2]"
Z3971_TEXT = "v.1(1990)-v.3(1992)"


def _866(text, ind2="0", source=None):
    subfields = [Subfield("a", text)]
    if source:
        subfields.append(Subfield("2", source))
    return Field(tag="866", indicators=["3", ind2], subfields=subfields)


@pytest.mark.parametrize("text, ind2, source, says", [
    (USNP_TEXT, "0", None, "looks like US Newspaper Program notation"),
    (USNP_TEXT, "7", "usnp", "declares US Newspaper Program notation ($2 usnp). The tool"),
    (Z3971_TEXT, "7", "usnp", "does not look like it, and was read as Z39.71"),
    (Z3971_TEXT, "7", "local", "declares its notation as 'local'"),
])
def test_a_note_where_it_helps(text, ind2, source, says):
    assert says in (notation_note(_866(text, ind2, source)) or "")


@pytest.mark.parametrize("ind2", ["0", "1", " "])
def test_no_note_for_the_ordinary_case(ind2):
    assert notation_note(_866(Z3971_TEXT, ind2)) is None


def _upload(client, *fields):
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    rec = Record()
    rec.leader = "00522cy  a22001453n 4500"
    rec.add_field(Field(tag="001", data="notation"))
    for f in fields:
        rec.add_field(f)
    writer.write(rec)
    writer.close(close_fh=False)
    upload_marc(client, buf.getvalue())
    return client.post("/api/preview-record",
                       json={"record_index": 0}).get_json()["previews"]


def test_a_wrong_declaration_breaks_nothing(client):
    """Declared usnp, written in Z39.71: converted exactly as without $2."""
    [declared] = _upload(client, _866(Z3971_TEXT, "7", "usnp"))
    [plain] = _upload(client, _866(Z3971_TEXT, "0"))
    assert declared["fields_863"] == plain["fields_863"] != []
    assert declared["flagged"] is False
    assert any("was read as Z39.71" in w for w in declared["warnings"])
    # Said for the log, asking nothing: yellow, not "to check".
    assert declared["attention"] == []


def test_undeclared_newspaper_notation_is_pointed_out(client):
    [held] = _upload(client, _866(USNP_TEXT, "0"))
    assert held["fields_863"] == []
    assert any("looks like US Newspaper Program notation" in w
               for w in held["warnings"])


def test_the_log_carries_it(client):
    import csv
    _upload(client, _866(Z3971_TEXT, "7", "usnp"))
    client.post("/api/batch-convert", json={})
    response = client.get("/api/download-log")
    rows = list(csv.reader(io.StringIO(response.data.decode("utf-8-sig"))))
    assert any("was read as Z39.71" in cell for row in rows for cell in row)
