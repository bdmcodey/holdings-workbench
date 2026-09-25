#!/usr/bin/env python3
"""
Round the loop with an ILS: convert, regenerate the 866, convert again.

    python scripts/round_trip.py data/textual_holdings_corpus.txt
    python scripts/round_trip.py your_export.mrc --detail

The loop this checks is the one the tool lives in. Holdings leave the ILS,
are converted here and go back; the ILS regenerates each 866 from the new
853/863s. If those 866s came out again and were converted a second time, they
should give the same 863s. A difference is drift, and drift is a bug on one
side or the other -- in how the 866 was read, or in how the ILS's 866 is
imitated by marc_serials.display.

For a .mrc export that already holds ILS-generated 866s -- ones linked by $8
to the 863 they came from -- it also checks the imitation against the real
thing: every such 866 is regenerated here and compared. A mismatch there says
display.py writes something the ILS does not, which is how to calibrate it
against forms the first sample did not show (seasons, days, chronology-only
ranges with months).

Nothing is written. Exit status is 1 when any 863 drifts or any generated 866
differs from the ILS's own.
"""

from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_conversion import statements_from                    # noqa: E402
from marc_serials.display import (CAPTION_ONLY, DRIFT, NOT_CONVERTED,  # noqa: E402
                                  SAME, render_866, round_trip)


def ils_mismatches(path: Path) -> tuple[int, list]:
    """Compare every $8-linked 866 in an export with what display.py writes."""
    if path.suffix.lower() not in (".mrc", ".marc", ".dat"):
        return 0, []
    from pymarc import MARCReader
    checked, differ = 0, []
    with path.open("rb") as handle:
        for record in MARCReader(handle):
            if record is None:
                continue
            f863 = {f.get("8"): f for f in record.get_fields("863") if f.get("8")}
            f853 = {f.get("8"): f for f in record.get_fields("853") if f.get("8")}
            for field in record.get_fields("866"):
                link = field.get("8")
                if not link or link not in f863:
                    continue
                checked += 1
                ours = render_866(f853.get(link.split(".")[0]), f863[link])
                if ours != field.get("a"):
                    differ.append((field.get("a"), ours, str(f863[link])))
    return checked, differ


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("path", type=Path,
                    help="a .mrc file, or a corpus text file of statements")
    ap.add_argument("--detail", action="store_true",
                    help="list every statement that drifts")
    args = ap.parse_args()
    if not args.path.exists():
        sys.exit(f"No such file: {args.path}")

    statements = sorted({text for _, text in statements_from(args.path)})
    counts = collections.Counter()
    drift = []
    for statement in statements:
        trip = round_trip(statement)
        counts[trip["outcome"]] += 1
        if trip["outcome"] == DRIFT:
            drift.append((statement, trip))

    checked, differ = ils_mismatches(args.path)

    print("=" * 78)
    print("Round trip: convert, regenerate the 866 as the ILS would, convert again")
    print("=" * 78)
    print(f"file                {args.path}")
    print(f"distinct statements {len(statements)}")
    print(f"  the same both times            {counts[SAME]}")
    print(f"  the same 863s; the 853 loses a {counts[CAPTION_ONLY]}   "
          "(a level named with no value; the first pass says so)")
    print(f"  not converted the first time   {counts[NOT_CONVERTED]}")
    print(f"  DRIFT                          {counts[DRIFT]}")
    if checked:
        print()
        print(f"ILS-generated 866s in the file  {checked}")
        print(f"  written the same way here      {checked - len(differ)}")
        print(f"  DIFFERENT                      {len(differ)}")

    if args.detail or len(drift) <= 10:
        for statement, trip in drift:
            print()
            print(f"  {statement}")
            print(f"    regenerated : {trip['generated']}")
            print(f"    first 863s  : {trip['first'][1]}")
            print(f"    second 863s : {trip['second'][1]}")
    for alma, ours, f863 in differ[: None if args.detail else 10]:
        print()
        print(f"  ILS wrote : {alma}")
        print(f"  we write  : {ours}")
        print(f"  from      : {f863}")

    return 1 if drift or differ else 0


if __name__ == "__main__":
    raise SystemExit(main())
