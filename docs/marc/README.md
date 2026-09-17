# MARC 21 holdings documentation, as consulted

Reference copies of the Library of Congress documentation this converter is
written against. None of it is this project's work.

| File | Covers | LC page |
|---|---|---|
| [hd853855.md](hd853855.md) | Captions and Pattern — the 853 this tool generates | <https://www.loc.gov/marc/holdings/hd853855.html> |
| [hd863865.md](hd863865.md) | Enumeration and Chronology — the 863 this tool generates | <https://www.loc.gov/marc/holdings/hd863865.html> |
| [hd866868.md](hd866868.md) | Textual Holdings — the 866 this tool reads | <https://www.loc.gov/marc/holdings/hd866868.html> |
| [hd853878.md](hd853878.md) | How the four kinds of holdings field relate, and compressibility | <https://www.loc.gov/marc/holdings/hd853878.html> |
| [hdleader.md](hdleader.md) | The Leader, including Leader/06 and Leader/17 | <https://www.loc.gov/marc/holdings/hdleader.html> |

Refresh one with the script that made them:

```bash
python scripts/extract_marc_doc.py <downloaded.pdf> hdleader "Leader" \
    https://www.loc.gov/marc/holdings/hdleader.html "MARC 21 Holdings April 2022"
```

## Why they are in the repository

Because a decision that cites the standard is worth more than one that recalls
it, and recollection was demonstrably not good enough. Reading 853-855 properly
found `$v` on the first level of enumeration in eighteen of the 117 corpus
statements — a rule the code had never been checked against. Reading 863-865
found the second indicator claiming a compressed range on fields holding a
single part. Both were invisible to every test the project had.

They also settled three questions that had been argued from memory, one of
which had been answered wrongly in this project's own notes. `CORPUS-FINDINGS.md`
now quotes these files, so the reasoning behind an output can be followed to its
source without a network connection or a fresh download.

## What they are not

Not a substitute for the LC pages, which are authoritative and revised. Not
complete: the format has many sections and only the three the converter touches
are here. Not edited — see each file's header.

Worth having eventually, in rough order of usefulness to this project:

- **Appendix B: Full Level Record Examples** (`examples.html`) — whole records
  to check output shape against, rather than fields in isolation. The obvious
  next one: reading the Leader found the two `.mrc` fixtures in `data/` coded
  as single-part items while carrying serial holdings, which whole-record
  examples would have made obvious sooner.
- **Appendix E: Glossary** (`hdapndxe.html`) — would pin down "part", "unit"
  and "itemized", which this project's notes use loosely.
- **876-878: Item Information** (`hd876878.html`) — only if piece-level
  holdings ever come into scope. Nothing needs it today.

## Licensing

Works of the US federal government. Their presence here does not change this
repository's own position, which is [NOTICE.md](../../NOTICE.md): no license
granted while institutional IP ownership is under review.
