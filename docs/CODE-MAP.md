# Code map

*Where everything is, and what happens when you press a button. Describes version 0.49.0.
For what the Workbench does and why, see [How the Holdings Workbench works](HOW-IT-WORKS.md).*

The Workbench has two halves that never touch directly:

- **The engine** (Python, in `marc_serials/`) reads 866s, finds patterns and writes 853s and 863s. It knows nothing about the screen.
- **The page** (in `marc_serials/templates/` and `marc_serials/static/`) is everything you see and click. It runs in your browser and knows nothing about MARC beyond what the engine tells it.

They talk only through requests. A button on the page sends a request (`api/detect`, `api/edit-866`, …), `webapp.py` receives it, asks the engine, and sends back the answer, which the page then draws. Everything runs on your own computer.

## The engine

| File | Its job |
| --- | --- |
| `parser.py` | Reads one 866 `$a`: which numbers are volumes and issues, which are years, months, seasons and days. Its answer is a "reading" of the statement. Also decides what a coded subfield can hold. |
| `converter.py` | Turns a reading into an 853 and its 863s, with indicators, `$8` links and every warning you see on a record ("To check:", "Left out to fit MARC:"). `convert_record` does a whole record at once, so statements can share an 853. |
| `detector.py` | Groups many statements by shape and writes each group's expression: the pattern cards. |
| `bridge.py` | Lets a confirmed pattern tell the parser what a value means. For each 866 it tries your confirmed patterns first, largest first, and hands the statement to the parser if none matches. |
| `library.py` | The pattern library: what a confirmed pattern holds, and checking one when it is loaded or imported. |
| `budget.py` | Runs an expression with a time limit, so a pattern that would never finish is refused before it is stored. |
| `records.py` | The MARC file itself: reading it, your 866 edits and splits, putting the new 853/863s on a record, removing converted 866s, and writing the file back out. |
| `display.py` | Writes the 866 Alma would generate from an 853/863, for the round-trip check. |
| `flavours.py` | Rewrites an expression for another tool: JavaScript, MarcEdit, Alma, Oracle and the rest. |
| `store.py` | Where your session's files live: the upload, your decisions and your library, in a temporary folder, removed after six hours (the library after 30 days unused). |
| `webapp.py` | The server. Each request the page sends arrives at a route here (`@app.route("/api/…")`), which calls the files above and sends the answer back. It also keeps your decisions: edits, skips, notes and each record's 853. |

## The page

`templates/tool.html` is the page's layout: the three steps, the settings, the filter chips, the About box. It also holds the few values the server writes into the page (the caption conventions, the choices for what a value is), and then loads the rest in this order:

| File | What it does |
| --- | --- |
| `static/workbench.css` | How the page looks: the pills, the cards, the orange, yellow and dashed boxes. Colours, buttons and dark mode that all pages share are in `shared/ui.css`. |
| `static/js/core.js` | What every part shares: the page's state, and small helpers for escaping text, showing an alert and sending a request. |
| `static/js/settings.js` | Conversion settings: caption convention, 853 indicators and subfields, frequency, issues per volume, strict, and the left-out choice. |
| `static/js/holdings.js` | Step 1: uploading the file, which steps show, and the field records are identified by. |
| `static/js/records.js` | The record list in step 3: each record's line and pills, the notes above the list, the filter chips, Find, and the pages. |
| `static/js/expressions.js` | A pattern's expression: Copy, "Write expressions for", and "Show the records" from a card. Also the pagers and the pasted statements. |
| `static/js/patterns.js` | Step 2: Find patterns, confirming what reads on its own, the folds and counts, and building each card. |
| `static/js/editors.js` | Edit and Split on step 2, the message saying whether a fix worked, and where the keyboard goes when an editor closes. |
| `static/js/cards.js` | Inside a pattern card: statements to look at, the table of what each value means, and the preview of what it would write. |
| `static/js/library.js` | The pattern library on screen: confirm, skip, remove, clear, import and export. |
| `static/js/convert.js` | Step 3: an open record, its 866s with Edit and Split, its 853, its note, and Convert all records. |
| `static/js/page.js` | Text size, dark theme and the About box. Loads your library when the page opens. |

The order matters only while the page is loading: a file can use what an earlier file sets up. Once the page is running, any file can call any other.

## What happens when you…

**Upload a file.** `holdings.js` sends it to `api/upload-marc`. `webapp.py` has `records.py` read it, stores it with `store.py`, and starts your decisions afresh. The record list (`records.js`) then asks `api/review-index` and `api/preview-records` how each record converts, for its line and pills.

**Press Find patterns.** `patterns.js` sends every statement to `api/detect`. `webapp.py`:

1. reads the records, with your edits applied (`records.py`);
2. divides statements the way the cards show them (`bridge.split_statement`);
3. groups them by shape (`detector.detect_patterns`);
4. reads each statement on its own to count what is held, to check, not read or left out (`parser.py`, `converter.py`).

Back on the page, every pattern that needs no decision is confirmed for you. That is `library.js` sending the library to `api/patterns`, where `budget.py` checks each new expression finishes. Then the cards are drawn (`patterns.js`, `cards.js`).

**Edit or Split an 866.** With a file, Edit and Split in step 2 open the record in step 3 with the editor on that 866 (`editInStep3` in `convert.js`). The editor sends the change to `api/edit-866` or `api/split-866`. With pasted statements, `editors.js` edits the line on the card. `webapp.py` keeps it with your decisions: the uploaded file itself is never changed, and the edit is applied each time the records are read. The page then re-reads the record list, finds patterns again, and asks `api/preview-record` how that 866 now converts, for the message at the bottom right.

**Confirm a pattern.** `library.js` sends the whole library to `api/patterns`. From then on `bridge.py` tries that pattern on every statement, before the parser.

**Press Convert all records.** `convert.js` sends `api/batch-convert`. For each record not skipped, `webapp.py`:

1. reads each 866 with your patterns or the parser (`bridge.apply_patterns`, `parser.parse_866`);
2. builds the record's 853s and 863s (`converter.convert_record`);
3. puts them on the record and removes converted 866s if you chose to (`records.py`);
4. writes the new file.

**Download.** **Download .mrc** asks `api/download-converted` for that file. **Download log** asks `api/download-log`, which converts again and writes one spreadsheet line for everything there is to say about each record.

## When a statement converts wrongly, where to look

| What you see | Where the cause usually is |
| --- | --- |
| A number or date read as the wrong thing, or not read at all | `parser.py` |
| Read right, but the wrong subfield, indicator, `$8` or warning | `converter.py` |
| Fine through the parser, wrong through a pattern | `bridge.py`, and the pattern itself: open its card and use Test expression. "Which pattern read what", in the summary after Convert all records, says what read each statement. |
| Wrong only after a round trip through Alma | `display.py` |
| The fields are right but the screen shows them wrong | the page file for that part, in the table above |
| A record changed that you didn't touch | `records.py` (edits, removing 866s) and your decisions in `webapp.py` |

To check a fix doesn't break something else, the project runs the same three checks on every change:
- `scripts/corpus_report.py` (real statements, before and after)
- `scripts/audit_conversion.py` (nothing dropped without a word)
- `scripts/round_trip.py` (the same 863s back after Alma's 866)

Many tests in `tests/` are named after a mistake the tool once made. Searching them for a statement's shape often finds the rule that governs it. [CORPUS-FINDINGS](../CORPUS-FINDINGS.md) says why each rule exists.

## Everything else

| Where | What |
| --- | --- |
| `shared/about.json` | The version and the changelog, written for cataloguers. `scripts/build_changelog.py` makes `CHANGELOG.md` from it. |
| `data/` | Made-up MARC files for the tests, and three collections of 866 text (the main corpus, LC's examples, other libraries' catalogues) |
| `docs/marc/` | The LC holdings pages the converter is written against, kept for quoting |
| `tests/` | The automated tests. `python -m pytest` runs them all in under a minute. |
| `scripts/` | The checks above, and the scripts that made the sample files |
