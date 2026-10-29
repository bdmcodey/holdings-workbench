/*
 * The pattern library: confirm, skip, remove, clear, import and export.
 *
 * Part of the page (templates/tool.html), which loads these files in order.
 */

// ─────────────────────────────────────────────────────────────────────────
// The pattern library
// ─────────────────────────────────────────────────────────────────────────

/**
 * Set this shape aside, or take it back.
 *
 * A skipped pattern still has to be stored and still has to match: matching is
 * what stops these statements falling through to the standard parser and being
 * converted anyway, which is the opposite of what was asked for.
 *
 * Skipping deliberately does not require every value to have a meaning first.
 * "I cannot tell what this is" is one of the better reasons to leave a shape
 * alone, and demanding the decisions first would make the button useless
 * exactly where it is wanted. Taking the skip off puts the pattern back through
 * those checks, and says so if it cannot pass them.
 */
async function toggleSkip(card) {
  const status  = card.querySelector('.pc-status');
  const current = library.find(p => p.id === card._id);
  const skipping = !(current && current.skip);

  const entry = {
    ...(current || {}),
    id:       card._id,
    label:    card._group.human_label,
    regex:    card.querySelector('.regex-box').value,
    roles:    collectRoles(card),
    split:    lastSplit,
    priority: card._group.count,
    notes:    (card._group.examples || [])[0] || '',
    skip:     skipping,
  };

  dismissed.delete(entry.id);
  const others = library.filter(p => p.id !== entry.id);
  const data = await withPatternChange(entry.id,
    () => saveLibrary(others.concat([entry])));

  if (data.rejected && data.rejected.length) {
    // Taking the skip off means the pattern has to stand on its own, and this
    // one cannot yet. The rejection must not cost the skip: a pattern dropped
    // from the library stops matching, and these statements would then be
    // converted by the standard parser -- the opposite of what was asked for.
    // So put it back as it was, and say what is missing.
    if (!skipping && current) await saveLibrary(others.concat([current]));
    showAlert(status, (skipping ? '' : 'Still skipped. ') + data.rejected.join(' '), 'err');
    redrawPatterns();
    return;
  }
  redrawPatterns();
}

async function confirmPattern(card) {
  const status = card.querySelector('.pc-status');
  if (undecidedCount(card)) {
    showAlert(status, 'Every captured value needs a meaning first.', 'warn');
    return;
  }

  const entry = {
    id:       card._id,
    label:    card._group.human_label,
    regex:    card.querySelector('.regex-box').value,
    roles:    collectRoles(card),
    split:    lastSplit,
    priority: card._group.count,
    // A compact label like ":#" says nothing on its own; the statement it came
    // from is how a cataloguer recognises the pattern in a list of them.
    notes:    (card._group.examples || [])[0] || '',
  };

  dismissed.delete(entry.id);
  const next = library.filter(p => p.id !== entry.id).concat([entry]);
  const data = await withPatternChange(entry.id, () => saveLibrary(next));
  if (data.rejected && data.rejected.length) {
    showAlert(status, data.rejected.join(' '), 'err');
    return;
  }

  // Confirming is the cataloguer accepting what the table shows, suggestions
  // included, so redraw it from what was saved: that puts out the "likely,
  // please confirm" labels and the pill. Only a changed row used to clear them,
  // so confirming a suggestion unchanged left "needs a decision" lit.
  card._roles = entry.roles;
  showExample(card);
  card.classList.add('confirmed');
  card.querySelector('.confirmed-pill').hidden = false;
  card.querySelector('.pc-remove').hidden = false;
  card.querySelector('.pc-confirm').textContent = 'Update confirmation';
  showAlert(status, 'Confirmed. This pattern will be used when you convert.', 'ok');
}

async function removePattern(card) {
  dismissed.add(card._id);
  await saveLibrary(library.filter(p => p.id !== card._id));
  card.classList.remove('confirmed');
  card.querySelector('.confirmed-pill').hidden = true;
  card.querySelector('.pc-remove').hidden = true;
  card.querySelector('.pc-confirm').textContent = 'Confirm pattern';
  updateCardWarnings(card);
  showAlert(card.querySelector('.pc-status'), 'Removed from the library.', 'info');
}

async function saveLibrary(patterns) {
  const res  = await fetch('api/patterns', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patterns }),
  });
  const data = await res.json();
  // A refusal leaves the stored library exactly as it was -- a pattern whose
  // expression will not finish is never stored -- so the screen has to keep
  // showing what is still there rather than emptying itself. The caller reads
  // `rejected` and says why.
  if (!res.ok || !data.patterns) return data;
  library = data.patterns || [];
  renderLibrary();
  // Every record's conversion depends on the library, so the review page and
  // any open row are now out of date. Awaited, because a caller comparing what
  // a pattern read before and after the change reads the refreshed index.
  if (allRecords.length) await refreshReview();
  return data;
}

/** Re-preview the current page and redraw whatever is open. */
async function refreshReview() {
  const open = [...document.querySelectorAll('.rec-row.open')].map(r => Number(r.dataset.index));
  recordPreviews.clear();
  await reloadReview();
  for (const idx of open) await renderRecordDetail(idx);
}

async function loadLibrary() {
  try {
    const res  = await fetch('api/patterns');
    const data = await res.json();
    library = data.patterns || [];
    renderLibrary();
  } catch (err) { console.error(err); }
}

function renderLibrary() {
  const summary = document.getElementById('library-summary');
  const list    = document.getElementById('library-list');
  revealSteps();          // the confirmed count is shown on step 3's header

  // Empty, it still says so and offers Import: a library exported last week
  // can be loaded before any file is.
  const empty = !library.length;
  document.getElementById('btn-export-library').hidden = empty;
  document.getElementById('btn-clear-library').hidden = empty;
  document.getElementById('library-about').textContent = empty
    ? 'No patterns confirmed yet. Patterns you confirm are kept here for this visit; '
      + 'import a library exported earlier to use it again.'
    : 'Every pattern confirmed so far, kept for this visit. They are tried in turn '
      + 'before the standard parser, so what is listed here is what will read your '
      + 'holdings. Remove any that should not be used, or export them to load again next time.';
  if (empty) {
    summary.textContent = 'Pattern library — empty';
    list.innerHTML = '';
    refreshPatternsSummary();
    return;
  }

  const n = library.length;
  const set_aside = library.filter(p => p.skip).length;
  summary.textContent =
    `Pattern library — ${n - set_aside} confirmed pattern${n - set_aside !== 1 ? 's' : ''} in use`
    + (set_aside ? `, ${set_aside} skipped` : '');
  // `open` is never touched: a cataloguer who opened it to remove something
  // should not have it fold up under them on the next render.
  list.innerHTML = library.map(p => `
    <div class="lib-item${p.skip ? ' skipped' : ''}">
      <span class="lib-label">${escHtml(p.label)}
        ${p.skip ? '<span class="pill skipped-pill">skipped</span>' : ''}
        ${p.notes ? `<span class="lib-example">${escHtml(p.notes)}</span>` : ''}</span>
      <button type="button" class="btn btn-ghost btn-sm" onclick="dropPattern('${escHtml(p.id)}')"
              title="Remove this pattern" aria-label="Remove ${escHtml(p.label)}">✕</button>
    </div>`).join('');
  refreshPatternsSummary();
}

async function dropPattern(id) {
  if (id) dismissed.add(id);
  await withPatternChange(id,
    () => saveLibrary(library.filter(p => p.id !== id)));
  redrawPatterns();      // so a removed pattern stops showing as confirmed
}

/** Re-render the cards from the last detection run, without re-detecting. */
function redrawPatterns() {
  if (!detected.length) return;
  renderPatterns({
    total_patterns: detected.length,
    total_statements: detected.reduce((n, g) => n + g.count, 0),
    groups: detected,
  });
}

document.getElementById('btn-clear-library').addEventListener('click', async () => {
  // Reachable now on a fresh page, with nothing else in view, and not undone
  // except by importing an export.
  const n = library.length;
  if (!confirm(`Clear all ${n} pattern${n !== 1 ? 's' : ''} from the library? `
               + 'Find patterns will confirm the ones it can read again; anything you '
               + 'chose on a card goes. Export first to keep them as they are.')) return;
  // Clear is starting over: the library is emptied and the patterns taken out
  // of it one by one are forgotten too, so the next Find patterns confirms
  // what it can read. Until 0.44.1 every cleared pattern was remembered as
  // removed, and the memory outlived an upload: clear, upload, Find patterns
  // left the library empty, with the one line that said why long gone.
  dismissed.clear();
  removedHeldBack = 0;
  await saveLibrary([]);
  showAlert(document.getElementById('library-status'),
    'Library cleared. Find patterns will confirm the patterns it can read again.',
    'info');
  if (detected.length) redrawPatterns();
});

document.getElementById('btn-import').addEventListener('click', () =>
  document.getElementById('import-input').click());

document.getElementById('import-input').addEventListener('change', async e => {
  if (!e.target.files.length) return;
  const status = document.getElementById('library-status');
  const form = new FormData();
  form.append('file', e.target.files[0]);
  form.append('merge', '1');
  try {
    const res  = await fetch('api/patterns/import', { method: 'POST', body: form });
    const data = await res.json();
    if (data.error) { showAlert(status, data.error, 'err'); return; }
    library = data.patterns || [];
    renderLibrary();
    showAlert(status,
      `Loaded ${data.imported} pattern${data.imported !== 1 ? 's' : ''}.` +
      (data.rejected.length ? ' Some were not usable: ' + data.rejected.join(' ') : ''),
      data.rejected.length ? 'warn' : 'ok');
  } catch (err) {
    showAlert(status, err.message, 'err');
  } finally {
    e.target.value = '';
  }
});
