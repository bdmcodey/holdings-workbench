/*
 * Edit and Split on step 2, the message saying whether a fix worked, and
 * where the keyboard goes when an editor closes.
 *
 * Part of the page (templates/tool.html), which loads these files in order.
 */

function openInlineEdit(slot, target, text, { where = '', same = 0 } = {}) {
  const before = slot.innerHTML;
  const back = focusReturn(slot);
  const id = `ie-${Math.random().toString(36).slice(2, 9)}`;
  slot.innerHTML = `
    <div class="edit866 mt-1">
      ${where ? `<div class="small">${where}</div>` : ''}
      <textarea rows="2" class="mt-1 ie-text"
                aria-label="Corrected holdings statement">${escHtml(text)}</textarea>
      ${same ? `<div class="check-row mt-1">
        <input type="checkbox" class="ex-edit-same" id="${id}-same" />
        <label for="${id}-same">Also make this change on the
          ${same} other record${same !== 1 ? 's' : ''} with exactly this 866</label>
      </div>` : ''}
      <div class="btn-row mt-1">
        <button type="button" class="btn btn-primary btn-sm ie-save">Save and find patterns again</button>
        <button type="button" class="btn btn-ghost btn-sm ie-cancel edit-cancel">Cancel</button>
      </div>
      <div class="ie-status"></div>
    </div>`;
  slot.querySelector('.ie-cancel').addEventListener('click', () => { slot.innerHTML = before; back(); });
  slot.querySelector('.ie-save').addEventListener('click', async () => {
    const status = slot.querySelector('.ie-status');
    const value = slot.querySelector('.ie-text').value.split(/\s+/).join(' ').trim();
    if (!value) { showAlert(status, 'An 866 needs its holdings statement.', 'warn'); return; }
    if (target.pasted) { await replacePastedLine(text, [value]); back(); return; }
    const box = slot.querySelector('.ex-edit-same');
    status.innerHTML = '<span class="spinner"></span>';
    try {
      const data = await postJson('api/edit-866', {
        record_index: target.record_index, field_index: target.field_index, code: 'a',
        value, same_text: !!(box && box.checked) });
      await after866Change(
        [{ record_index: target.record_index, fields_866: data.fields_866 }]
          .concat(data.also || []), data.statements,
        { record_index: target.record_index, fields: [target.field_index] });
      back();
    } catch (err) {
      showAlert(status, err.message, 'err');
    }
  });
  slot.querySelector('textarea').focus();
}

function openInlineSplit(slot, target, text, { where = '' } = {}) {
  const before = slot.innerHTML;
  const back = focusReturn(slot);
  const id = `is-${Math.random().toString(36).slice(2, 9)}`;
  slot.innerHTML = `
    <div class="edit866 mt-1">
      ${where ? `<div class="small">${where}</div>` : ''}
      <div class="small mt-1">Write each part as a statement of its own, dividing where the
        change falls: for example <code>v. 19 no. 3-6 (Sept.-Dec. 1986)</code> and
        <code>v. 20 no. 1-4 (Winter-Fall 1987)</code>.${target.pasted
          ? ' The parts replace this statement in the pasted text.'
          : ' The first keeps this 866\'s notes; each other part becomes an 866 of its own right after it.'}</div>
      <div id="s866-parts-${id}" class="mt-1">
        ${[text, text].map((t, n) => splitPartHtml(id, n, t)).join('')}
      </div>
      <div class="btn-row mt-1">
        <button type="button" class="btn btn-primary btn-sm is-save">Save and find patterns again</button>
        <button type="button" class="btn btn-ghost btn-sm" onclick="addSplitPart('${id}')">Add another part</button>
        <button type="button" class="btn btn-ghost btn-sm is-cancel edit-cancel">Cancel</button>
      </div>
      <div class="is-status"></div>
    </div>`;
  slot.querySelector('.is-cancel').addEventListener('click', () => { slot.innerHTML = before; back(); });
  slot.querySelector('.is-save').addEventListener('click', async () => {
    const status = slot.querySelector('.is-status');
    const parts = [...slot.querySelectorAll('.s866-part')]
      .map(t => t.value.split(/\s+/).join(' ').trim()).filter(Boolean);
    if (parts.length < 2) {
      showAlert(status, 'A split needs at least two statements. To change one, use Edit.', 'warn');
      return;
    }
    if (target.pasted) { await replacePastedLine(text, parts); back(); return; }
    status.innerHTML = '<span class="spinner"></span>';
    try {
      const data = await postJson('api/split-866', {
        record_index: target.record_index, field_index: target.field_index, parts });
      await after866Change(
        [{ record_index: target.record_index, fields_866: data.fields_866 }], data.statements,
        { record_index: target.record_index,
          fields: parts.map((_, n) => target.field_index + n) });
      back();
    } catch (err) {
      showAlert(status, err.message, 'err');
    }
  });
  slot.querySelector('textarea').focus();
}

/**
 * Put focus back where an editor in step 2 was opened from, once it closes.
 *
 * Cancel, and Save once the patterns had been found again, took the editor
 * away with the focus in it, and focus fell to the top of the page: someone
 * on a keyboard or a screen reader started again from "Skip to content". Back
 * to the button that opened it, if it is still on screen; after a save it
 * usually is not, since the cards are drawn again, so to the same pattern's
 * Review button, and failing that to the step's heading. The page is not
 * scrolled: it stays where the cataloguer was working.
 */
function focusReturn(slot) {
  const opener = document.activeElement;
  const card = slot.closest('.pattern-card');
  const id = card && card._id;
  return () => {
    const again = [...document.querySelectorAll('.pattern-card')].find(c => c._id === id);
    const to = [opener, again && again.querySelector('.pc-toggle'),
                document.getElementById('patterns-heading')]
      .find(el => el && el.isConnected && el.getClientRects().length);
    if (to) to.focus({ preventScroll: true });
  };
}

/** Escape in an editor is its Cancel, in step 2 and step 3 alike. */
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  const editor = e.target.closest && e.target.closest('.edit866');
  const cancel = editor && editor.querySelector('.edit-cancel');
  if (!cancel) return;
  e.preventDefault();
  cancel.click();
});

/** A pasted statement corrected or split: its line, every time it is pasted. */
async function replacePastedLine(text, replacement) {
  const box = document.getElementById('stmt-input');
  box.value = box.value.split('\n')
    .flatMap(line => line.trim() === text ? replacement : [line]).join('\n');
  showPastedSummary();
  await runDetect({ keepFold: true });
  await reportFix({ pasted: replacement });
}

/**
 * After an edit or a split, from any step: every screen that read the old
 * text reads the new. The Patterns step is left folded or open as it was.
 */
async function after866Change(changes, statements, report = null) {
  changes.forEach(r => {
    if (allRecords[r.record_index]) allRecords[r.record_index].fields_866 = r.fields_866;
    recordPreviews.delete(r.record_index);
  });
  allStatements = statements;
  if (allRecords.length) await reloadReview();
  for (const r of changes) {
    const row = document.querySelector(`.rec-row[data-index="${r.record_index}"]`);
    if (row && row.classList.contains('open')) await renderRecordDetail(r.record_index);
  }
  if (detected && detected.length) await runDetect({ keepFold: true });
  if (report) await reportFix({ ...report, also: changes.length - 1 });
}

/**
 * Say what an edit or a split did, once it has been checked again.
 *
 * A fixed statement simply left the card's list, and the cataloguer could
 * not tell a fix from a statement that had gone somewhere else. So the 866
 * is converted again as its record now reads, and the result is said: it
 * converts, it converts with something to check, or it is still held, and
 * why. `report` is {record_index, fields: [shown 866 indexes]} for a file,
 * {pasted: [statements]} for pasted text.
 */
async function reportFix(report) {
  let outcome;
  try {
    outcome = report.pasted ? pastedOutcome(report.pasted) : await recordOutcome(report);
  } catch (err) {
    return;                       // the record shows it either way; say nothing wrong
  }
  if (!outcome) return;
  const others = report.also > 0
    ? ` The same change was made on ${report.also} other record${report.also !== 1 ? 's' : ''}.` : '';
  showFixToast(outcome.kind, outcome.html + others);
}

async function recordOutcome({ record_index, fields }) {
  const data = await postJson('api/preview-record', { record_index, ...conventionPayload() });
  const mine = (data.previews || []).filter(pv => fields.includes(pv.field_index));
  if (!mine.length) return null;
  const on = `on ${recordName(record_index)}`;
  const where = `the 866${mine.length > 1 ? 's' : ''} ${on}`;
  const Where = `The 866${mine.length > 1 ? 's' : ''} ${on}`;
  const held = mine.filter(pv => pv.needs_review || !pv.fields_863.length);
  if (held.length) {
    return { kind: 'attention', html: `<strong>Saved, but still held.</strong> ${Where}.
      <div class="mt-05">${escHtml((held[0].warnings || [])
        .find(w => !w.startsWith('No recognisable holdings ranges found')) || (held[0].warnings || [])[0] || '')}</div>` };
  }
  const n = mine.reduce((sum, pv) => sum + pv.fields_863.length, 0);
  const flagged = mine.filter(pv => (pv.attention || []).length);
  if (flagged.length) {
    return { kind: 'attention', html: `<strong>Saved. It converts, with something to check:</strong>
      ${Where}, ${n} 863${n !== 1 ? 's' : ''}.<div class="mt-05">${escHtml(flagged[0].attention[0])}</div>` };
  }
  return { kind: 'ok', html: `<strong>Fixed.</strong> ${Where} now convert${mine.length > 1 ? '' : 's'}:
    ${n} 863${n !== 1 ? 's' : ''}.` };
}

function pastedOutcome(texts) {
  const rows = (detected || []).flatMap(g => g.to_look_at || [])
    .filter(r => texts.includes(r.text) && r.kinds.some(k => k !== 'left_out'));
  if (!rows.length) {
    return { kind: 'ok', html: `<strong>Fixed.</strong> ${texts.length > 1 ? 'The statements now convert'
      : 'The statement now converts'}.` };
  }
  const r = rows[0];
  const reason = (r.attention || [])[0] || (r.warnings || [])
    .find(w => !w.startsWith('No recognisable holdings ranges found')) || '';
  return { kind: 'attention', html: `<strong>${r.kinds.includes('to_check')
    ? 'Saved. It converts, with something to check.' : 'Saved, but still held.'}</strong>
    <div class="mt-05">${escHtml(reason)}</div>` };
}

/**
 * Say aloud what a button did somewhere else on the page.
 *
 * Find patterns drew a step's worth of cards, and a filter chip a new list,
 * both out of sight of the button pressed, and a screen reader said nothing
 * about either. Emptied first, so the same words said twice are said again.
 */
let announceTimer = null;
function announce(text) {
  const box = document.getElementById('sr-status');
  box.textContent = '';
  clearTimeout(announceTimer);
  announceTimer = setTimeout(() => { box.textContent = text; }, 100);
}

let fixToastTimer = null;
function showFixToast(kind, html) {
  const toast = document.getElementById('fix-toast');
  toast.className = `alert alert-${kind}`;
  toast.innerHTML = `<div class="toast-text">${html}</div>
    <button type="button" class="btn btn-ghost btn-sm" aria-label="Dismiss"
            onclick="document.getElementById('fix-toast').hidden = true">✕</button>`;
  toast.hidden = false;
  clearTimeout(fixToastTimer);
  // Long enough to read a reason; a held result stays until dismissed.
  if (kind === 'ok') fixToastTimer = setTimeout(() => { toast.hidden = true; }, 8000);
}

/** What Edit or Split on a card's example works on, for pasted statements. */
function cardTarget(card) {
  // Pasted statements only: with a file the example is edited on its record,
  // in step 3 (cardInStep3).
  const example = (card._group.examples || [])[card._example] || '';
  return { target: { pasted: true }, text: example,
           where: 'The line you pasted. Saving changes it in the pasted text.' };
}

function openCardEdit(card) {
  if (sourceMode !== 'paste') { cardInStep3(card, 'edit'); return; }
  const slot = card.querySelector('.ex-edit-slot');
  const t = cardTarget(card);
  openInlineEdit(slot, t.target, t.text, { where: t.where });
}

function openCardSplit(card) {
  if (sourceMode !== 'paste') { cardInStep3(card, 'split'); return; }
  const slot = card.querySelector('.ex-edit-slot');
  const t = cardTarget(card);
  openInlineSplit(slot, t.target, t.text, { where: t.where });
}

/** The example on screen, edited on its record in step 3: see editInStep3(). */
function cardInStep3(card, kind) {
  const src = exampleSource(card);
  if (src) editInStep3(src.record_index, src.field_index, kind, card);
}

/** Where the example on screen came from, when it came from a file at all. */
function exampleSource(card) {
  return (card._group.example_sources || [])[card._example] || null;
}

/**
 * Statements to look at: every statement of a card that is held, to check or
 * not read -- or, under the "Left out" filter, that loses a value -- each with
 * its record, what happens to it and why, and Edit and Split beside it.
 *
 * Until 0.43.0 a card from a file only counted these ("224 statements, 6
 * held"), and the six could be reached only if they happened to be among the
 * 25 examples shown, or from step 3. Pasted statements had a list; a file now
 * has the same one. The statements that convert cleanly stay out of it.
 */
const LOOK_PILLS = {
  held: ['attention', 'held'],
  to_check: ['attention', 'to check'],
  unread: ['decide', 'not read'],
  left_out: ['leftout', 'left out'],
};
const LOOK_SHOWN = 10;
const lookExpanded = new Set();     // cards showing their whole list
