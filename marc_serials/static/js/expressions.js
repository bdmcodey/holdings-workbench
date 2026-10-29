/*
 * A pattern's expression: Copy, "Write expressions for" other tools, and
 * "Show the records" from a card; also the pagers and what is pasted.
 *
 * Part of the page (templates/tool.html), which loads these files in order.
 */

// ── Expressions and the records a pattern runs on ────────────────────────────

/**
 * Put text on the clipboard, and say whether it got there.
 *
 * The Clipboard API wants a secure context, which http://localhost is -- but
 * the tool can be reached by another name on a network, and there it is not.
 * The older select-and-copy route works in both.
 */
async function copyText(text, statusEl) {
  let ok = false;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      ok = true;
    }
  } catch (_) { /* fall through to the older route */ }
  if (!ok) {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
    area.remove();
  }
  if (statusEl) {
    statusEl.textContent = ok ? 'Copied.' : 'Could not copy -- select the text and copy it by hand.';
    setTimeout(() => { statusEl.textContent = ''; }, 2500);
  }
  return ok;
}

/**
 * The expression a pattern stands for right now: what is in its box if the
 * card has one (edits included), else the library's copy, else the detector's.
 */
function currentRegex(group, card) {
  const box = card && card.querySelector('.regex-box');
  if (box) return box.value;
  const kept = library.find(p => p.id === patternIdFor(group));
  return (kept && kept.regex) || group.regex || '';
}

/**
 * The buttons that show a pattern's records in the list below.
 *
 * Two sets, and they are not the same thing. The records *with this shape* are
 * what the card's statement count describes. The records a confirmed pattern
 * *converts* can be fewer -- patterns are tried largest first and the first
 * whole match wins, and a statement listing several runs goes to the parser
 * even where it matches -- or more, because an expression can also match
 * statements of a neighbouring shape. On a real 372-record file one pattern
 * converted 8 of the 18 records with its shape, and another converted 31
 * against 29. Where the two differ both are offered.
 */
function paintPatternRecords(card) {
  const slot = card.querySelector('.pc-records');
  if (!slot) return;
  const group = card._group;
  const shape = (group.records || []).length;
  const kept = library.find(p => p.id === card._id);
  const plural = n => `${n} record${n !== 1 ? 's' : ''}`;
  const button = (mode, text, n) =>
    `<button type="button" class="btn btn-ghost btn-sm pc-show-records"
             data-mode="${mode}" ${n ? '' : 'disabled'}>${text}</button>`;

  const bits = [];
  if (kept && !kept.skip && recordIndex.size) {
    const converted = recordsUsing(card._id).length;
    bits.push(button('converted', `Show the ${plural(converted)} it converts`, converted));
    if (converted !== shape) {
      bits.push(button('shape', `Show the ${plural(shape)} with this shape`, shape));
    }
  } else if (shape) {
    bits.push(button('shape', `Show the ${plural(shape)} with this shape`, shape));
  }
  // Only the records with a statement held, to check or not read: for working
  // through them in step 3 rather than on the card.
  const look = (group.look_at_records || []).length;
  if (look && look !== shape && recordIndex.size) {
    bits.push(button('look', `Show the ${plural(look)} to look at`, look));
  }
  slot.innerHTML = bits.join('');
}

function refreshPatternRecordCounts() {
  document.querySelectorAll('.pattern-card').forEach(card => {
    if (card._group) paintPatternRecords(card);
  });
}

/** Narrow the record list to one pattern's records, and go there. */
function showPatternRecords(card, mode) {
  const group = card._group;
  patternFilter = {
    id: card._id,
    mode,
    indexes: new Set(mode === 'look' ? group.look_at_records || [] : group.records || []),
  };
  const chip = document.getElementById('chip-one-pattern');
  chip.textContent = `${mode === 'converted' ? 'Converted by'
    : mode === 'look' ? 'To look at, with the shape' : 'Has the shape'}: ${group.human_label}`;
  chip.hidden = false;
  document.getElementById('btn-clear-pattern-filter').hidden = false;
  filterTo('one-pattern');
  const bar = document.getElementById('review-bar');
  if (bar) bar.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/** Stop filtering by a pattern; `refilter` goes back to All. */
function clearPatternFilter(refilter = true) {
  const wasOn = reviewFilter === 'one-pattern';
  patternFilter = null;
  document.getElementById('chip-one-pattern').hidden = true;
  document.getElementById('btn-clear-pattern-filter').hidden = true;
  if (wasOn) {
    if (refilter) {
      filterTo('all');
    } else {
      reviewFilter = 'all';
      document.querySelectorAll('.filter-row .chip').forEach(c => {
        c.classList.toggle('active', c.dataset.filter === 'all');
        c.setAttribute('aria-pressed', String(c.dataset.filter === 'all'));
      });
    }
  }
}

document.getElementById('btn-clear-pattern-filter')
  .addEventListener('click', () => clearPatternFilter(true));

document.addEventListener('click', e => {
  const copy = e.target.closest('.pc-copy');
  if (copy) {
    const card = copy.closest('.pattern-card');
    flavouredText(currentRegex(card._group, card)).then(result => {
      // The card already shows why in place of the expression.
      if (!result.text) {
        copy.textContent = 'Nothing to copy';
        setTimeout(() => { copy.textContent = 'Copy'; }, 2000);
        return null;
      }
      return copyText(result.text, null);
    }).then(ok => {
      if (ok === null) return;
      copy.textContent = ok ? 'Copied' : 'Could not copy';
      setTimeout(() => { copy.textContent = 'Copy'; }, 2000);
      if (!ok) {
        // Leave it ready to copy by hand: whole, and selected.
        const expr = card.querySelector('.pc-expr');
        expr.classList.add('open');
        expr.setAttribute('aria-expanded', 'true');
        const range = document.createRange();
        range.selectNodeContents(expr);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
      }
    });
    return;
  }
  const expr = e.target.closest('.pc-expr');
  if (expr) {
    const open = expr.classList.toggle('open');
    expr.setAttribute('aria-expanded', String(open));
    return;
  }
  const show = e.target.closest('.pc-show-records');
  if (show) {
    showPatternRecords(show.closest('.pattern-card'), show.dataset.mode);
    return;
  }
  if (e.target.closest('#btn-copy-all-regex')) {
    copyAllExpressions();
  }
});

document.addEventListener('keydown', e => {
  const expr = e.target.closest && e.target.closest('.pc-expr');
  if (expr && (e.key === 'Enter' || e.key === ' ')) {
    e.preventDefault();
    expr.click();
  }
});

// The line above the card follows the box below it, so what Copy takes is
// what the card shows. Briefly behind while typing: it is rewritten for the
// chosen tool on the server.
document.addEventListener('input', e => {
  if (!e.target.classList.contains('regex-box')) return;
  scheduleFlavoured(e.target.closest('.pattern-card'), 250);
});

document.addEventListener('change', e => {
  if (e.target.id !== 'regex-flavour') return;
  regexFlavour = e.target.value;
  try { localStorage.setItem(FLAVOUR_KEY, regexFlavour); } catch (_) {}
  paintFlavourAlert();
  document.querySelectorAll('.pattern-card').forEach(c => {
    if (c._group && !c._group.too_complex) scheduleFlavoured(c);
  });
});

// ── The expression, written for another tool ─────────────────────────────────
//
// The workbench runs an expression in Python, ignoring capitals and against
// the whole statement. The menu above the patterns rewrites it for the tool
// the cataloguer is pasting into, with both of those settings in that tool's
// form. The rewriting is done by the server (marc_serials/flavours.py), where
// it is tested against the tools' own engines; this keeps what it sent back.

const FLAVOUR_KEY = 'mst-regex-flavour';
let regexFlavour = DEFAULT_REGEX_FLAVOUR;
try {
  const saved = localStorage.getItem(FLAVOUR_KEY);
  if (REGEX_FLAVOURS.some(f => f.key === saved)) regexFlavour = saved;
} catch (_) {}

const flavourCache = new Map();          // flavour + "\n" + regex -> {text, error}

function flavourLabel(key = regexFlavour) {
  return (REGEX_FLAVOURS.find(f => f.key === key) || {}).label || key;
}

/** Each expression in the chosen flavour: {text} or {text: null, error}. */
async function flavouredTexts(regexes, flavour = regexFlavour) {
  const keyOf = r => flavour + '\n' + r;
  const missing = [...new Set(regexes)].filter(r => r && !flavourCache.has(keyOf(r)));
  if (missing.length) {
    try {
      const data = await postJson('api/regex-flavour', { flavour, regexes: missing });
      missing.forEach((r, i) => flavourCache.set(keyOf(r), data.results[i]));
    } catch (err) {
      // Not kept: the next attempt should ask again.
      return regexes.map(r => flavourCache.get(keyOf(r)) || {
        text: null, error: `Could not be written for ${flavourLabel(flavour)}: ${err.message}`,
      });
    }
  }
  return regexes.map(r => (r ? flavourCache.get(keyOf(r))
                             : { text: null, error: 'There is no expression.' }));
}

async function flavouredText(regex) {
  return (await flavouredTexts([regex]))[0];
}

/** Show a card's expression as the chosen tool writes it, or why it cannot. */
function paintFlavoured(card, result) {
  const expr = card.querySelector('.pc-expr');
  const copy = card.querySelector('.pc-copy');
  if (!expr) return;
  const refused = !result.text;
  expr.textContent = refused ? result.error : result.text;
  expr.classList.toggle('refused', refused);
  expr.title = refused ? `${flavourLabel()} cannot take this expression`
                       : 'Click to show the whole expression';
  if (copy) {
    copy.disabled = refused;
    copy.title = refused ? 'Nothing to copy for this tool; the line says why'
                         : 'Copy this expression, including any edits made below';
  }
}

// Cards are rewritten together, one request for all of them.
const flavourPending = new Set();
let flavourTimer = null;

function scheduleFlavoured(card, delay = 0) {
  flavourPending.add(card);
  clearTimeout(flavourTimer);
  flavourTimer = setTimeout(flushFlavoured, delay);
}

async function flushFlavoured() {
  const cards = [...flavourPending];
  flavourPending.clear();
  const flavour = regexFlavour;
  const wanted = cards.map(c => currentRegex(c._group, c));
  const results = await flavouredTexts(wanted, flavour);
  cards.forEach((card, i) => {
    // Edited again or another tool chosen since: a newer request is coming.
    if (flavour !== regexFlavour || currentRegex(card._group, card) !== wanted[i]) return;
    paintFlavoured(card, results[i]);
  });
}

function flavourChooserHtml() {
  return `
    <div class="flavour-row">
      <label for="regex-flavour" class="small">Write expressions for</label>
      <select id="regex-flavour">${REGEX_FLAVOURS.map(f =>
        `<option value="${escHtml(f.key)}" ${f.key === regexFlavour ? 'selected' : ''}>${
          escHtml(f.label)}</option>`).join('')}</select>
    </div>
    <div id="flavour-alert" class="small mt-1"></div>`;
}

function paintFlavourAlert() {
  const el = document.getElementById('flavour-alert');
  const f = REGEX_FLAVOURS.find(x => x.key === regexFlavour);
  if (!el || !f) return;
  el.className = `alert ${f.severity === 'warn' ? 'alert-warn' : 'alert-info'} small mt-1`;
  el.textContent = f.alert;
}

/**
 * Every expression, one line per pattern, tab-separated so it pastes into a
 * spreadsheet as three columns: heading, statements, expression. A pattern
 * the chosen tool cannot take keeps its line, with the reason in place of the
 * expression. Patterns declined as too complex have no expression at all.
 */
async function copyAllExpressions() {
  const status = document.getElementById('copy-all-status');
  const cards = new Map([...document.querySelectorAll('.pattern-card')]
    .filter(c => c._group).map(c => [patternIdFor(c._group), c]));
  const groups = detected.filter(g => !g.too_complex && (g.regex || '').length);
  const results = await flavouredTexts(
    groups.map(g => currentRegex(g, cards.get(patternIdFor(g)))));
  const refused = results.filter(r => !r.text).length;
  const lines = groups.map((g, i) => [g.human_label, g.count,
    results[i].text || `(not written: ${results[i].error})`].join('\t'));
  const ok = await copyText(lines.join('\n'), null);
  if (!status) return;
  status.textContent = !ok
    ? 'Could not copy -- select the text and copy it by hand.'
    : `Copied ${groups.length - refused} for ${flavourLabel()}.` + (refused
      ? ` ${refused} could not be written for it; ${refused === 1 ? 'its line says' : 'their lines say'} why.`
      : '');
  setTimeout(() => { status.textContent = ''; }, refused ? 8000 : 2500);
}

/**
 * Open the pattern that read this statement, wherever it is on the screen.
 *
 * A mistake is nearly always spotted while reviewing records, and the place to
 * fix it is the pattern -- which by then may be folded inside step 2, inside a
 * group, with its own body closed. All three have to give way, or the link
 * lands the cataloguer on a screen with nothing visibly different about it.
 */
function jumpToPattern(patternId) {
  const card = [...document.querySelectorAll('.pattern-card')]
    .find(c => c._id === patternId);

  if (!card) {
    // In the library but not on screen: the library outlives a detection run,
    // and can be imported without one. Say so rather than doing nothing.
    const known = library.find(p => p.id === patternId);
    alert(known
      ? `"${known.label}" is in your library but not in the patterns on screen. `
        + 'Run "Find patterns" again to work on it.'
      : 'That pattern is no longer in your library.');
    return;
  }

  setPatternsCollapsed(false);
  const fold = card.closest('.pattern-group');
  if (fold) fold.open = true;               // the toggle handler records this
  if (card.querySelector('.pc-body').hidden) card.querySelector('.pc-toggle').click();

  card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  card.classList.add('jumped-to');
  setTimeout(() => card.classList.remove('jumped-to'), 2500);
}

document.addEventListener('click', e => {
  const link = e.target.closest('.jump-to-pattern');
  if (link) jumpToPattern(link.dataset.pattern);
});

/** Every record the whole-file index says this pattern read. */
function recordsUsing(patternId) {
  const out = [];
  recordIndex.forEach((row, index) => {
    if ((row.sources || []).includes(patternId)) out.push(index);
  });
  return out;
}

/**
 * Make a change to one pattern, and un-review the records it touched.
 *
 * This is the half of "jump back to the pattern" that matters. Editing a
 * pattern rewrites the MARC for every record it reads, including ones a
 * cataloguer has already ticked off -- and a tick that no longer describes
 * anything anybody looked at is worse than no tick at all, because it is
 * indistinguishable from one that does.
 *
 * Both sides of the change count: records the pattern read before it (whose
 * conversion has now changed or gone) and records it reads after it (which it
 * may not have matched before).
 */
async function withPatternChange(patternId, change) {
  const before = recordsUsing(patternId);
  const result = await change();
  const after = recordsUsing(patternId);

  const touched = [...new Set([...before, ...after])].filter(i => reviewed.has(i));
  if (touched.length) {
    touched.forEach(i => {
      reviewed.delete(i);
      const row = document.querySelector(`.rec-row[data-index="${i}"]`);
      if (row) {
        row.classList.remove('reviewed');
        const box = row.querySelector('.rec-reviewed');
        if (box) box.checked = false;
      }
    });
    announceUnreviewed(touched.length);
    applyReviewFilter();
  }
  return result;
}

function announceUnreviewed(n) {
  const notice = document.getElementById('review-notice');
  if (!notice) return;
  notice.innerHTML = `<div class="alert alert-info">Editing that pattern changed
    what ${n} record${n !== 1 ? 's' : ''} you had already reviewed would produce,
    so ${n !== 1 ? 'they have' : 'it has'} gone back to
    "${n !== 1 ? 'not yet reviewed' : 'not yet reviewed'}".</div>`;
  notice.hidden = false;
}

document.getElementById('btn-patt-prev').addEventListener('click', () => {
  patternOffset = Math.max(0, patternOffset - PATTERN_PAGE);
  redrawPatterns();
  document.getElementById('patterns-area').scrollIntoView(
    { block: 'start', behavior: 'smooth' });
});

document.getElementById('btn-patt-next').addEventListener('click', () => {
  patternOffset += PATTERN_PAGE;
  redrawPatterns();
  document.getElementById('patterns-area').scrollIntoView(
    { block: 'start', behavior: 'smooth' });
});

document.getElementById('btn-page-prev').addEventListener('click', () => {
  closeOpenRecords();
  reviewOffset = Math.max(0, reviewOffset - reviewPageLimit());
  loadReviewPage();
});
document.getElementById('btn-page-next').addEventListener('click', () => {
  closeOpenRecords();
  reviewOffset += reviewPageLimit();
  loadReviewPage();
});

// Records per page. A new size starts from the first page, as a new filter
// does: page 3 of tens and page 3 of fifties are different records.
(function () {
  const select = document.getElementById('review-page-size');
  let saved = null;
  try { saved = localStorage.getItem('mst-review-page'); } catch (e) {}
  if (saved === 'all') saved = '50';
  if (REVIEW_PAGE_SIZES.includes(saved)) reviewPageSize = saved;
  select.value = reviewPageSize;

  select.addEventListener('change', () => {
    reviewPageSize = select.value;
    try { localStorage.setItem('mst-review-page', reviewPageSize); } catch (e) {}
    closeOpenRecords();
    reviewOffset = 0;
    if (allRecords.length) loadReviewPage();
  });
})();

document.getElementById('btn-expand-all').addEventListener('click', () => {
  document.querySelectorAll('.rec-row:not([hidden])').forEach(row => {
    if (row.querySelector('.rec-detail').hidden) selectRecord(Number(row.dataset.index));
  });
});
document.getElementById('btn-collapse-all').addEventListener('click', () => {
  closeOpenRecords();
  // Records kept open after they stopped matching leave the list now.
  applyReviewFilter();
});

function pastedStatements() {
  return document.getElementById('stmt-input').value
    .split('\n').map(s => s.trim()).filter(Boolean);
}

/** The statements pattern detection runs over: the file, or what was pasted. */
function statementsForDetection() {
  const source = sourceMode === 'paste' ? pastedStatements() : allStatements;
  if (!document.getElementById('opt-dedup').checked) return source;
  return [...new Set(source)];
}
