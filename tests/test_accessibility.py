"""
The page used from a keyboard, and heard through a screen reader.

An audit against WCAG 2.1 AA before 0.46.0 found nothing for axe to object to
-- contrast, labels on the form fields, landmarks and the focus ring all
passed -- and seven things only using the page showed up: a file could not be
chosen from the keyboard at all; the three ticks under a record were heard as
one "Reviewed Keep patterns separate Skip" and two with no name; toggles did
not say whether they were open or pressed; focus fell to the top of the page
after Cancel, Close or Save; every Edit, Split, Copy and text-size button had
the same name as the next; nothing was said once Find patterns or a filter
had changed the page; and Escape did not leave an editor.

These read the page as served. What each fix does on screen was checked by
driving the page in Chromium; these keep them from being lost.
"""

from __future__ import annotations

import re

from conftest import REPO_ROOT


def _page() -> str:
    return (REPO_ROOT / "marc_serials" / "templates" / "tool.html").read_text(
        encoding="utf-8")


def _css() -> str:
    return (REPO_ROOT / "marc_serials" / "shared" / "ui.css").read_text(
        encoding="utf-8")


def test_a_file_can_be_chosen_from_the_keyboard():
    page = _page()
    zone = re.search(r'<div id="drop-zone"[^>]*>', page).group(0)
    assert 'role="button"' in zone and 'tabindex="0"' in zone and "aria-label=" in zone
    assert ("if (e.key === 'Enter' || e.key === ' ') "
            "{ e.preventDefault(); fileInput.click(); }") in page


def test_each_tick_under_a_record_has_a_name_of_its_own():
    page = _page()
    foot = re.search(r'<div class="rec-review">.*?</div>', page, re.S).group(0)
    # Three labels, each round its own box -- not one round all three.
    assert foot.count("<label") == 3
    for cls, words in [("rec-reviewed", "Reviewed"),
                       ("rec-keep-separate", "Keep patterns separate"),
                       ("rec-skip", "Skip")]:
        assert re.search(r'<label[^>]*><input\s+type="checkbox" class="%s"[^>]*/> %s</label>'
                         % (cls, words), foot), cls
    # And each says which record it is on.
    assert foot.count('aria-describedby="rec-title-${i}"') == 3
    assert 'id="rec-title-${i}"' in page


def test_toggles_say_whether_they_are_open_or_pressed():
    page = _page()
    assert 'class="rec-toggle" onclick="selectRecord(${i})" aria-expanded="false"' in page
    assert "row.querySelector('.rec-toggle').setAttribute('aria-expanded', 'true');" in page
    assert "row.querySelector('.rec-toggle').setAttribute('aria-expanded', 'false');" in page
    assert 'pc-toggle" aria-expanded="false"' in page
    # Every record filter chip starts with a state, and keeps it in step.
    chips = re.findall(r'<button type="button" class="chip[^"]*"[^>]*data-filter=[^>]*>', page)
    assert chips and all("aria-pressed=" in c for c in chips)
    assert "c.setAttribute('aria-pressed', String(c === chip));" in page
    assert "c.setAttribute('aria-pressed', String(c.dataset.filter === 'all'));" in page


def test_focus_comes_back_after_cancel_close_and_save():
    page = _page()
    # Step 2's editors: back to the opener, or the card, or the heading.
    assert page.count("const back = focusReturn(slot);") == 2
    assert page.count("slot.innerHTML = before; back(); });") == 2
    assert page.count("await replacePastedLine(") == 2
    assert 'id="patterns-heading" tabindex="-1"' in page
    # Step 3's: back to the 866's own button.
    assert "onclick=\"cancel866(${idx}, ${fi}, 'edit')\"" in page
    assert "onclick=\"cancel866(${idx}, ${first}, 'split')\"" in page
    assert "focus866(idx, fi, 'edit');" in page and "focus866(idx, fi, 'split');" in page
    # A closed record: its own line, or the one that took its place.
    close = re.search(r"function closeRecord.*?\n}\n", page, re.S).group(0)
    assert "target.querySelector('.rec-toggle')" in close
    assert ".focus({ preventScroll: true })" in close


def test_buttons_that_repeat_say_what_they_act_on():
    page = _page()
    assert 'aria-label="Edit ${escHtml(r.text)}">Edit</button>' in page
    assert 'aria-label="Edit 866 ${escHtml(pv.source_866)}"' in page
    assert 'aria-label="Edit 866 ${escHtml(f.a || \'\')}"' in page
    assert 'aria-label="Split 866 ${escHtml(f.a || \'\')}"' in page
    assert 'aria-label="Copy expression for ${escHtml(group.human_label)}"' in page
    assert 'aria-label="Close ${escHtml(rec.title)}"' in page
    assert 'aria-describedby="ex-text-${idx}"' in page
    for words in ("normal text size", "larger text", "largest text"):
        assert f'<span class="sr-only">, {words}</span>' in page
    assert ".sr-only" in _css()


def test_what_changed_out_of_sight_is_said():
    page = _page()
    assert '<div id="sr-status" class="sr-only" role="status" aria-live="polite"></div>' in page
    run = re.search(r"async function runDetect.*?\n}\n", page, re.S).group(0)
    assert "announce(`Found ${n} pattern" in run
    assert page.count("announce(document.getElementById('review-count').textContent)") == 2


def test_escape_leaves_an_editor():
    page = _page()
    assert "if (e.key !== 'Escape') return;" in page
    assert "e.target.closest('.edit866')" in page
    # Every editor's Cancel is the one Escape finds.
    assert page.count("edit-cancel") >= 5
