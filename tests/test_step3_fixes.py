"""
With a file, statements are put right on their records in step 3, not on a card.

Asked for by the cataloguer on 0.48.0: the real export showed "17 patterns with
statements to look at" in step 2, each listing its statements with Edit and
Split -- and putting one right needs the rest of its record in view, which a
card does not show. Of the 28 statements listed, 27 came out the same whatever
was decided on any card: 13 changing between months and seasons, 8 with
wording MARC has no code for, 4 with a range inside one end, 2 issues dated
across two years. One was not read at all, for a typo, on the card asking for
an answer.

So with a file: a card lists only what is not read; says how many are held or
to check, with a way to them in step 3; Edit and Split anywhere in step 2 open
the record in step 3 with the editor open on that 866; statements and messages
name the record by its identifier as well as its title; and step 3's Edit
offers what step 2's did, the same change on every record with exactly that
866. Pasted statements have no step 3, and keep everything on the card.
"""

from __future__ import annotations

import re

from conftest import page_source

PAGE = page_source()


def _function(name):
    match = re.search(rf"(?:async )?function {name}\(.*?\n\}}\n", PAGE, re.S)
    assert match, f"{name}() has moved or been renamed"
    return match.group(0)


def test_edit_and_split_in_step_2_open_the_record_in_step_3():
    go = _function("editInStep3")
    # Narrowed to the card's records to look at, and waited on, so the record
    # is on the page before it is opened.
    assert "narrowToPattern(card, 'look');\n    await applyFilter('one-pattern');" in go
    assert "await loadReviewPage();" in go and "await selectRecord(idx);" in go
    assert "openSplit866(idx, fi);" in go and "openEdit866(idx, fi);" in go
    # From the card's list, its example, and its record preview.
    assert "editInStep3(src.record_index, src.field_index, kind, row.closest('.pattern-card'));" \
        in _function("lookAction")
    held = _function("heldAction")
    assert "if (card) { editInStep3(idx, fi, kind, card); return; }" in held
    for name, kind in (("openCardEdit", "edit"), ("openCardSplit", "split")):
        assert f"if (sourceMode !== 'paste') {{ cardInStep3(card, '{kind}'); return; }}" \
            in _function(name)


def test_pasted_statements_are_still_put_right_on_the_card():
    look = _function("lookAction")
    assert "if (kind === 'split') openInlineSplit(slot, { pasted: true }, r.text);" in look
    assert "openInlineEdit(slot, t.target, t.text, { where: t.where });" in _function("openCardEdit")


def test_a_card_counts_what_is_put_right_in_step_3_and_goes_there():
    line = _function("lookStep3Html")
    assert "if (sourceMode === 'paste' || lookFilter !== 'all') return '';" in line
    assert 'class="btn btn-secondary btn-sm pc-show-records"\n            data-mode="look"' in line
    # And what keeps a card in the open group is a statement not read.
    assert ": (group.unread || 0) > 0);" in _function("needsALook")


def test_the_step_says_where_the_rest_are():
    summary = _function("step3LookHtml")
    assert "showInStep3('held')" in summary and "showInStep3('leftout')" in summary
    assert "await applyFilter(name);" in _function("showInStep3")


def test_a_record_is_named_by_its_identifier_and_title():
    name = _function("recordName")
    assert '<span class="rec-id">${escHtml(rec.identifier)}</span> ' in name
    assert "on ${recordName(src.record_index)}" in _function("lookRowHtml")
    assert "const on = `on ${recordName(record_index)}`;" in _function("recordOutcome")


def test_step_3_edit_offers_the_same_change_on_the_other_records():
    opener = _function("openEdit866")
    assert "Also make this change on the" in opener
    assert "g.split_part == null && (g.a || '').trim() === statement" in opener
    save = _function("saveEdit866")
    assert "same_text: !!(box && box.checked && code === 'a') });" in save
    assert "also: (data.also || []).length" in save
