#!/usr/bin/env python3
"""
Turn an LC holdings-format PDF into the reference Markdown under docs/marc/.

    python scripts/extract_marc_doc.py <pdf> <slug> "<title>" <url> "<edition>"

    python scripts/extract_marc_doc.py ~/hdleader.pdf hdleader \\
        "Leader" https://www.loc.gov/marc/holdings/hdleader.html \\
        "MARC 21 Holdings April 2022"

Exists because the documentation is consulted often enough to be worth carrying
in the repository, and because the conversion should be reproducible rather than
something somebody did once by hand. docs/marc/README.md says why the copies are
there at all.

The body is written inside a fenced block on purpose. The text uses "#" for the
blank indicator value and "$a" for subfield codes, and Markdown eats both --
which matters for a file whose whole value is being quotable.

Extraction is imperfect where the original used tables or two columns. The LC
page named in each header is the authority, not the copy; when LC revises a
page, re-run this rather than patching the Markdown.
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import sys

DOCS = pathlib.Path(__file__).resolve().parents[1] / "docs" / "marc"

HEADER = """# MARC 21 {title}

> **Reference copy.** Not written by this project. Text extracted verbatim from
> the Library of Congress documentation so that decisions about the converter
> can cite the standard rather than recollection of it.
>
> | | |
> |---|---|
> | Source | <{url}> |
> | Edition | {edition} |
> | Retrieved | {retrieved} |
> | Extracted with | `scripts/extract_marc_doc.py` (pypdf) |
> | Authority | Network Development and MARC Standards Office, Library of Congress |
>
> The body below is the extraction unedited, page markers included, inside a
> code fence. Fenced deliberately: the text uses `#` for the blank indicator
> value and `$a` for subfield codes, and Markdown would eat both. Nothing is
> reworded, reordered or summarised -- a paraphrase of a standard is no longer
> the standard, and this file exists to be quotable.
>
> Extraction is imperfect where the original used tables or two columns; where
> a passage looks garbled, the source URL above is the authority, not this
> file. If LC revises the page, re-run the script rather than patching this
> file, and update the edition and retrieval date.

```text
{body}
```
"""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("pdf", type=pathlib.Path)
    ap.add_argument("slug", help="file name without .md, e.g. hdleader")
    ap.add_argument("title", help='e.g. "Leader" or "853-855 - Captions and Pattern"')
    ap.add_argument("url", help="the LC page this came from")
    ap.add_argument("edition", help='the line LC prints, e.g. "MARC 21 Holdings June 2021"')
    ap.add_argument("--retrieved", default=None,
                    help="date the PDF was downloaded (default: today)")
    args = ap.parse_args(argv)

    try:
        import pypdf
    except ImportError:
        print("pypdf is needed: pip install -r requirements-dev.txt", file=sys.stderr)
        return 2

    if not args.pdf.is_file():
        print(f"no such file: {args.pdf}", file=sys.stderr)
        return 2

    reader = pypdf.PdfReader(str(args.pdf))
    body = "\n".join(f"\n===== PAGE {i} =====\n" + (page.extract_text() or "")
                     for i, page in enumerate(reader.pages, 1)).strip()

    retrieved = args.retrieved or datetime.date.today().strftime("%-d %B %Y")
    out = DOCS / f"{args.slug}.md"
    out.write_text(HEADER.format(title=args.title, url=args.url,
                                 edition=args.edition, retrieved=retrieved,
                                 body=body), encoding="utf-8")
    print(f"wrote {out.relative_to(DOCS.parents[1])} "
          f"({len(reader.pages)} pages, {len(body):,} characters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
