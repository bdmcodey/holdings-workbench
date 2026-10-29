# Quick start for cataloguers

*One page, for a first try with the Workbench. Describes version 0.47.1.
[How the Holdings Workbench works](HOW-IT-WORKS.md) has the detail behind every step.*

The Workbench reads the free-text holdings in your 866s and writes 853 captions
and 863 enumeration and chronology from them. It runs on your own computer,
nothing leaves it, and it changes nothing in your catalogue: you get a new file
back, and you decide whether to load it.

## Before you start

- **Export the records** you want to work on from your ILS as a MARC file
  (`.mrc`), holdings records with their 866s. Keep the export as it is: the
  Workbench gives you a new file and never changes the one you upload.
- **Start the Workbench** (see the [README](../README.md#quick-start)) and open
  <http://localhost:5003>.
- **Allow for one sitting.** Your edits, skips and notes last until you upload
  another file, and the uploaded file is deleted from the computer about six
  hours after it was uploaded. Download the converted file and the log before
  you stop. Only the pattern library is kept longer (30 days unused), and
  Export keeps it for good.

## 1 · Holdings: upload the file

Drop the file on the box, or click it (or Tab to it and press Enter) and choose
it. Step 1 folds to one line naming the file, and steps 2 and 3 appear.

If you saved a pattern library last time, open **Pattern library** under step 1
and **Import** it now, before finding patterns.

To try a few statements without a file, paste them, one per line, under
"Or paste 866 statements" and press **Use these statements**. You'll see their
patterns, but there's nothing to convert or download.

## 2 · Patterns: find them, then answer what's asked

Press **⟳ Find patterns**. The 866s are grouped by shape, one card per shape,
for example every statement written like `v.1:no.1(1990:Jan.)-v.5:no.4(1994:Dec.)`.

- **Most cards need nothing from you.** A pattern whose every value already has
  a meaning is confirmed for you. If nothing needs deciding, the step folds
  away and you can go straight to step 3.
- **The cards that want an answer come first,** loose above the folded groups,
  each marked **needs a decision** in yellow until you confirm it. The line
  above them says how many ("1 still wants an answer"), and whether
  each one supplies a caption (a level written as a bare number, as in
  `39 no 1 (2018)`) or decides how a statement is read (nothing in the wording
  says what a value is, like the `5` in `v.1(1990)-5(1994)`). Press **Review**, say what each value is
  (enumeration, year, month or season), give a caption (`v.`, `no.`) where it
  has none, and press **Confirm pattern**. That answer converts every
  statement of that shape.
- **A card saying "not read" usually has a typo,** such as a comma missing
  between runs. **Edit** the statement rather than answering for it: written
  as meant, it reads like the others.
- **"Statements to look at"** on a card lists the ones that won't convert
  cleanly, each with the record it's on. Fix a typo with **Edit**. Where
  months change to seasons inside one statement, as in
  `v. 19 no. 3-v. 20 no. 4 (September 1986-Winter 1987)`, use **Split** to
  divide it where the change falls. A message at the bottom right says whether
  the fix worked.

When you're done, **Export** the pattern library, so next time starts with
these answers.

## 3 · Convert: check the settings, review, download

Open **Conversion settings** first. They apply to the whole file:

| Setting | Why look at it |
| --- | --- |
| Frequency (853 `$w`), Numbering (853 `$v`), Issues per volume (853 `$u`) | Frequency starts as "(not specified)". Set it here for the whole file, or per record under "This record's 853" |
| Holdings reported at (863 first indicator) | Detailed (4) or summary (3) |
| When something would be left out to fit MARC | Convert and mark it (the default), hold that one statement, or leave the record as uploaded |
| Clear existing 853 / 863 first | Off by default: a record that already has 863s is kept exactly as it is |

Then work through the records:

1. Choose the **Needs attention** filter. It gathers every record with
   something held, to check, or belonging in an 867 or 868.
2. Open each record. Its warnings say what to do: **Edit** or **Split** an
   866, set **This record's 853**, or tick **Skip** to leave the record exactly
   as uploaded and handle it yourself. Tick **Reviewed** when you're done with
   it, and **Close** it.
3. Look through **Something left out** too. Those records convert, and each
   says which value had no place in an 863.

Decide whether to tick **Remove each 866 once it has been converted**. It's
off by default, so the 866s stay beside the new fields.

Press **Convert all records**, then **Download .mrc** for the converted file
and **Download log** for a spreadsheet (it opens in Excel) of every record
with something to look at: held, skipped, kept, converted with a note or with
something left out, or edited by you. A record that converted cleanly has no
line.

## Before you load the file

- Open a few records in MarcEdit or your ILS and compare the 853/863s with the
  866s they came from, especially records from "Needs attention".
- Work through the log. Held statements were not converted: their 866s are
  still there, and the log says why each was held.
- Keep the log with the export. Together they record what changed.

## What the colours and labels mean

| On screen | Meaning |
| --- | --- |
| Green **100% matched** | The pattern's expression matches every statement in its group |
| Green **Confirmed** | The pattern is in your library, confirmed for you or by you, and will be used when you convert |
| Yellow **needs a decision** | The card is waiting on you: confirm it, or Skip it. It goes out when you do |
| Yellow **not read** | The standard parser can't read the statement at all, often because of a typo. Edit fixes it |
| Orange **held** | Nothing was written from it, because writing part of it would be wrong. The 866 stays |
| Orange **to check**, a box beginning "To check:" | It converted, with something you should look at before loading |
| Dashed **left out**, a dashed box beginning "Left out to fit MARC:" | It converted, but a value read correctly has no place in an 863 |
| A yellow note on a record | Recorded for the log. Nothing to decide |
| **belongs in 867** / **868** | A supplement or index. Held, for you to move by hand |

## Good to know

- **Nothing disappears silently.** Every value in an 866 is written into an
  863, named on the record, or the statement is held for you.
- **The same file and the same answers always give the same result.** It is
  not an AI model, and it calls nothing on the internet.
- **Everything works from the keyboard**: Tab, Enter or Space, and Escape to
  cancel an edit. Screen readers are told what each button acts on.
