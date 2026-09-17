"""
Generate the synthetic "unkempt" .mrc fixture used by the test suite.

All titles, identifiers, and location codes below are invented — there is no
real institutional data here. Where create_example_mrc.py collects holdings
statements the parser handles cleanly, this file collects the awkward ones: the
chronology-first block grammar, slash-separated ranges, records that already
carry an 853, degenerate statements, and a run-on long enough to trip the
pattern detector's complexity guard.

Every entry names the code path it exists to reach, so the fixture stays
reviewable in a diff. Generating rather than hand-writing the binary keeps the
file regenerable and keeps the promise that no real holdings data enters the
repository.

Run:
    python scripts/create_messy_mrc.py
    # -> writes data/messy_holdings.mrc
"""

import os
from pymarc import Record, Field, Subfield

OUTPUT = os.path.join(os.path.dirname(__file__), "..", "data", "messy_holdings.mrc")

# (title, [866 $a statements], [853 subfields as (code, value) or None])
EXAMPLES = [
    # Chronology-first block grammar: single block, and a multi-year run-on.
    ("Yearbook of Invented Proceedings", [
        "1993: (1 [Feb])",
        "2019: (1-6 [Feb-Nov])2020: (7-12 [Jan-Dec])",
    ], None),

    # Volume stated before the parens — exercises positional role assignment,
    # where a number outside the parens is the volume rather than the issue.
    ("Chronicle of Notional Affairs", [
        "1949: 1 (1-6 [Apr-Sep])",
    ], None),

    # Slashes that must split into separate ranges, and slashes that must not:
    # v.7/8 is a combined volume and Jul./Aug. a combined month.
    ("Digest of Hypothetical Matters", [
        "v.1(1990)-v.3(1992) / v.5(1994)-v.8(1997)",
        "v.7/8(1996:Jul./Aug.)",
    ], None),

    # Already carries an 853 numbered $8 3 — the conform path. Converted 863s
    # should adopt link 3 rather than allocating a fresh one.
    ("Transactions of the Imaginary Society", [
        "v.1:no.1(1990)-v.2:no.4(1991)",
    ], [("8", "3"), ("a", "(year)"), ("b", "v."), ("c", "no.")]),

    # An 853 that declares only the volume while the data also carries a year —
    # too partial to conform to, so a full 853 is regenerated with a warning.
    ("Papers on Fictitious Methods", [
        "v.4(1993)-v.9(1998)",
    ], [("8", "1"), ("a", "v.")]),

    # Degenerate forms: held for review, uncertain year, bare number.
    ("Occasional Notes of Nowhere", [
        "?: 16",
        "2016?",
        "? 106",
    ], None),

    # Long enough to exceed MAX_PATTERN_TOKENS, so the detector reports a
    # finding instead of emitting a regex nobody could read.
    ("Register of Elaborate Runs", [
        "1977: (46[Jul], 48-51[Sep-Dec])"
        "1978: (52-60[Jan-Jun], 61-70[Jul-Dec])"
        "1979: (71-80[Jan-Jun], 81-90[Jul-Dec])",
    ], None),

    # Cataloguer notes and unexplained markers — both warning-only, and both
    # must still parse rather than being discarded.
    ("Annual of Bracketed Asides", [
        "1993: {Memorial Issue} (1 [Feb])",
        "N 1994: (2 [Mar])",
    ], None),

    # Two statements sharing one publication pattern — they must share a single
    # 853 and receive $8 1.1 and 1.2 rather than an 853 each.
    ("Gazette of Repeated Patterns", [
        "v.1(1990)-v.10(1999)",
        "v.12(2001)-v.15(2004)",
    ], None),

    # No holdings at all: batch conversion must skip it without raising.
    # Ranges written with spaces around the separator, which is at least as
    # common as writing them tight. Nothing in this corpus had them, which is
    # how a bug that silently dropped the end of such a range went unnoticed:
    # it produced an 863 for the start alone, so the 866 was removed as
    # converted and the rest of the holdings went with it.
    ("Journal of Spaced Separators", [
        "v. 1 (2001) - v. 5 (2005)",
        "v. 7 (2007) - v. 9 (2009)",
    ], None),

    ("Index of Absent Holdings", [], None),
]


def make_record(n, title, holdings, existing_853):
    rec = Record()
    # Leader/06 y, Leader/18 n, and both were wrong until 0.12.5.
    #
    # docs/marc/hdleader.md:
    #   /06  y - Serial item holdings   (was x - Single-part item holdings)
    #   /17  3 - Holdings level 3: "summary holdings information, that is,
    #            holdings at the first level of enumeration and chronology"
    #   /18  n - No item information   (was a blank, which is not a value /18
    #            defines; the choices are i and n, and these records carry no
    #            876-878 Item Information fields)
    #
    # /06 is the one that mattered. These are serials with volumes and issues,
    # coded as single-part items -- and 863-865 says first indicator 3 "is not
    # applicable to a single-part item (Leader/06, code x)", so the fixtures
    # were quietly ruling out a value the standard allows for what they hold.
    # Nothing in the toolkit reads the Leader yet; the first change that does
    # would have been calibrated against records describing the wrong kind of
    # thing.
    #
    # /17 stays 3 and is right for these records: what they carry is 866
    # summary statements. Whether conversion into detailed 853/863 ought to
    # raise the record to level 4 is a real question and a separate one -- see
    # CORPUS-FINDINGS.
    rec.leader = "00522cy  a22001453n 4500"
    rec.add_field(Field(tag="001", data=f"messy{n:04d}"))
    rec.add_field(Field(tag="008", data="1011252u    8  4001uueng0000000"))
    rec.add_field(Field(tag="245", indicators=["0", "0"],
                        subfields=[Subfield(code="a", value=title + ".")]))
    rec.add_field(Field(tag="852", indicators=["8", " "], subfields=[
        Subfield(code="b", value="EXL"),
        Subfield(code="c", value="messy-lib"),
        Subfield(code="h", value="Journals"),
    ]))
    if existing_853:
        rec.add_field(Field(tag="853", indicators=["2", "0"], subfields=[
            Subfield(code=code, value=value) for code, value in existing_853
        ]))
    for text in holdings:
        rec.add_field(Field(tag="866", indicators=[" ", "0"],
                            subfields=[Subfield(code="a", value=text)]))
    return rec


def main():
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "wb") as fh:
        for i, (title, holdings, existing) in enumerate(EXAMPLES, start=1):
            fh.write(make_record(i, title, holdings, existing).as_marc())
    print(f"Wrote {len(EXAMPLES)} synthetic records to {os.path.relpath(OUTPUT)}")


if __name__ == "__main__":
    main()
