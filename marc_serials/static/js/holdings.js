/*
 * Step 1, Holdings: which steps show, uploading the MARC file, and the
 * field the records are identified by.
 *
 * Part of the page (templates/tool.html), which loads these files in order.
 */

// ─────────────────────────────────────────────────────────────────────────
// Steps
// ─────────────────────────────────────────────────────────────────────────

/**
 * Show each step once the one before it has given it something to do.
 *
 * Patterns need statements, from a file or pasted; converting needs a file,
 * whether or not any pattern was confirmed — converting with none is the
 * standard parser, which is a real thing to want and produces exactly what the
 * converter on its own produces.
 */
function revealSteps() {
  const haveStatements = allStatements.length > 0 || pastedStatements().length > 0;
  document.getElementById('step-patterns').hidden = !haveStatements;
  // Convert works on the file, so it is there only while the file is in use.
  document.getElementById('step-convert').hidden  =
    allRecords.length === 0 || sourceMode === 'paste';

  const summary = document.getElementById('convert-summary');
  if (allRecords.length) {
    const n = library.length;
    const fallback = document.getElementById('opt-parser-fallback').checked;
    summary.textContent = `${allRecords.length} record${allRecords.length !== 1 ? 's' : ''} · `
      + (n ? `${n} pattern${n !== 1 ? 's' : ''} confirmed` : 'no patterns confirmed')
      + (!fallback ? ' · nothing else will be converted'
         : document.getElementById('opt-parser-strict').checked
           ? ' · standard parser for the rest, where it reads the whole statement'
           : ' · standard parser for the rest');
  }
}

/** Collapse step 1 to a line once it has a file; "Change" puts it back. */
function showSourceSummary(text, extraHtml = '') {
  const body = document.getElementById('source-body');
  const summary = document.getElementById('source-summary');
  const change = document.getElementById('btn-change-source');
  if (!text) {
    body.hidden = false; summary.hidden = true; change.hidden = true;
    return;
  }
  body.hidden = true;
  summary.hidden = false;
  change.hidden = false;
  summary.innerHTML = `<span class="icon">✓</span> ${escHtml(text)}${extraHtml}`;
}

document.getElementById('btn-change-source').addEventListener('click',
  () => showSourceSummary(null));

// ─────────────────────────────────────────────────────────────────────────
// 1 · Holdings — upload once, both halves use it
// ─────────────────────────────────────────────────────────────────────────

const dropZone  = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
});
dropZone.addEventListener('dragover', e => {
  e.preventDefault(); dropZone.classList.add('dragover');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  if (e.dataTransfer.files.length) uploadMarcFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', e => {
  if (e.target.files.length) uploadMarcFile(e.target.files[0]);
});

async function uploadMarcFile(file) {
  const form = new FormData();
  form.append('file', file);
  dropZone.innerHTML = '<span class="spinner"></span> Reading MARC file…';

  try {
    const res  = await fetch('api/upload-marc', { method: 'POST', body: form });
    const data = await res.json();
    if (data.error) {
      dropZone.innerHTML = `<span class="icon">❌</span>${escHtml(data.error)}`;
      return;
    }
    // Switching back from pasted statements: their patterns go with them.
    if (sourceMode === 'paste') {
      detected = [];
      document.getElementById('patterns-area').innerHTML = '';
    }
    allRecords    = data.records;
    allStatements = data.statements;
    sourceMode    = 'file';
    fileName      = file.name;
    fileDetect    = null;       // a new file: nothing found from it yet
    fileSummary   = `${file.name} — ${data.total} records, ${data.count} holdings statements`;
    showPasteHint();
    renderRecordList(data.records);
    showIdentifierNotice(data);
    recordPreviews.clear();
    reviewed.clear();
    keepSeparate.clear();
    skipRecords.clear();
    convertedRecords.clear();
    document.getElementById('btn-download').style.display = 'none';
    document.getElementById('btn-download-log').style.display = 'none';
    reviewOffset = 0;
    recordIndex.clear();
    // A new file starts unsearched. The Find box used to keep its text across
    // uploads and quietly narrow every filter on the next file -- "1 of 5
    // match" for a file nobody had searched.
    reviewSearch = '';
    document.getElementById('review-search').value = '';
    document.getElementById('btn-search-clear').hidden = true;
    // And unfiltered by pattern: the records it named were the last file's.
    clearPatternFilter(false);
    // Re-read the library from the server rather than trusting what this page
    // read when it loaded. The two used to be able to disagree -- the sidebar
    // showing a hundred confirmed patterns the server had already discarded,
    // and every record then converting with the standard parser -- and a count
    // on screen that conversion does not use is worse than no count at all.
    await loadLibrary();
    reloadReview();
    dropZone.innerHTML = '<span class="icon">📁</span>Drop a MARC file here, or click to browse';
    showSourceSummary(fileSummary);
    revealSteps();
  } catch (err) {
    dropZone.innerHTML = '<span class="icon">❌</span>Upload failed.';
    console.error(err);
  }
}

/**
 * Say when this file carries no identifier, once, rather than drawing an empty
 * slot beside every row.
 *
 * A cataloguer looking at 372 rows with nothing where the number should be
 * cannot tell whether the file lacks the field or the tool has failed to read
 * it. Those want different actions, so the screen says which.
 *
 * Choosing a different field is the next change; for now this names the field
 * looked for, which is what someone needs in order to ask for another.
 */
let identifierSpec       = '';   // the field records are currently found by
let identifierCandidates = [];   // what this file could be found by instead

/**
 * Say what this file is identified by, and offer the alternatives it carries.
 *
 * A file with no 999 $b is the ordinary case for anyone whose ILS is not
 * Alma, and the useful response is not "type a field" -- that asks the
 * cataloguer to guess at a MARC structure they may not have in front of them.
 * The server has read the file and knows which of its fields are on every
 * record, unrepeated and distinct, so the screen offers those with a sample
 * value beside each. "991000485469603731" is recognisable to whoever uses it;
 * "999$b" is not.
 */
function showIdentifierNotice(data) {
  const notice = document.getElementById('identifier-notice');
  if (!notice) return;
  identifierSpec       = data.identifier_field || '';
  identifierCandidates = data.identifier_candidates || [];

  const none    = identifierSpec === '';
  const missing = data.identifier_found === false && (data.total || 0) > 0 && !none;

  notice.hidden = false;
  if (missing) {
    notice.innerHTML = `<div class="alert alert-info">No
      <code>${escHtml(identifierSpec)}</code> in this file, so its records are
      listed without an identifier.
      <button type="button" class="btn btn-ghost btn-sm" onclick="openIdentifierPicker()"
        >Use a different field</button></div>`;
    openIdentifierPicker();
  } else {
    // Findable rather than shouted about: a working identifier needs no alert,
    // but the field it came from should never be a mystery either.
    notice.innerHTML = `<div class="small dim">Records are identified by
      ${none ? 'nothing' : `<code>${escHtml(identifierSpec)}</code>`} ·
      <button type="button" class="btn btn-ghost btn-sm" onclick="openIdentifierPicker()"
        >Change</button></div>`;
  }
}

/** Put the current identifiers onto rows that are already built. */
function paintIdentifiers() {
  document.querySelectorAll('.rec-row').forEach(row => {
    const rec = allRecords[Number(row.dataset.index)];
    const toggle = row.querySelector('.rec-toggle');
    if (!toggle) return;
    let slot = row.querySelector('.rec-id');
    const value = rec && rec.identifier ? rec.identifier : '';
    if (!value) { if (slot) slot.remove(); return; }
    if (!slot) {
      slot = document.createElement('span');
      slot.className = 'rec-id';
      toggle.insertBefore(slot, row.querySelector('.rec-title'));
    }
    slot.textContent = value;
  });
}

function openIdentifierPicker() {
  const picker = document.getElementById('identifier-picker');
  const lead   = document.getElementById('identifier-picker-lead');
  const list   = document.getElementById('identifier-options');
  if (!picker) return;

  // What the list can honestly claim depends on what is in it. Saying "a
  // different value on every record" above a field that repeats one would be
  // the screen telling the cataloguer something the file contradicts.
  const anyUnique = identifierCandidates.some(c => c.unique);
  lead.textContent = !identifierCandidates.length
    ? 'Nothing in this file is on every record with a value of its own, so '
      + 'there is no identifier to suggest. Name a field yourself, or show none.'
    : anyUnique
    ? 'These fields are on every record in this file and appear once each. '
      + 'The ones marked below share a value between records, so they would '
      + 'label two rows the same.'
    : 'Nothing in this file has a value of its own on every record. These are '
      + 'the closest, and each would label some rows the same.';

  list.innerHTML = identifierCandidates.map(c => `
    <button type="button" class="id-option${c.spec === identifierSpec ? ' chosen' : ''}${
      c.unique ? '' : ' not-unique'}"
            onclick="chooseIdentifier('${escHtml(c.spec)}')">
      <span class="spec">${escHtml(c.spec)}</span>
      <span class="sample">${escHtml(c.sample || '')}</span>
      <span class="tally">on ${c.present} of ${c.total} · ${c.distinct} different${
        c.unique ? '' : ' — some records share one'}</span>
    </button>`).join('');

  document.getElementById('identifier-custom').value =
    identifierCandidates.some(c => c.spec === identifierSpec) ? '' : identifierSpec;
  document.getElementById('identifier-error').hidden = true;
  picker.hidden = false;
}

/** Apply a field and repaint the rows, without re-uploading the file. */
async function chooseIdentifier(spec) {
  const err = document.getElementById('identifier-error');
  // Cleared first: a message about the last thing typed must not outlive it
  // and appear to be about this one.
  err.hidden = true;
  err.innerHTML = '';
  try {
    const res  = await fetch('api/identifier', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spec }),
    });
    const data = await res.json();
    if (data.error) {
      err.innerHTML = `<div class="alert alert-warn">${escHtml(data.error)}</div>`;
      err.hidden = false;
      return;
    }
    identifierSpec = data.spec || '';
    (data.identifiers || []).forEach(row => {
      if (allRecords[row.index]) allRecords[row.index].identifier = row.identifier;
    });
    // Updated in place rather than by re-rendering the list. renderRecordList()
    // rebuilds every row from scratch, which would silently clear the reviewed,
    // skip and keep-separate boxes a cataloguer had already ticked -- a far
    // worse thing to do than the one they asked for.
    paintIdentifiers();
    showIdentifierNotice({
      identifier_field: identifierSpec,
      identifier_found: data.found,
      identifier_candidates: identifierCandidates,
      total: allRecords.length,
    });
    document.getElementById('identifier-picker').hidden = true;
    if (allRecords.length) loadReviewPage();
  } catch (e) {
    err.innerHTML = '<div class="alert alert-warn">Could not change the field.</div>';
    err.hidden = false;
    console.error(e);
  }
}

document.getElementById('btn-identifier-use').addEventListener('click', () =>
  chooseIdentifier(document.getElementById('identifier-custom').value.trim()));
document.getElementById('btn-identifier-none').addEventListener('click', () =>
  chooseIdentifier(''));
document.getElementById('btn-identifier-close').addEventListener('click', () => {
  document.getElementById('identifier-picker').hidden = true;
});
