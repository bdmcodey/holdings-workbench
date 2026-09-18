# Working on this project

Conventions that the code already follows. They are written down because most of
them were arrived at by getting something wrong first, and the reasoning is
easier to keep than to rediscover.

The long-form record is [CORPUS-FINDINGS.md](CORPUS-FINDINGS.md): every defect
the real corpus exposed, what was decided about it, and why. Read that before
changing the parser or the converter.

## Running it

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt                 # the app, editable, plus pytest
python run.py                                       # or: marc-serials
```

Opens <http://localhost:5003>. Port 5003 rather than 5000 because macOS gives
5000 to AirPlay Receiver; `MARC_PORT` overrides it.

```bash
python -m pytest                          # the suite
python scripts/corpus_report.py           # what the real corpus converts to
python scripts/corpus_report.py --drift   # only outcomes that have changed
```

---

## 1. Measure before you change

Run the corpus and count what actually happens before writing a fix. More than
one defect in this project's history came from reasoning about what the code
probably did rather than checking.

The two worst regressions both had the same shape: a change was verified against
a handful of hand-picked cases that happened to share a property, and the cases
that lacked it broke silently. When you report what you did, give the numbers.

`scripts/corpus_report.py --drift` compares against the tags recorded in
`data/textual_holdings_corpus.txt`, so it tells you what your change moved
rather than what the totals are.

## 2. Nothing disappears silently

The invariant the whole tool rests on. Every value in a source statement must
end up in one of three states:

- **encoded** into an 853/863 subfield,
- **deliberately dropped**, with a warning that names the value and says why,
- **unaccounted for**, in which case the statement is held for review and
  nothing is written.

There is no fourth state. A statement the tool can only partly read is refused
outright rather than half-converted, because the original 866 is removed once
anything has been written from it — so converting half a statement deletes the
other half from the catalogue with nothing on screen to say so.

Two distinct outcomes, and they mean different things to a cataloguer:

- `needs_review` — nothing was written, the 866 survives.
- `flagged` — fields were written but the tool is not vouching for them.

If a change would let a value vanish without a warning, the change is wrong,
whatever else it improves.

## 3. One reader of holdings structure

`parse_866()` in `marc_serials/parser.py` is the only thing that reads a
statement into structure. A confirmed pattern supplies what the parser cannot
settle and nothing else:

- a **caption** for a level the statement writes as a bare number, where the
  parser can only write `(*)`;
- the **meaning of a value** nothing in the wording can type — `v.1(1990)-5(1994)`
  carries a `5` that no caption reaches, and no amount of parsing will fix that
  because the information is not in the statement.

This was measured rather than assumed. Across 141 statements the two readings
agreed on 90 and disagreed on 10 — and on 9 of those 10 the pattern was the one
that was wrong. Before that, a confirmed pattern built holdings out of its own
capture groups, and a large share of this project's bugs were the two paths
disagreeing about the same statement.

**Do not reintroduce a second path that builds holdings independently of the
parser.** `tests/test_invariants.py` asserts that both paths write the same 863.

## 4. One source of truth

`marc_serials/shared/about.json` holds the version and the changelog. The
application reads it for the version badge and the "What has changed" panel, so
it is the copy that stays current.

`CHANGELOG.md` is generated from it:

```bash
python scripts/build_changelog.py           # regenerate
python scripts/build_changelog.py --check   # fails if stale (the test runs this)
```

Two copies of one list drift. This project has fixed that class of bug
repeatedly — a dependency pin that diverged between three requirements files, a
data-loss fix applied to one copy of a function and not the other — so when you
find yourself writing the same fact twice, generate one from the other or pin
them together with a test.

## 5. Write the changelog for cataloguers

`about.json` says it in its own comment: *say what changed about the output or
the screen, not how the code changed.* The audience is cataloguing staff, not
developers.

Good: "A statement that is only a year spanning the turn of one — 1996/97 — now
converts instead of coming out empty."

Not: "Fixed `normalise_year()` in the year-only branch of `_parse_unit()`."

Where a change alters something a cataloguer may have been relying on, say so
plainly and say what to do about it.

## 6. Commit messages explain why

The diff says what changed. The message says what was measured, what was ruled
out, and what the change costs. Someone reading it in six months should be able
to tell whether the reasoning still holds.

Include the counts. "506 passed, 8 skipped, 1 xfailed; no corpus drift" is worth
the line.

## 7. If a fix needs the tests rewritten, stop

A change that requires rewriting tests which protect a considered design is
usually arguing with the design rather than fixing a bug.

This has a worked example. A tokeniser change once required four tests to be
rewritten, one of which carried a docstring explaining why its two captures were
deliberate — that was the signal the change was wrong. The redesign that
followed left every original test passing untouched.

Tests that merely describe a *mechanism* are fair to update when the mechanism
changes. Tests that describe an *outcome a cataloguer sees* are not.

## 8. Verify in the real application, not only in the suite

The Python suite cannot see a template that renders an error. One bug —
a function deleted while the line calling it stayed — broke every pasted
statement and no route test noticed, because the server was fine throughout.

When a change touches `marc_serials/templates/`, load the page and use it.
A refresh is enough: since 0.13.1 the app sets `TEMPLATES_AUTO_RELOAD`, so a
changed template is re-read rather than compiled once per process.

**A change to any `.py` file still needs the server restarted.** Only templates
reload. And the header's version badge cannot tell you whether you restarted:
`shared/about.json` is read per request, so it reports the version on disk, not
the version of the code answering you. If the screen and the badge disagree,
believe the screen.

---

## Tests

```
tests/test_parser.py          866 text → ParseResult
tests/test_converter.py       ParseResult → 853/863
tests/test_detector.py        clustering and regex generation
tests/test_bridge.py          confirmed patterns
tests/test_api_*.py           the HTTP routes
tests/test_invariants.py      properties that hold for any input, any corpus
tests/test_app_surface.py     the app's whole route list, and template hooks
tests/test_calibration.py     exact counts against private files; skips cleanly
```

A test marked `xfail` describes a known defect and says what the behaviour
should be, so fixing it turns the test green. Don't delete one to make the suite
quiet.

`tests/test_calibration.py` pins counts against real library holdings that are
deliberately not in this repository. It skips unless `MARC_TEST_DATA_DIR` points
at them. The skip is left visible rather than deselected: a SKIPPED line is
documentation, a silent deselection is a trap.

## Sample data

`.gitignore` excludes every `*.mrc` except the two synthetic fixtures in
`data/`, both generated by `scripts/`. **No library's real holdings may reach
this repository.** If you add a fixture, generate it.

## Python version

Developed against 3.10+. Be aware that warnings differ between versions — an
invalid escape sequence is a silent `DeprecationWarning` on 3.11 and a visible
`SyntaxWarning` on 3.12+. `tests/test_source_hygiene.py` fails on either, so the
suite catches it wherever it runs.

## Licensing

**There is no `LICENSE` file, and there must not be one yet.** Institutional
intellectual property ownership is under review. Do not add a license, state an
intended license, or write about licensing history. `NOTICE.md` says only that
the question is open.

`THIRD-PARTY-NOTICES.md` attributes the `MARC_CHRON_CODES` table, which derives
from `extract.py` by Phani Chaitanya Pendyala under MIT. That attribution is
required by that license, is unaffected by the review, and stays.
