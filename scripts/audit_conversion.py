#!/usr/bin/env python3
"""
What went into a conversion, and what came out of it.

    python scripts/audit_conversion.py your_file.mrc
    python scripts/audit_conversion.py data/textual_holdings_corpus.txt --detail

Rule 4 says a value is encoded, deliberately dropped with a reason, or held
for review, and never a fourth thing.  This script looks for the fourth thing:
a number that was in an 866 statement, is in none of the fields written from
it, and is named in no warning about it.  Nothing else in the project asks that
question from the outside -- the corpus report asks it of 117 statements whose
answers are already written down, which is a different and narrower thing.

It was written after one turned up.  "(1986-1988, 1993-1994)" converted to a
single 863 reading "$i 1986" and dropped 1988, 1993 and 1994 without a word:
one statement in the 1057 of a real file, found only because a throwaway script
compared the years going in against the years coming out.  This is that script,
made to be run again.

    Nothing is written.  The file is read where it lies and no copy is made,
    which matters because the files worth running this against are real
    library holdings and belong nowhere near this repository.

Exit status is 1 when anything is unaccounted for, so it can gate a release the
way the drift check does.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marc_serials.converter import convert_holdings          # noqa: E402
from marc_serials.parser import (                            # noqa: E402
    _expand_abbreviated_end_year as expand_end_year,
    parse_866,
)

# A number worth tracking: a year, or an enumeration value. Bounded at four
# digits because five-digit runs are record identifiers rather than holdings,
# and a bare 0 is never a volume.
NUMBER_RE = re.compile(r"\d{1,4}")

# "1986-1988" in a written subfield covers every year between its ends, so a
# statement naming 1987 inside that span is accounted for.
SPAN_RE = re.compile(r"(\d{1,4})\s*[-/]\s*(\d{1,4})")

# $8 is the link between an 853 and its 863s -- "1.1", "1.2" -- and its digits
# are the tool's own bookkeeping. Counting them as output would let an 863
# linked "1.12" account for an input volume 12 that was never written.
BOOKKEEPING_SUBFIELDS = {"8"}


def written_values(conversion) -> str:
    """Everything the conversion actually wrote, minus its own bookkeeping.

    Only the 863s: the 853 holds captions, and a value landing there instead of
    in an 863 is itself a defect rather than an accounting.
    """
    return " ".join(
        sf.value
        for field in (conversion.fields_863 or [])
        for sf in field.subfields
        if sf.code not in BOOKKEEPING_SUBFIELDS
    )


def accounted_for(number: str, written: str, said: str) -> bool:
    """Whether this number reached a field or a sentence about the statement."""
    if re.search(rf"(?<!\d){re.escape(number)}(?!\d)", written):
        return True
    if number in said:
        return True
    value = int(number)
    for span in SPAN_RE.finditer(written):
        low, high = int(span.group(1)), int(span.group(2))
        if low <= value <= high:
            return True
    return False


# "1996/97" means 1996 and 1997, and the converter writes it out in full as
# "1996/1997" because MARC wants four digits. Comparing the raw text against
# the written fields would report the "97" as lost every time -- three of the
# 117 corpus statements, all of them correct. The statement is expanded the
# same way before its numbers are read, so like is compared with like.
ABBREVIATED_SPAN_RE = re.compile(r"\b(\d{4})\s*/\s*(\d{2})\b")


def expand_abbreviated_years(text: str) -> str:
    """Write the statement's years the way the converter writes them.

    Two abbreviations, both of which the converter expands: "1996/97" for one
    year and the next, and "1960-66" for a span. The hyphen form is expanded by
    borrowing the parser's own function rather than by keeping a second copy of
    the rule here -- a copy would be free to drift, and an audit that disagrees
    with the thing it audits is worse than no audit. The first version of this
    script did exactly that and reported nine correct conversions as losses.
    """
    def expand(match: "re.Match") -> str:
        first, short = match.group(1), match.group(2)
        candidate = int(first) // 100 * 100 + int(short)
        if candidate < int(first):
            candidate += 100          # "1999/00" is 1999 and 2000
        return f"{first}/{candidate}"
    return expand_end_year(ABBREVIATED_SPAN_RE.sub(expand, text))


def audit(statement: str) -> dict:
    """One statement: what it says, what was written, what went missing."""
    result = parse_866(statement)
    conversion = convert_holdings(result)
    written = written_values(conversion)
    said = " ".join(list(conversion.warnings or []) + list(result.warnings or []))

    produced = bool(conversion.fields_863)
    missing = sorted({
        n for n in NUMBER_RE.findall(expand_abbreviated_years(statement))
        if n.lstrip("0") and not accounted_for(n, written, said)
    }, key=int)

    return {
        "statement": statement,
        "produced": produced,
        "written": written,
        "missing": missing,
        "warned": bool(said),
    }


def statements_from(path: Path) -> list[tuple[str, str]]:
    """(where, statement) pairs from a MARC file or a corpus text file."""
    if path.suffix.lower() in (".mrc", ".marc", ".dat"):
        try:
            from pymarc import MARCReader
        except ImportError:                                   # pragma: no cover
            sys.exit("pymarc is needed to read a MARC file.")
        out = []
        with path.open("rb") as handle:
            for index, record in enumerate(MARCReader(handle)):
                if record is None:
                    continue
                where = record["001"].data if record["001"] else f"record {index + 1}"
                for field in record.get_fields("866"):
                    text = (field["a"] or "").strip()
                    if text:
                        out.append((where, text))
        return out

    # A corpus text file: one statement a line, "#" starting a comment. The
    # same convention corpus_report.py reads, and safe for the same reason --
    # no statement in it contains a "#".
    out = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("[section:"):
            continue
        statement = line.partition("#")[0].strip()
        if statement:
            out.append((f"line {lineno}", statement))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare what went into a conversion against what came out.")
    parser.add_argument("path", type=Path,
                        help="a .mrc file, or a corpus text file of statements")
    parser.add_argument("--detail", action="store_true",
                        help="list every statement with something unaccounted for")
    args = parser.parse_args()

    if not args.path.exists():
        sys.exit(f"No such file: {args.path}")

    pairs = statements_from(args.path)
    if not pairs:
        sys.exit(f"No 866 statements found in {args.path}")

    silent, refused, warned_losses = [], 0, 0
    for where, statement in pairs:
        found = audit(statement)
        if not found["produced"]:
            # Nothing was written, and the screen says so. Visible, not silent.
            refused += 1
            continue
        if found["missing"]:
            if found["warned"]:
                # Something was said about this statement. Worth seeing, but it
                # is not the defect this script exists for.
                warned_losses += 1
            else:
                silent.append((where, found))

    print("=" * 78)
    print("Conversion audit")
    print("=" * 78)
    print(f"file                {args.path}")
    print(f"866 statements      {len(pairs)}")
    print(f"produced no fields  {refused}   (visible: the screen shows nothing written)")
    print(f"missing but warned  {warned_losses}   (accounted for: a warning names it)")
    print()
    print(f"UNACCOUNTED FOR     {len(silent)}"
          f"   <- in the statement, in no field, in no warning")
    print()

    if silent and args.detail:
        print("-" * 78)
        for where, found in silent:
            print(f"  {where}")
            print(f"     866      {found['statement']}")
            print(f"     written  {found['written'] or '(nothing)'}")
            print(f"     missing  {', '.join(found['missing'])}")
            print()
    elif silent:
        print("Re-run with --detail to see them.")
        print()

    if silent:
        print("Rule 4: encoded, deliberately dropped with a reason, or held for")
        print("review -- and never a fourth thing. These are the fourth thing.")
        return 1

    print("Nothing went missing without being accounted for.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
