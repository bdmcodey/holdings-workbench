#!/usr/bin/env python3
"""
Can the 863 first indicator be worked out from the field?

The first indicator of an 863 is Field encoding level: 3 for a summary
statement, 4 for a detailed one, matching Leader/17.  A converter would much
rather derive it than ask for it, and Z39.71 4.3 looks like it gives a rule --
level 3 includes "only the highest levels (first-order designators)", level 4
"the most specific levels (including all hierarchical levels)".

This script asks whether that rule, or any rule reading only the field, can
reproduce what the MARC documentation actually does.  It reads every 863, 864
and 865 example in docs/marc/, groups them by which enumeration and chronology
subfields they carry, and reports where one shape carries both values.

It does not score a candidate rule against the examples, because the answer
turned out not to need one: where a single shape appears with both indicators,
no function of the field's content can return both, so no such rule exists.

    python scripts/measure_863_indicator.py

Findings are recorded in CORPUS-FINDINGS.md under "The 863 first indicator is
a declaration, not a derivation".  Re-run this after adding a document to
docs/marc/ -- if the ambiguity ever disappears, the setting it justifies
should be revisited.
"""
from __future__ import annotations

import collections
import glob
import os
import re
import sys

# "863 30$81.1$a113-123$i1923-1928" -- the documents run the indicators
# straight into the first subfield, with no space.
FIELD = re.compile(r"(86[345])\s+([0-9#\\ ])([0-9#\\ ])(\$[^\s]*)")
SUBFIELD = re.compile(r"\$([a-z0-9])([^$]*)")

# Enumeration runs $a-$f, most significant first; chronology $i-$l.
ENUM = "abcdef"
CHRON = "ijkl"

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "docs", "marc")


def examples():
    """Every 863/864/865 example carrying a first indicator of 3 or 4."""
    for path in sorted(glob.glob(os.path.join(DOCS, "*.md"))):
        doc = os.path.basename(path)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for match in FIELD.finditer(text):
            tag, ind1, ind2, body = match.groups()
            if ind1 not in "34":
                continue
            codes = [code for code, _ in SUBFIELD.findall(body)]
            shape = tuple(c for c in codes if c in ENUM + CHRON)
            yield {
                "doc": doc,
                "tag": tag,
                "ind1": ind1,
                "shape": shape,
                "raw": f"{tag} {ind1}{ind2}{body}",
            }


def show(shape) -> str:
    return " ".join("$" + code for code in shape) or "(no enumeration or chronology)"


def main() -> int:
    fields = list(examples())
    if not fields:
        print(f"No 863/864/865 examples found under {DOCS}.", file=sys.stderr)
        return 1

    by_shape = collections.defaultdict(list)
    for field in fields:
        by_shape[field["shape"]].append(field)

    both = {shape: rows for shape, rows in by_shape.items()
            if len({r["ind1"] for r in rows}) > 1}
    covered = sum(len(rows) for rows in both.values())
    marked = collections.Counter(f["ind1"] for f in fields)

    print("=" * 78)
    print("863 first indicator: what the documentation does")
    print("=" * 78)
    print(f"documents            {len(set(f['doc'] for f in fields))} under docs/marc/")
    print(f"examples             {len(fields)} with a first indicator of 3 or 4")
    print(f"  marked 3           {marked['3']}")
    print(f"  marked 4           {marked['4']}")
    print()
    print(f"distinct shapes      {len(by_shape)}")
    print(f"shapes carrying both 3 and 4   {len(both)}")
    print(f"examples under such a shape    {covered}"
          f"  ({covered * 100 // len(fields)}% of all of them)")
    print()

    print("-" * 78)
    print("Shapes the documentation marks both ways")
    print("-" * 78)
    for shape, rows in sorted(both.items(), key=lambda kv: -len(kv[1])):
        counts = collections.Counter(r["ind1"] for r in rows)
        print(f"\n  {show(shape)}   {len(rows)} examples"
              f"   -- 3: {counts['3']}, 4: {counts['4']}")
        for want in "34":
            example = next((r for r in rows if r["ind1"] == want), None)
            if example:
                print(f"      {want}:  {example['raw']:<46} ({example['doc']})")

    print()
    print("-" * 78)
    print("Shapes the documentation is consistent about")
    print("-" * 78)
    for shape, rows in sorted(by_shape.items(), key=lambda kv: -len(kv[1])):
        if shape in both:
            continue
        value = rows[0]["ind1"]
        print(f"  {show(shape):<38} {len(rows):>3} examples   always {value}")

    # The strongest single case: the same field, to the byte, marked both ways.
    identical = collections.defaultdict(set)
    where = collections.defaultdict(set)
    for field in fields:
        body = field["raw"].split(None, 1)[1][2:]     # past the tag and indicators
        identical[(field["tag"], body)].add(field["ind1"])
        where[(field["tag"], body)].add(field["doc"])
    pairs = {key: values for key, values in identical.items() if len(values) > 1}

    print()
    print("-" * 78)
    print("Fields identical but for the indicator")
    print("-" * 78)
    if not pairs:
        print("  none")
    for (tag, body), values in pairs.items():
        for value in sorted(values):
            docs = sorted(d for d in where[(tag, body)])
            print(f"  {tag} {value}0{body}")
        print(f"      in {', '.join(sorted(where[(tag, body)]))}")

    print()
    print("-" * 78)
    if both:
        print("A shape marked both ways has no single right answer to derive.")
        print("The indicator is a declaration of institutional practice, and the")
        print("tool asks for it: see CORPUS-FINDINGS.md and converter.HOLDINGS_LEVELS.")
    else:
        print("No shape is marked both ways. The case for asking rather than")
        print("deriving rests on the examples -- re-read CORPUS-FINDINGS.md.")
    print("-" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
