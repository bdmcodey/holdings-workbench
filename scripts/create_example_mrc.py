"""
Generate a small, fully synthetic example .mrc file for demos and tests.

All titles, identifiers, and location codes below are invented — there is no
real institutional data here. The 866 holdings strings are format examples
chosen to exercise the parser's supported patterns.

Run:
    python scripts/create_example_mrc.py
    # -> writes data/example_holdings.mrc
"""

import os
from pymarc import Record, Field, Subfield

OUTPUT = os.path.join(os.path.dirname(__file__), "..", "data", "example_holdings.mrc")

# (title, [866 $a holdings statements]) — invented titles, example holdings
EXAMPLES = [
    ("Journal of Imaginary Studies", [
        "v.1:no.1(1990:Jan.)-v.5:no.4(1994:Dec.)",
        "v.6(1995)-",
    ]),
    ("Annals of Fictional Research", [
        "v. 1-14 (1953-1966)",
    ]),
    ("Review of Made-Up Sciences", [
        "v. 8 no. 3-v. 10 no. 2 (1981-Fall 1983)",
        "v. 27 no. 4-v. 31 no. 4 (April 1992-April 1996)",
    ]),
    ("Quarterly of Nonexistent Topics", [
        "34 no 3, 4 (Summer, Autumn 1990)",
        "39 no 1 (Spring 1995)",
        # One statement the parser refuses, on purpose. The rule that matters
        # most in the Converter is that a statement it cannot read keeps its
        # 866 -- the field is removed once anything has been written from it --
        # and a corpus where everything converts leaves that rule untested.
        # A designation between the enumeration and the chronology is the
        # simplest shape that is still beyond the parser (D3's remainder).
        "v. 58 Suppl. (Sep 2003)",
    ]),
    ("Bulletin of Placeholder Serials", [
        "v.1(1990)-v.10(1999)",
        "v.12(2001)-v.15(2004)",
    ]),
]


def make_record(n, title, holdings):
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
    rec.add_field(Field(tag="001", data=f"exmpl{n:04d}"))
    rec.add_field(Field(tag="008", data="1011252u    8  4001uueng0000000"))
    rec.add_field(Field(tag="245", indicators=["0", "0"],
                        subfields=[Subfield(code="a", value=title + ".")]))
    rec.add_field(Field(tag="852", indicators=["8", " "], subfields=[
        Subfield(code="b", value="EXL"),
        Subfield(code="c", value="example-lib"),
        Subfield(code="h", value="Journals"),
    ]))
    for text in holdings:
        rec.add_field(Field(tag="866", indicators=[" ", "0"],
                            subfields=[Subfield(code="a", value=text)]))
    return rec


def main():
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "wb") as fh:
        for i, (title, holdings) in enumerate(EXAMPLES, start=1):
            fh.write(make_record(i, title, holdings).as_marc())
    print(f"Wrote {len(EXAMPLES)} synthetic records to {os.path.relpath(OUTPUT)}")


if __name__ == "__main__":
    main()
