/*
 * Step 3, Convert: an open record, its 866s with Edit and Split, its 853,
 * its note, and Convert all records.
 *
 * Part of the page (templates/tool.html), which loads these files in order.
 */

// ─────────────────────────────────────────────────────────────────────────
// 3 · Convert
// ─────────────────────────────────────────────────────────────────────────

async function selectRecord(idx) {
  const row = document.querySelector(`.rec-row[data-index="${idx}"]`);
  const detail = row.querySelector('.rec-detail');

  if (!detail.hidden) {                      // second click closes it
    closeRecord(idx, false);
    return;
  }
  detail.hidden = false;
  row.classList.add('open');
  row.querySelector('.rec-caret').textContent = '▾';
  row.querySelector('.rec-toggle').setAttribute('aria-expanded', 'true');
  await renderRecordDetail(idx);
}

/**
 * Fold an open record back to its line. From the Close at its foot, the
 * folded line is brought into view, since what was on screen has gone.
 */
function closeRecord(idx, bringIntoView = true) {
  const row = document.querySelector(`.rec-row[data-index="${idx}"]`);
  if (!row) return;
  foldRow(row);
  // A record that no longer matches the filter leaves the list now.
  applyReviewFilter();
  // The closed record, or, if it has left the list, the one that took its
  // place -- the next to work on.
  let target = row;
  while (target && target.hidden) target = target.nextElementSibling;
  // Focus goes with it. The Close it was on is hidden now, and so is the
  // line's own button when the record has left the list; either way focus
  // fell to the top of the page.
  if (bringIntoView || row.hidden) {
    const to = target ? target.querySelector('.rec-toggle')
      : document.querySelector('.filter-row .chip.active');
    if (to) to.focus({ preventScroll: true });
  }
  if (!bringIntoView) return;
  // To the top of the screen. Closing at the foot of a long record used to
  // leave the screen wherever the record's middle had been, and the way back
  // was scrolling up.
  (target || document.getElementById('review-bar')).scrollIntoView({ block: 'start' });
}

function foldRow(row) {
  row.querySelector('.rec-detail').hidden = true;
  row.classList.remove('open');
  row.querySelector('.rec-caret').textContent = '▸';
  row.querySelector('.rec-toggle').setAttribute('aria-expanded', 'false');
}

/** Close whatever is open, before the list moves to another filter or page. */
function closeOpenRecords() {
  document.querySelectorAll('.rec-row.open').forEach(foldRow);
}

/**
 * The record's 866s as they stand, each with an Edit button.
 *
 * Above the conversion rather than inside it, so every 866 can be corrected --
 * a statement nothing was converted from as much as one that converted wrong,
 * and on a record kept for its own 863s too.
 */
function fields866Html(idx) {
  const fields = allRecords[idx].fields_866 || [];
  if (!fields.length) return '';
  return `
    <div class="f866-list">
      <div class="pair-col-label">866 fields — edit one to correct a typo and check it again,
        or split one to say where a change falls</div>
      ${fields.map((f, fi) => `
        <div class="f866-row" id="f866-${idx}-${fi}">
          <div class="field-display">${highlightField(escHtml(f.display))}${
            f.split_part != null ? ` <span class="pill" title="You split one 866 into
              these statements">split ${f.split_part + 1}</span>` : ''}</div>
          ${f.split_part == null ? `<button type="button" class="btn btn-secondary btn-sm f866-edit"
                  aria-label="Edit 866 ${escHtml(f.a || '')}"
                  onclick="openEdit866(${idx}, ${fi})">Edit</button>` : ''}
          <button type="button" class="btn btn-ghost btn-sm f866-split"
                  aria-label="Split 866 ${escHtml(f.a || '')}"
                  title="Make this 866 into two or more statements, to say where a change falls that it does not show, such as months to seasons"
                  onclick="openSplit866(${idx}, ${fi})">Split</button>
        </div>`).join('')}
    </div>`;
}

/**
 * The cataloguer's own note on this record: for the log, never the file.
 *
 * A reminder to a person -- why a record was skipped, what to look at when it
 * is opened in the ILS -- rather than $x or $z, which are written into the
 * record. Saved when it loses focus as well as on the button, so a note
 * typed and walked away from is not lost.
 */
/**
 * This record's 853: its $w, and a caption for each level its statements
 * leave blank.
 *
 * How often a serial is published differs from title to title and no holdings
 * statement says it, so it is set here, record by record, rather than once for
 * the file. A caption given here fills only levels the statements print none
 * for -- the rule a confirmed pattern follows -- but reaches every statement on
 * the record whatever its shape, so two shapes of one serial can share an 853.
 */
function record853Html(idx, about) {
  const chosen = (about && about.record_853) || {};
  const levels = (about && about.uncaptioned_levels) || [];
  const fileFreq = document.getElementById('batch-freq');
  const fileLabel = fileFreq.options[fileFreq.selectedIndex].text;
  const fileUnits = document.getElementById('batch-units').value.trim();
  const fileCont = document.getElementById('batch-continuity');
  const fileContLabel = fileCont.options[fileCont.selectedIndex].text;
  const contOptions = [...fileCont.options].map(o =>
    `<option value="${escHtml(o.value)}" ${'numbering_continuity' in chosen
      && chosen.numbering_continuity === o.value ? 'selected' : ''}>${escHtml(o.text)}</option>`).join('');
  const freqOptions = [...fileFreq.options].map(o =>
    `<option value="${escHtml(o.value)}" ${'frequency' in chosen && chosen.frequency === o.value
      ? 'selected' : ''}>${escHtml(o.text)}</option>`).join('');
  const captions = chosen.captions || {};
  const captionRows = levels.map(level => `
      <div class="form-group">
        <label for="r853-cap-${idx}-${level}">Caption for the ${ordinal(level + 1)} level</label>
        <input type="text" id="r853-cap-${idx}-${level}" class="r853-cap" list="caption-words"
               data-level="${level}" maxlength="20" placeholder="(*) — none printed"
               value="${escHtml(captions[String(level)] || '')}" />
      </div>`).join('');
  return `
    <div class="record-853 mt-2">
      <div class="pair-col-label">This record's 853 — applies to this record only</div>
      <div class="form-row mt-1">
        <div class="form-group">
          <label for="r853-freq-${idx}">Frequency ($w)</label>
          <select id="r853-freq-${idx}">
            <option value="__file" ${'frequency' in chosen ? '' : 'selected'}>As in Conversion settings: ${escHtml(fileLabel)}</option>
            ${freqOptions}
          </select>
        </div>
        <div class="form-group">
          <label for="r853-units-${idx}">Issues per volume ($u)</label>
          <input type="text" id="r853-units-${idx}" maxlength="4"
                 placeholder="As in Conversion settings: ${escHtml(fileUnits || 'not specified')}"
                 value="${escHtml('units_per_higher' in chosen
                   ? (chosen.units_per_higher || 'none') : '')}" />
        </div>
        <div class="form-group">
          <label for="r853-cont-${idx}">Numbering ($v)</label>
          <select id="r853-cont-${idx}">
            <option value="__file" ${'numbering_continuity' in chosen ? '' : 'selected'}>As in Conversion settings: ${escHtml(fileContLabel)}</option>
            ${contOptions}
          </select>
        </div>
        ${captionRows}
      </div>
      <div class="small dim mt-1">Issues per volume: a number such as 4 or 12, or
        <code>var</code> or <code>und</code>. Leave it empty to use Conversion settings, or
        type <code>none</code> to write no $u on this record.</div>
      ${levels.length ? `<div class="small dim mt-1">A caption here fills a level these
        statements print no caption for, on every 866 of this record, and nowhere else.
        A caption a statement prints is never replaced; to correct one, edit its 866.</div>` : ''}
      <div class="btn-row mt-1">
        <button type="button" class="btn btn-secondary btn-sm"
                onclick="saveRecord853(${idx})">Save for this record</button>
        <span id="r853-status-${idx}" class="small dim" style="align-self:center;"></span>
      </div>
    </div>`;
}

async function saveRecord853(idx) {
  const status = document.getElementById(`r853-status-${idx}`);
  const freq = document.getElementById(`r853-freq-${idx}`).value;
  const cont = document.getElementById(`r853-cont-${idx}`).value;
  const captions = {};
  document.querySelectorAll(`.rec-row[data-index="${idx}"] .r853-cap`).forEach(box => {
    if (box.value.trim()) captions[box.dataset.level] = box.value.trim();
  });
  try {
    const units = document.getElementById(`r853-units-${idx}`).value.trim();
    const data = await postJson('api/record-853', {
      record_index: idx,
      frequency: freq === '__file' ? null : freq,
      units_per_higher: units || null,
      numbering_continuity: cont === '__file' ? null : cont,
      captions,
    });
    const entry = recordIndex.get(idx);
    if (entry) entry.record_853 = data.record_853;
    // The record's 853 and 863s are now different: fetch them again.
    recordPreviews.delete(idx);
    paintRecordStatus();
    await renderRecordDetail(idx);
    const after = document.getElementById(`r853-status-${idx}`);
    if (after) after.textContent = Object.keys(data.record_853).length
      ? 'Saved. It is used whenever this record is converted, and is in the log.'
      : 'Back to the Conversion settings.';
  } catch (err) {
    if (status) status.textContent = `Not saved: ${err.message}`;
  }
}

function recordNoteHtml(idx) {
  const entry = recordIndex.get(idx) || {};
  return `
    <div class="rec-note">
      <label class="pair-col-label" for="note-${idx}">Your note — goes in the log only, never in the record</label>
      <textarea id="note-${idx}" rows="2" class="mt-1"
                placeholder="Why this record was skipped, or what to check in the catalogue"
                data-saved="${escHtml(entry.note || '')}"
                onblur="saveRecordNote(${idx})">${escHtml(entry.note || '')}</textarea>
      <div class="btn-row mt-1">
        <button type="button" class="btn btn-secondary btn-sm"
                onclick="saveRecordNote(${idx}, true)">Save note</button>
        <span id="note-status-${idx}" class="small dim" style="align-self:center;"></span>
      </div>
    </div>`;
}

async function saveRecordNote(idx, force) {
  const box = document.getElementById(`note-${idx}`);
  if (!box) return;
  const note = box.value.trim();
  if (!force && note === (box.dataset.saved || '')) return;
  const status = document.getElementById(`note-status-${idx}`);
  try {
    const data = await postJson('api/record-note', { record_index: idx, note });
    box.dataset.saved = data.note;
    const entry = recordIndex.get(idx);
    if (entry) entry.note = data.note;
    paintRecordStatus();
    if (status) status.textContent = data.note ? 'Saved. It will be in the log.' : 'Note removed.';
  } catch (err) {
    if (status) status.textContent = `Not saved: ${err.message}`;
  }
}

const EDIT_866_LABELS = { a: '$a Textual holdings', z: '$z Public note', x: '$x Nonpublic note' };

function openEdit866(idx, fi) {
  const f = allRecords[idx].fields_866[fi];
  const row = document.getElementById(`f866-${idx}-${fi}`);
  const id = `${idx}-${fi}`;
  row.innerHTML = `
    <div class="edit866">
      <label class="small" for="e866-code-${id}">Subfield</label>
      <select id="e866-code-${id}">
        ${Object.entries(EDIT_866_LABELS).map(([code, label]) =>
          `<option value="${code}"${code === 'a' ? ' selected' : ''}>${escHtml(label)}</option>`).join('')}
      </select>
      <textarea id="e866-text-${id}" rows="2" class="mt-1"
                aria-label="New text for this subfield">${escHtml(f.a || '')}</textarea>
      <div class="btn-row mt-1">
        <button type="button" class="btn btn-primary btn-sm"
                onclick="saveEdit866(${idx}, ${fi}, false)">Save and check again</button>
        <button type="button" class="btn btn-ghost btn-sm edit-cancel"
                onclick="cancel866(${idx}, ${fi}, 'edit')">Cancel</button>
        <button type="button" class="btn btn-ghost btn-sm"
                title="Undo your correction to this subfield"
                onclick="saveEdit866(${idx}, ${fi}, true)">Put back as uploaded</button>
      </div>
      <div id="e866-status-${id}"></div>
    </div>`;
  const code = document.getElementById(`e866-code-${id}`);
  const text = document.getElementById(`e866-text-${id}`);
  code.addEventListener('change', () => { text.value = f[code.value] || ''; text.focus(); });
  text.focus();
}

/**
 * Split one 866 into several statements.
 *
 * How a cataloguer says where a change falls that the statement does not show:
 * "v. 19 no. 3-v. 20 no. 4 (September 1986-Winter 1987)" changes from months
 * to seasons somewhere inside, which is held until it is split there. Opened on
 * any part of an earlier split, it shows all the parts, to change or undo.
 */
function openSplit866(idx, fi) {
  const fields = allRecords[idx].fields_866;
  const f = fields[fi];
  // A part of an earlier split edits the whole split, from its first part.
  let first = fi;
  let parts = [f.a || '', f.a || ''];
  if (f.split_part != null) {
    const mine = fields.map((g, gi) => ({ g, gi }))
      .filter(({ g }) => g.split_part != null && g.position === f.position);
    first = mine[0].gi;
    parts = mine.map(({ g }) => g.a || '');
    mine.slice(1).forEach(({ gi }) => {
      const row = document.getElementById(`f866-${idx}-${gi}`);
      if (row) row.remove();
    });
  }
  const row = document.getElementById(`f866-${idx}-${first}`);
  const id = `${idx}-${first}`;
  row.innerHTML = `
    <div class="edit866">
      <div class="small">Write each part as a statement of its own, dividing where the
        change falls: for example <code>v. 19 no. 3-6 (Sept.-Dec. 1986)</code> and
        <code>v. 20 no. 1-4 (Winter-Fall 1987)</code>. The first keeps this 866's notes;
        each other part becomes an 866 of its own right after it.</div>
      <div id="s866-parts-${id}" class="mt-1">
        ${parts.map((p, i) => splitPartHtml(id, i, p)).join('')}
      </div>
      <div class="btn-row mt-1">
        <button type="button" class="btn btn-primary btn-sm"
                onclick="saveSplit866(${idx}, ${first}, false)">Save and check again</button>
        <button type="button" class="btn btn-ghost btn-sm"
                onclick="addSplitPart('${id}')">Add another part</button>
        <button type="button" class="btn btn-ghost btn-sm edit-cancel"
                onclick="cancel866(${idx}, ${first}, 'split')">Cancel</button>
        ${f.split_part != null ? `<button type="button" class="btn btn-ghost btn-sm"
                title="Put this 866 back as one statement, as uploaded"
                onclick="saveSplit866(${idx}, ${first}, true)">Undo the split</button>` : ''}
      </div>
      <div id="s866-status-${id}"></div>
    </div>`;
  row.querySelector('textarea').focus();
}

/**
 * Back to the 866's own Edit or Split once its editor in step 3 closes, or to
 * the record's line if that 866 has gone; the record is drawn again either
 * way, and focus used to fall to the top of the page with it.
 */
function focus866(idx, fi, kind) {
  const row = document.querySelector(`.rec-row[data-index="${idx}"]`);
  const to = document.querySelector(`#f866-${idx}-${fi} .f866-${kind}`)
    || (row && row.querySelector('.rec-toggle'));
  if (to) to.focus({ preventScroll: true });
}

async function cancel866(idx, fi, kind) {
  await renderRecordDetail(idx);
  focus866(idx, fi, kind);
}

function splitPartHtml(id, i, text) {
  return `<div class="split-part">
    <label class="small" for="s866-${id}-${i}">Part ${i + 1}</label>
    <textarea id="s866-${id}-${i}" rows="2" class="s866-part">${escHtml(text)}</textarea>
  </div>`;
}

function addSplitPart(id) {
  const box = document.getElementById(`s866-parts-${id}`);
  const n = box.querySelectorAll('.s866-part').length;
  box.insertAdjacentHTML('beforeend', splitPartHtml(id, n, ''));
  box.querySelectorAll('.s866-part')[n].focus();
}

async function saveSplit866(idx, fi, revert) {
  const id = `${idx}-${fi}`;
  const parts = [...document.querySelectorAll(`#s866-parts-${id} .s866-part`)]
    .map(t => t.value);
  const status = document.getElementById(`s866-status-${id}`);
  status.innerHTML = '<span class="spinner"></span>';
  try {
    const data = await postJson('api/split-866', {
      record_index: idx, field_index: fi, parts, revert });
    allRecords[idx].fields_866 = data.fields_866;
    allStatements = data.statements;
    recordPreviews.delete(idx);
    await reloadReview();
    await renderRecordDetail(idx);
    focus866(idx, fi, 'split');
    if (detected && detected.length) runDetect({ keepFold: true });
    if (!revert) reportFix({ record_index: idx,
      fields: parts.filter(t => t.trim()).map((_, n) => fi + n) });
  } catch (err) {
    showAlert(status, err.message, 'err');
  }
}

/**
 * Store the correction, then redraw everything that read the old text: this
 * record's preview, the list the filters run on, and -- when the holdings
 * statement changed and patterns have been found -- pattern detection.
 */
async function saveEdit866(idx, fi, revert) {
  const id = `${idx}-${fi}`;
  const code = document.getElementById(`e866-code-${id}`).value;
  const value = document.getElementById(`e866-text-${id}`).value;
  const status = document.getElementById(`e866-status-${id}`);
  status.innerHTML = '<span class="spinner"></span>';
  try {
    const data = await postJson('api/edit-866', {
      record_index: idx, field_index: fi, code, value, revert });
    allRecords[idx].fields_866 = data.fields_866;
    allStatements = data.statements;
    recordPreviews.delete(idx);
    await reloadReview();
    await renderRecordDetail(idx);
    focus866(idx, fi, 'edit');
    // Left folded or open as it was: folding step 2 above the record being
    // worked on moved the whole page under the cataloguer.
    if (code === 'a' && detected && detected.length) runDetect({ keepFold: true });
    if (!revert) reportFix({ record_index: idx, fields: [fi] });
  } catch (err) {
    showAlert(status, err.message, 'err');
  }
}

async function renderRecordDetail(idx) {
  const rec = allRecords[idx];
  // The title is already on the row's own button, so the detail does not repeat it.
  const detail = document.querySelector(`.rec-row[data-index="${idx}"] .rec-detail`);

  if (!rec.fields_866.length) {
    detail.innerHTML =
      '<div class="alert alert-info">No 866 fields found in this record.</div>'
      + recordNoteHtml(idx);
    return;
  }

  // The review page already fetched this record's preview, so opening a row
  // usually costs nothing; a record outside the current page still asks.
  const cached = recordPreviews.get(idx);
  let previews = cached ? cached.previews : null;
  // What the record says about itself as a whole: kept for its own 863s, or
  // an existing 853 worth a look. Carried on the cached row and on the
  // single-record preview alike.
  let about = cached || null;

  if (!previews) {
    detail.innerHTML = '<span class="spinner"></span>';
    try {
      const data = await postJson('api/preview-record', {
        record_index: idx,
        ...conventionPayload(),
      });
      previews = data.previews;
      about = data;
    } catch (err) {
      detail.innerHTML =
        `<div class="alert alert-err">Preview failed: ${escHtml(err.message)}</div>`;
      return;
    }
  }

  const notesHtml = ((about && about.record_notes) || [])
    .map(n => `<div class="alert alert-warn mt-2">${escHtml(n)}</div>`).join('');
  const editedHtml = ((about && about.edited) || [])
    .map(n => `<div class="alert alert-info mt-2">${escHtml(n)}</div>`).join('');
  const sourceHtml = fields866Html(idx) + editedHtml;
  if (about && about.kept_existing) {
    const n = about.existing_863;
    detail.innerHTML = `
      <div class="alert alert-info">This record already has ${n} 863
        field${n !== 1 ? 's' : ''}, so it is kept exactly as it is: nothing is
        generated beside ${n !== 1 ? 'them' : 'it'} and nothing is replaced.
        To regenerate its 853s and 863s from its 866s instead, tick
        "Clear existing 853 / 863 first" in Conversion settings.</div>
      ${notesHtml}
      <div class="mt-2">${sourceHtml}</div>
      ${recordNoteHtml(idx)}`;
    return;
  }

  // In the order the 866s come, each under the 853 it links to, a held
  // statement where it falls: see inRecordOrder().
  const elsewhere = previews.filter(pv => pv.belongs_in);
  const counts = linkCounts(previews);
  const groupsHtml = inRecordOrder(previews).map(seg => seg.held
    ? heldRowsHtml(seg.rows, idx)
    : `
    <div class="pattern-group">
      <div class="pg-header">
        <div class="pg-header-meta">
          <span class="pg-title">Pattern $8 ${escHtml(seg.link)}${seg.continued ? ', continued' : ''}</span>
          <span class="pill ${seg.existing ? '' : 'has-866'}">${
            seg.existing ? 'already on this record' : 'generated'}</span>
          <span class="dim small">${counts[seg.link]} statement${counts[seg.link] !== 1 ? 's' : ''}</span>
          ${seg.merged ? `<span class="pill decide"
             title="These statements record different amounts of detail. Tick &quot;Keep patterns separate&quot; below if they are not one publication.">merged</span>` : ''}
        </div>
        <div class="field-display f853">${highlightField(escHtml(seg.field_853 || ''))}</div>
      </div>
      ${seg.rows.map(pv => `
        <div class="pair-row">
          <div>
            <div class="pair-col-label">866 — source</div>
            <div class="field-display f866">${escHtml(pv.source_866)}</div>
            <div class="small dim mt-1">
              read by <span class="pill ${pv.from_pattern ? 'from-pattern' : ''}">${escHtml(pv.source_label)}</span>
              ${pv.from_pattern ? `<button type="button" class="btn btn-ghost btn-sm jump-to-pattern"
                data-pattern="${escHtml(pv.source)}"
                title="Open this pattern in step 2">Edit this pattern ↑</button>` : ''}
            </div>
          </div>
          <div>
            <div class="pair-col-label">863 — generated</div>
            ${pv.fields_863.map(f => fieldHtml(f, 'f863')).join('')}
            ${(pv.warnings || []).length ? `
              <div class="mt-1">
                ${pv.warnings.map(w => warningHtml(pv, w)).join('')}
              </div>` : ''}
          </div>
        </div>`).join('')}
    </div>`).join('');
  const leftAsUploaded = (about && about.left_as_uploaded) || [];
  const leftHtml = leftAsUploaded.length ? `
    <div class="alert alert-attention mt-2"><strong>Left as uploaded by your setting.</strong>
      Converting this record would leave something out to fit MARC, and Conversion settings
      say to leave such a record exactly as it is. Below is what converting would have
      written; nothing of it goes into the file. What would be left out:
      ${leftAsUploaded.map(w => `<div class="mt-1"><code>${escHtml(w.text)}</code>:
        ${escHtml(w.reason)}</div>`).join('')}</div>` : '';
  detail.innerHTML = `
    ${sourceHtml}
    ${notesHtml}
    ${leftHtml}
    ${groupsHtml}
    ${elsewhereHtml(elsewhere)}
    ${record853Html(idx, about)}
    <div class="btn-row">
      <button class="btn btn-primary" onclick="applyAllInRecord(${idx})"
              title="Linking numbers are shared across a record, so conversion applies to every 866 here">
        Convert this record
      </button>
      <a href="api/download-record?index=${idx}" class="btn btn-success btn-sm"
         id="dl-record-${idx}" ${convertedRecords.has(idx) ? '' : 'hidden'}
         title="This record on its own, as it now stands, named after its identifier">
        Download this record
      </a>
    </div>
    <div id="record-status-${idx}" class="mt-2"></div>
    ${recordNoteHtml(idx)}`;
}

async function applyAllInRecord(recIdx) {
  const rec = allRecords[recIdx];
  const status = document.getElementById(`record-status-${recIdx}`);
  status.innerHTML = '<span class="spinner"></span> Converting…';

  const settings = conventionPayload();
  try {
    const data = await postJson('api/convert-record', {
      record_index: recIdx,
      clear_existing_853_863: document.getElementById('batch-clear853863').checked,
      conversions: rec.fields_866.filter(f => f.a).map(f => ({
        text: f.a,
        captions: settings.captions,
        frequency: settings.frequency,
        numbering_continuity: settings.numbering_continuity,
        remove_866: document.getElementById('batch-remove866').checked,
      })),
      ...settings,
    });
    if (data.kept_existing) {
      // Nothing was converted, and "Converted 0 statements" would say
      // something happened. Say why nothing did.
      showAlert(status, (data.warnings || []).join(' '), 'info');
      return;
    }
    if ((data.left_as_uploaded || []).length) {
      showAlert(status, (data.warnings || []).join(' '), 'warn');
      return;
    }
    const converted = data.previews.filter(p => p.fields_863.length).length;
    const held = data.previews.filter(p => !p.fields_863.length).length;
    const n = data.records_with_decisions || 1;
    showAlert(status,
      `Converted ${converted} statement${converted !== 1 ? 's' : ''}` +
      (held ? `; ${held} left for review.` : '.') +
      ` ${n} record${n !== 1 ? 's' : ''} converted one at a time so far; ` +
      'each stays converted, and "Convert all records" will leave them as you ' +
      'converted them.', held ? 'warn' : 'ok');
    convertedRecords.add(recIdx);
    const own = document.getElementById(`dl-record-${recIdx}`);
    if (own) own.hidden = false;
    document.getElementById('btn-download').style.display = 'inline-flex';
    document.getElementById('btn-download-log').style.display = 'inline-flex';
  } catch (err) {
    showAlert(status, err.message, 'err');
  }
}

// Sources that are not one of the cataloguer's patterns. Kept in step with
// PARSER_SOURCE, UNMATCHED_SOURCE and SKIPPED_SOURCE in marc_serials/bridge.py.
const NOT_A_PATTERN = new Set(['parser', 'unmatched', 'skipped']);

/**
 * What a whole-file conversion did, as figures and a table.
 *
 * This used to be one sentence: "10 records converted — 6 by VOL(YEAR) —
 * VOL(YEAR), 3 by Standard parser, 1 by YEAR:(#‹text›CHRON‹text›), …", every
 * source joined by commas. That is 432 characters on a ten-source file and runs
 * into the thousands on a real library, and the pattern labels contain
 * em-dashes themselves, so there was no telling where one entry ended.
 *
 * The lead figures are the question a cataloguer is actually asking: how much
 * did my own patterns read, and how much fell through to the standard parser?
 * That pairing is also what makes a library the server has quietly lost show up
 * immediately, rather than as a wall of prose nobody reads to the end.
 */
function renderBatchSummary(data) {
  const rows = data.by_source || [];
  const total = rows.reduce((n, s) => n + s.count, 0);
  const byPattern = rows.filter(s => !NOT_A_PATTERN.has(s.source))
                        .reduce((n, s) => n + s.count, 0);
  const bySource = id => (rows.find(s => s.source === id) || {}).count || 0;
  const biggest = rows.reduce((n, s) => Math.max(n, s.count), 0) || 1;

  // The headline counts records; every figure counts statements, so the two
  // never show the same number twice under different words.
  const figure = (n, what, cls = '') => `
    <div class="sum-figure ${cls} ${n ? '' : 'is-zero'}">
      <span class="n">${n}</span><span class="what">${what}</span>
    </div>`;
  const plural = (n, one, many) => `${n === 1 ? one : many}`;

  const figures = [
    figure(total, plural(total, 'statement read', 'statements read')),
    figure(byPattern, 'by your patterns', 'is-patterns'),
    figure(bySource('parser'), 'by the standard parser'),
    data.needs_review ? figure(data.needs_review, 'left for review', 'is-review') : '',
    data.skipped_records
      ? figure(data.skipped_records,
               plural(data.skipped_records, 'record skipped', 'records skipped')) : '',
    data.own_decisions
      ? figure(data.own_decisions, 'kept as you converted them') : '',
    data.kept_existing
      ? figure(data.kept_existing,
               plural(data.kept_existing, 'record already had 863s, kept as it was',
                                          'records already had 863s, kept as they were')) : '',
    bySource('unmatched') ? figure(bySource('unmatched'), 'left as they are') : '',
    bySource('skipped') ? figure(bySource('skipped'), 'skipped by a pattern') : '',
  ].join('');

  const table = rows.map(s => `
    <tr class="${NOT_A_PATTERN.has(s.source) ? 'not-a-pattern' : ''}">
      <td class="sum-label">${escHtml(s.label)}</td>
      <td class="sum-count">${s.count}</td>
      <td class="sum-bar-cell">
        <div class="sum-bar" style="width:${Math.round(100 * s.count / biggest)}%"
             role="img" aria-label="${s.count} of ${total}"></div>
      </td>
    </tr>`).join('');

  // Open when it is short enough to take in at a glance; folded when a long
  // library would otherwise bury the download button.
  const open = rows.length <= 8 ? ' open' : '';
  const breakdown = rows.length ? `
    <details class="mt-2"${open}>
      <summary class="small">Which pattern read what
        — ${rows.length} source${rows.length !== 1 ? 's' : ''}</summary>
      <div class="sum-scroll">
        <table class="sum-table">
          <thead><tr><th>Read by</th><th class="sum-count">Statements</th><th></th></tr></thead>
          <tbody>${table}</tbody>
        </table>
      </div>
    </details>` : '';

  const warnings = [];
  if (!rows.length) {
    warnings.push('Nothing was converted.');
  } else if (!byPattern && library.length) {
    // The shape of the bug that lost a library to an upload: the screen says
    // patterns are confirmed and not one of them read anything.
    warnings.push(`None of your ${library.length} confirmed patterns were used. ` +
      'Check that the library still holds the shapes in this file.');
  }
  if (data.skipped_own_decisions) {
    // Skipping is the stronger instruction, but it must not quietly undo work
    // the cataloguer did by hand: the decision is still held, and clearing the
    // skip puts it back.
    warnings.push(`${data.skipped_own_decisions} record` +
      `${data.skipped_own_decisions !== 1 ? 's you' : ' you'} converted ` +
      'individually are set aside, so those conversions are not in the file. ' +
      'Untick "Skip" on them and convert again to put them back.');
  }
  (data.rejections || []).forEach(r => warnings.push(r));

  return `
    <div class="alert alert-${warnings.length ? 'warn' : 'ok'}">
      <div>
        <strong>${data.records_processed} record${data.records_processed !== 1 ? 's' : ''} converted.</strong>
        ${warnings.map(escHtml).join(' ')}
      </div>
    </div>
    <div class="sum-figures">${figures}</div>
    ${breakdown}`;
}

document.getElementById('btn-batch-all').addEventListener('click', async () => {
  const status = document.getElementById('batch-status');
  status.innerHTML = '<span class="spinner"></span> Converting every record…';
  try {
    const data = await postJson('api/batch-convert', {
      remove_866: document.getElementById('batch-remove866').checked,
      clear_existing_853_863: document.getElementById('batch-clear853863').checked,
      ...conventionPayload(),
    });
    status.innerHTML = renderBatchSummary(data);
    (data.converted_indexes || []).forEach(i => convertedRecords.add(i));
    // A record this run skipped is in the file exactly as it came in, whatever
    // was done to it before, so its own download would hand back an
    // unconverted record. The button goes with it.
    (data.summary || []).filter(row => row.skipped)
                        .forEach(row => convertedRecords.delete(row.index));
    allRecords.forEach((_, i) => {
      const own = document.getElementById(`dl-record-${i}`);
      if (own) own.hidden = !convertedRecords.has(i);
    });
    document.getElementById('btn-download').style.display = 'inline-flex';
    document.getElementById('btn-download-log').style.display = 'inline-flex';
  } catch (err) {
    showAlert(status, err.message, 'err');
  }
});
