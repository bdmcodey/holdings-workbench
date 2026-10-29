/*
 * The record list in step 3: each record's line and its pills, the notes
 * above the list, the filter chips, Find, and the pages.
 *
 * Part of the page (templates/tool.html), which loads these files in order.
 */

function renderRecordList(records) {
  const box = document.getElementById('records-accordion');
  box.innerHTML = records.map((rec, i) => `
    <div class="rec-row" data-index="${i}">
      <button type="button" class="rec-toggle" onclick="selectRecord(${i})" aria-expanded="false">
        <span class="rec-caret" aria-hidden="true">▸</span>
        ${rec.identifier ? `<span class="rec-id">${escHtml(rec.identifier)}</span>` : ''}
        <span class="rec-title" id="rec-title-${i}">${escHtml(rec.title)}</span>
        <span class="rec-status"></span>
        <span class="rec-meta">${escHtml(rec.issn || '–')} · ${escHtml(rec.location || 'no location')}</span>
      </button>
      <div class="rec-detail" hidden></div>
      <div class="rec-foot">
      <!-- A label each: one label round all three named only the first, as
           "Reviewed Keep patterns separate Skip", and the other two not at all. -->
      <div class="rec-review">
        <label><input type="checkbox" class="rec-reviewed" data-index="${i}" aria-describedby="rec-title-${i}" /> Reviewed</label>
        <span class="rec-sep" aria-hidden="true"></span>
        <label title="Give each pattern its own 853, even where one records less detail than another"><input
          type="checkbox" class="rec-keep-separate" data-index="${i}" aria-describedby="rec-title-${i}" /> Keep patterns separate</label>
        <span class="rec-sep" aria-hidden="true"></span>
        <label title="Leave this record exactly as it is: nothing converted, no 866 removed, existing 853/863 untouched"><input
          type="checkbox" class="rec-skip" data-index="${i}" aria-describedby="rec-title-${i}" /> Skip</label>
      </div>
      <span class="small dim rec-leaving" hidden>No longer matches this filter: it stays
        open while you work on it, and leaves the list when you close it.</span>
      <button type="button" class="btn btn-ghost btn-sm rec-close" onclick="closeRecord(${i})"
              aria-label="Close ${escHtml(rec.title)}"
              title="Fold this record back to its line, and bring it to the top of the screen">▴ Close</button>
      </div>
    </div>`).join('');

  box.querySelectorAll('.rec-keep-separate').forEach(el =>
    el.addEventListener('change', async e => {
      const idx = Number(e.target.dataset.index);
      e.target.checked ? keepSeparate.add(idx) : keepSeparate.delete(idx);
      // The record's whole conversion changes, so re-preview it.
      recordPreviews.delete(idx);
      await reloadReview();
      const row = document.querySelector(`.rec-row[data-index="${idx}"]`);
      if (row && !row.querySelector('.rec-detail').hidden) await renderRecordDetail(idx);
    }));

  box.querySelectorAll('.rec-skip').forEach(el =>
    el.addEventListener('change', async e => {
      const idx = Number(e.target.dataset.index);
      e.target.checked ? skipRecords.add(idx) : skipRecords.delete(idx);
      document.querySelector(`.rec-row[data-index="${idx}"]`)
              .classList.toggle('skipped', e.target.checked);
      // What the record would produce has changed to "nothing", or back.
      recordPreviews.delete(idx);
      await reloadReview();
      const row = document.querySelector(`.rec-row[data-index="${idx}"]`);
      if (row && !row.querySelector('.rec-detail').hidden) await renderRecordDetail(idx);
      // Nothing opens and the cursor stays put: skipping several records in a
      // row should be one click each. The note box is in the record's detail,
      // and the Skipped filter gathers them for writing reasons afterwards.
    }));

  box.querySelectorAll('.rec-reviewed').forEach(box_ =>
    box_.addEventListener('change', e => {
      const idx = Number(e.target.dataset.index);
      e.target.checked ? reviewed.add(idx) : reviewed.delete(idx);
      document.querySelector(`.rec-row[data-index="${idx}"]`)
              .classList.toggle('reviewed', e.target.checked);
      if (reviewFilter === 'unreviewed') loadReviewPage();
      else applyReviewFilter();
    }));
}

/**
 * What every record in the file would produce, in counts rather than fields.
 *
 * The filters and the row status run on this, so they answer for the whole
 * file. Previews are still fetched a page at a time, because the fields are
 * the bulky part and only the rows on screen need them.
 */
async function loadReviewIndex() {
  const box = document.getElementById('review-error');
  try {
    const data = await postJson('api/review-index', conventionPayload());
    recordIndex = new Map(data.records.map(row => [row.index, row]));
    showLeaderNotices(data);
    refreshPatternRecordCounts();
    box.hidden = true;
  } catch (err) {
    console.error(err);
    // Not only the console. With no index every filter but All matches
    // nothing, and "0 match" reads as a finding rather than a failure.
    box.innerHTML = `<div class="alert alert-err">The records could not be
      checked, so the filters and counts below cannot be trusted
      (${escHtml(err.message)}). Try uploading the file again; if it keeps
      happening, the server's terminal window says why.</div>`;
    box.hidden = false;
  }
}

/**
 * The encoding level of the file, said once above the list.
 *
 * This used to be a marker on every affected row, and on a real 372-record
 * export that was 371 markers all saying the same thing -- which is how a
 * cataloguer came to report it as taking away the value it was supposed to
 * provide. The count is the useful part, and whoever acts on it acts on it in
 * their ILS in one operation rather than row by row.
 *
 * The rows are still reachable, through the "Encoding level" chip, for the
 * file where only a handful disagree and finding those is the point.
 */
//
// Each note can be hidden, and stays hidden in this browser for every file.
// On a file migrated with default Leader values the same note comes back on
// every upload saying the same thing, and a note read once is noise the
// second time. Hidden is not gone: it folds to one line that keeps the count
// and a Show button, so nothing the tool found disappears from the screen.
const HIDDEN_NOTICES_KEY = 'mst-hidden-notices';
let hiddenNotices = new Set();
try {
  const saved = JSON.parse(localStorage.getItem(HIDDEN_NOTICES_KEY) || '[]');
  if (Array.isArray(saved)) hiddenNotices = new Set(saved);
} catch (e) {}
// The notes are redrawn on every filter change, not only on upload, so the
// last figures are kept to redraw from when one is hidden or shown.
let lastLeaderData = null;

function showLeaderNotices(data) {
  lastLeaderData = data;
  const box = document.getElementById('encoding-level-notice');
  if (!box) return;
  const encoding = data.encoding_level || {};
  const notes = [
    { key: 'encoding-level', name: 'Encoding level in the Leader',
      count: encoding.records, body: encodingLevelLine(encoding) },
    { key: 'beyond-level', name: 'Holdings beyond the level you are recording at',
      count: data.beyond_level,
      body: beyondLevelLine(data.beyond_level, data.with_holdings,
                            data.declared_level) },
    { key: 'single-part', name: 'Leader/06 coded as single-part item',
      count: data.single_part, body: singlePartLine(data.single_part, data.total) },
  ].filter(note => note.body);

  box.innerHTML = notes.map((note, i) => hiddenNotices.has(note.key)
    ? `<div class="notice-hidden small dim${i ? ' mt-1' : ''}">
         Hidden: ${escHtml(note.name)} — ${note.count}
         record${note.count !== 1 ? 's' : ''}.
         <button type="button" class="btn btn-ghost btn-sm"
                 aria-label="Show the note: ${escHtml(note.name)}"
                 data-show-notice="${note.key}">Show</button></div>`
    : `<div class="alert alert-info${i ? ' mt-2' : ''}">${note.body}
         <button type="button" class="btn btn-ghost btn-sm"
                 data-hide-notice="${note.key}"
                 aria-label="Hide the note: ${escHtml(note.name)}"
                 title="Folds this note to one line, in this browser, for every file you upload"
                 >Hide</button></div>`).join('');
  box.hidden = notes.length === 0;
}

function setNoticeHidden(key, hide) {
  hide ? hiddenNotices.add(key) : hiddenNotices.delete(key);
  try {
    localStorage.setItem(HIDDEN_NOTICES_KEY, JSON.stringify([...hiddenNotices]));
  } catch (e) {}
  if (lastLeaderData) showLeaderNotices(lastLeaderData);
}

document.getElementById('encoding-level-notice').addEventListener('click', e => {
  const hide = e.target.closest('[data-hide-notice]');
  const show = e.target.closest('[data-show-notice]');
  if (hide) setNoticeHidden(hide.dataset.hideNotice, true);
  if (show) setNoticeHidden(show.dataset.showNotice, false);
});

/**
 * Leader/06 says single-part item; the holdings say otherwise.
 *
 * Counted rather than marked, like the encoding level and for the same
 * reason: on a file migrated from an ILS that kept no MARC holdings this is
 * true of almost every record, so it describes the file.
 *
 * What it should be instead is left alone. "v" is multipart item holdings and
 * "y" is serial item holdings, and telling a finite set of volumes from a
 * continuing publication is a cataloguing judgement no holdings statement
 * settles. The line says "x" cannot be right, not which to use.
 */
function singlePartLine(count, total) {
  if (!count) return '';
  const many = count !== 1;
  return `
    ${count} of ${total} record${many ? 's are' : ' is'} coded in the Leader as
    single-part item holdings (<code>06 = x</code>), while the holdings
    ${many ? 'name' : 'names'} a volume, an issue, or a span of more than one
    part. A single-part item is complete in one piece, so that coding cannot be
    right for ${many ? 'them' : 'it'} — but whether ${many ? 'they are' : 'it is'}
    a serial (<code>y</code>) or a multipart item (<code>v</code>) is a
    cataloguing decision this tool does not make. The Leader is never changed.`;
}

/**
 * Holdings that go past the level being recorded at.
 *
 * Level 3 is summary -- "only the highest levels (first-order designators)",
 * Z39.71 4.3 -- and an 863 carrying a volume, an issue, a year and a month is
 * not that. It is the one encoding-level question that genuinely varies from
 * record to record, and it was a marker beside each affected row until a
 * cataloguer pointed out that 242 of 371 markers is not a signal.
 *
 * That is the third time the same shape has come up, so the rule is applied
 * rather than rediscovered: a fact true of most of a file is a property of
 * the file. Stated once, with the records a click away.
 */
function beyondLevelLine(count, total, declared) {
  if (!count) return '';
  const many = count !== 1;
  return `
    You are recording at level ${escHtml(declared || '3')}, which is summary
    holdings — the first level of enumeration and chronology only.
    ${count} of ${total} record${many ? 's' : ''} produced fields that go
    further than that, so ${many ? 'their' : 'its'} 863s claim less than
    ${many ? 'they' : 'it'} carr${many ? 'y' : 'ies'}. Record at level 4 if
    these holdings are detailed.
    <button type="button" class="btn btn-ghost btn-sm"
            onclick="filterTo('encoding')">Show them</button>`;
}

function encodingLevelLine(summary) {
  if (!summary || !summary.records) return '';

  const levels = Object.entries(summary.levels || {})
    .map(([value, n]) => `${n} at <code>${escHtml(value)}</code>`)
    .join(', ');
  const many = summary.records !== 1;
  return `
    ${summary.records} of ${summary.total} record${many ? 's' : ''}
    declare${many ? '' : 's'} an encoding level in the Leader that is not the
    level you are recording at (${levels}, against
    <code>${escHtml(summary.declared)}</code>).
    The Leader is never changed by this tool — it is your statement about your
    own holdings. Set it in your catalogue if these records should say what
    they now carry, or record at that level instead.
    <button type="button" class="btn btn-ghost btn-sm"
            onclick="filterTo('encoding')">Show them</button>`;
}

/** Switch the review filter from somewhere other than a chip. */
function filterTo(name) {
  const chip = document.querySelector(`.filter-row .chip[data-filter="${name}"]`);
  if (chip) chip.click();
}

/** The records the current filter shows, in file order. */
function filteredIndices() {
  // Search narrows the chosen filter rather than replacing it, and both are
  // applied here rather than at the two call sites, so the pager, the count
  // line and the rows on screen can never disagree about what matches.
  return allRecords
    .map((_, i) => i)
    .filter(i => recordMatchesFilter(recordIndex.get(i), i)
              && recordMatchesSearch(i));
}

/**
 * Fetch previews for the page of records currently on screen.
 *
 * The page is a slice of what the *filter* shows, not of the file: with a
 * filter on, records 1-50 of the file are not the first fifty a cataloguer is
 * looking at, and paging through them would mostly turn up hidden rows.
 */
async function loadReviewPage() {
  const bar = document.getElementById('review-bar');
  try {
    const matching = filteredIndices();
    if (reviewOffset >= matching.length) reviewOffset = 0;
    const page = matching.slice(reviewOffset, reviewOffset + reviewPageLimit());

    for (let at = 0; at < page.length; at += PREVIEW_BATCH) {
      const data = await postJson('api/preview-records', {
        indices: page.slice(at, at + PREVIEW_BATCH), ...conventionPayload() });
      data.records.forEach(entry => recordPreviews.set(entry.index, entry));
    }
    bar.hidden = false;
    paintRecordStatus();
    applyReviewFilter();
    renderPager({ total: matching.length, offset: reviewOffset, limit: reviewPageLimit() });
  } catch (err) {
    bar.hidden = true;
    console.error(err);
  }
}

/** Re-read the index, then the page that sits on top of it. */
async function reloadReview() {
  await loadReviewIndex();
  await loadReviewPage();
}

/** What each row says about itself before it is opened. */
function paintRecordStatus() {
  document.querySelectorAll('.rec-row').forEach(row => {
    const entry = recordIndex.get(Number(row.dataset.index));
    const slot = row.querySelector('.rec-status');
    paintStatusPills(slot, entry);
    // After whatever else the row says: a note of the cataloguer's own.
    if (entry && entry.note) {
      slot.insertAdjacentHTML('beforeend',
        ` <span class="pill" title="${escHtml(entry.note)}">note</span>`);
    }
  });
}

/** [tag, how many] for each field a record's held statements belong in. */
function elsewhereCounts(tags) {
  const counts = new Map();
  (tags || []).forEach(tag => counts.set(tag, (counts.get(tag) || 0) + 1));
  return [...counts.entries()].sort();
}

function paintStatusPills(slot, entry) {
  {
    if (!entry) { slot.innerHTML = ''; return; }
    if (entry.skipped) {
      slot.innerHTML = '<span class="pill skipped-pill">skipped</span>';
      return;
    }
    if (entry.unreadable) {
      slot.innerHTML = '<span class="pill decide">could not check</span>';
      return;
    }
    if (entry.kept_existing) {
      slot.innerHTML = `<span class="pill"
        title="Already has ${entry.existing_863} 863 field${entry.existing_863 !== 1 ? 's' : ''}; left as it is">has 863s · kept</span>`
        + ((entry.record_notes || []).length ? ' <span class="pill decide">to check</span>' : '')
        + ((entry.edited || []).length ? ' <span class="pill">866 edited</span>' : '');
      return;
    }
    if (!entry.has_866) {
      slot.innerHTML = '<span class="pill">no 866</span>';
      return;
    }
    const bits = [];
    if ((entry.left_as_uploaded || []).length) {
      slot.innerHTML = `<span class="pill attention"
        title="Converting it would leave something out to fit MARC, and Conversion settings say to leave such a record as uploaded">left as uploaded</span>`;
      return;
    }
    if (entry.converted) bits.push(`<span class="pill has-866">${entry.converted} converted</span>`);
    if (entry.held) bits.push(`<span class="pill attention">${entry.held} held</span>`);
    elsewhereCounts(entry.elsewhere).forEach(([tag, n]) => bits.push(
      `<span class="pill elsewhere" title="${n === 1 ? 'A statement that reads' : 'Statements that read'} as ${
        tag === '868' ? 'an index' : 'a supplement'}: not converted, and ${n === 1 ? 'belongs' : 'belong'} in ${tag}">${
        n} belong${n === 1 ? 's' : ''} in ${tag}</span>`));
    if (entry.flagged) bits.push(`<span class="pill attention">${entry.flagged} to check</span>`);
    if (entry.left_out) bits.push(`<span class="pill leftout"
      title="Converted, with a value read and left out because MARC has no place for it">${entry.left_out} left out</span>`);
    if ((entry.record_notes || []).length) bits.push('<span class="pill decide">853 to check</span>');
    if ((entry.edited || []).length) bits.push('<span class="pill">866 edited</span>');
    if (Object.keys(entry.record_853 || {}).length) bits.push('<span class="pill">853 set</span>');
    // No marker for the encoding level. Recording at level 3 against a file
    // of detailed holdings marked 242 of 371 rows, which is the third time
    // this shape has come up: a majority is not a signal, it is a property of
    // the file, and it belongs in a line above the list where it can be read
    // once and acted on in the catalogue. The records are still gathered by
    // the "Leader & level" chip for the file where only a handful disagree.
    slot.innerHTML = bits.join(' ');
  }
}

/**
 * Whether a record answers what is typed in the Find box.
 *
 * Deliberately not just the identifier. A holdings record carries no 245, so
 * on a real file every row reads "Record 412" and the identifier is the only
 * thing that tells two apart -- but the cataloguer who remembers a statement
 * rather than a number is the same cataloguer, and everything here is already
 * in the browser from the upload. Searching the file costs nothing extra.
 *
 * Matched case-insensitively, as a substring: an MMS ID is long enough that
 * nobody types it whole, and the last six digits should find it.
 */
function recordMatchesSearch(index) {
  if (!reviewSearch) return true;
  const rec = allRecords[index];
  if (!rec) return false;
  const hay = [
    rec.identifier, rec.title, rec.issn, rec.location,
    ...(rec.fields_866 || []).map(f => f.a || ''),
  ].join(' ').toLowerCase();
  return hay.includes(reviewSearch);
}

function recordMatchesFilter(entry, index) {
  // Nothing known about this record yet. It cannot be said to match, and
  // saying it does is the bug this replaced: previews were loaded a page at a
  // time, every record past the first page had no entry, and so every filter
  // showed the rest of the file alongside its actual matches.
  if (!entry) return reviewFilter === 'all';
  switch (reviewFilter) {
    // No longer includes the encoding level. On a real file every record's
    // Leader/17 disagreed with the declared level, so 371 of 372 records
    // landed here and the filter stopped meaning anything. Encoding level has
    // a chip of its own now, and "Needs attention" is about conversion again.
    // Skipping a record is the cataloguer taking it in hand, so it no longer
    // needs attention here. Held and flagged counts drop to 0 on a skip by
    // themselves -- a skipped record is not converted -- but record_notes are
    // about the 853s already on the record and survive it, which left records
    // with an 853 warning under this filter after they were skipped (0.24.2).
    // The notes still show when the record is opened.
    case 'held':       return !entry.skipped
                             && (entry.held > 0 || entry.flagged > 0
                                 || (entry.elsewhere || []).length > 0
                                 || (entry.left_as_uploaded || []).length > 0
                                 || (entry.record_notes || []).length > 0);
    case 'leftout':    return entry.left_out > 0
                             || (entry.left_as_uploaded || []).length > 0;
    case 'encoding':   return !!entry.leader_note || !!entry.leader_mismatch
                             || !!entry.single_part;
    case 'pattern':    return entry.sources.some(
                        sc => sc !== 'parser' && sc !== 'unmatched' && sc !== 'skipped');
    case 'parser':     return entry.sources.includes('parser');
    case 'unreviewed': return !reviewed.has(index);
    case 'skipped':    return skipRecords.has(index);
    case 'one-pattern':
      if (!patternFilter) return false;
      return patternFilter.mode === 'converted'
        ? (entry.sources || []).includes(patternFilter.id)
        : patternFilter.indexes.has(index);
    default:           return true;
  }
}

function applyReviewFilter() {
  // Show the page, not everything the filter matches.
  //
  // renderRecordList() builds a row for every record in the file once, and
  // this decided which to show from the filter alone -- so a 320-record file
  // with no filter showed all 320 rows while the pager underneath said
  // "records 1-50 of 320". The pager was real; it governed which previews
  // were fetched. It just had nothing to do with what was on screen.
  const matching = filteredIndices();
  const onPage = new Set(matching.slice(reviewOffset, reviewOffset + reviewPageLimit()));

  // A record open on screen stays, even once it no longer matches: fixing it,
  // skipping it or ticking Reviewed used to take it off the list under the
  // cataloguer, mid-task, and everything below jumped up. It leaves when it
  // is closed, and says so meanwhile. Moving to another filter, search or
  // page closes what is open first (closeOpenRecords), so this keeps only
  // the record being worked on.
  document.querySelectorAll('.rec-row').forEach(row => {
    const on = onPage.has(Number(row.dataset.index));
    const open = row.classList.contains('open');
    row.hidden = !on && !open;
    const leaving = row.querySelector('.rec-leaving');
    if (leaving) leaving.hidden = on || !open;
  });

  const total = document.querySelectorAll('.rec-row').length;
  const done = [...reviewed].filter(i => i < allRecords.length).length;
  const set_aside = [...skipRecords].filter(i => i < allRecords.length).length;
  // "shown" used to mean the number of visible rows, which with a page of ten
  // is only ever ten and says nothing. What a cataloguer wants to know is how
  // much of the file the filter is showing them; the pager says where in it
  // they are.
  document.getElementById('review-count').textContent =
    `${matching.length} of ${total} match · ${done} of ${allRecords.length} reviewed`
    + (set_aside ? ` · ${set_aside} skipped` : '');

  // An empty list under a filter chip explains itself; an empty list under a
  // search box looks like the search is broken. Say which it is.
  const empty = document.getElementById('review-empty');
  if (empty) {
    const nothing = matching.length === 0 && allRecords.length > 0;
    empty.hidden = !nothing;
    if (nothing) {
      empty.innerHTML = reviewSearch
        ? `<div class="alert alert-info">Nothing in this file matches
           "${escHtml(reviewSearch)}"${reviewFilter !== 'all'
             ? ' under the filter you have selected' : ''}.</div>`
        : '<div class="alert alert-info">No records match this filter.</div>';
    }
  }
}

/**
 * The pager under the patterns still wanting a decision.
 *
 * Hidden unless there is more than one page of them, so a cataloguer whose file
 * asks for three decisions never sees a control for paging three cards.
 */
function renderPatternPager(total) {
  const pager = document.getElementById('pattern-pager');
  if (!pager) return;
  const more = total > PATTERN_PAGE;
  pager.hidden = !more;
  if (!more) return;
  const last = Math.min(patternOffset + PATTERN_PAGE, total);
  document.getElementById('patt-page-label').textContent =
    `patterns ${patternOffset + 1}–${last} of ${total} still wanting an answer`;
  document.getElementById('btn-patt-prev').disabled = patternOffset === 0;
  document.getElementById('btn-patt-next').disabled = last >= total;
}


function renderPager(data) {
  const pager = document.getElementById('review-pager');
  const more = data.total > data.limit;
  pager.hidden = !more;
  if (!more) return;
  const last = Math.min(data.offset + data.limit, data.total);
  document.getElementById('page-label').textContent =
    (reviewFilter === 'all' ? `records ${data.offset + 1}–${last} of ${data.total}`
                            : `showing ${data.offset + 1}–${last} of ${data.total} matching`);
  document.getElementById('btn-page-prev').disabled = data.offset === 0;
  document.getElementById('btn-page-next').disabled = last >= data.total;
}

/**
 * The Find box.
 *
 * Deliberately not reloadReview(): the per-record counts the filters read do
 * not depend on what is typed here, so re-fetching the whole index on every
 * keystroke would be a request per character to learn nothing new. The page of
 * previews does change, because the page is a slice of what matches, and
 * loadReviewPage() is exactly that much work.
 *
 * Debounced because a cataloguer pasting an MMS ID types eighteen characters,
 * and each one would otherwise ask the server for a page nobody will see.
 */
(function () {
  const box   = document.getElementById('review-search');
  const clear = document.getElementById('btn-search-clear');
  let timer   = null;

  function apply() {
    const next = box.value.trim().toLowerCase();
    if (next === reviewSearch) return;
    reviewSearch = next;
    clear.hidden = !next;
    // A narrower list means the first page of it, not wherever the last one
    // had got to -- the same reason the filter chips reset the offset.
    closeOpenRecords();
    reviewOffset = 0;
    if (allRecords.length) loadReviewPage().then(() =>
      announce(document.getElementById('review-count').textContent));
  }

  box.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(apply, 180);
  });
  // Enter should not wait out the debounce, and should not submit anything.
  box.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); clearTimeout(timer); apply(); }
  });
  clear.addEventListener('click', () => {
    box.value = '';
    clearTimeout(timer);
    apply();
    box.focus();
  });
})();

document.querySelectorAll('.filter-row .chip').forEach(chip =>
  chip.addEventListener('click', () => {
    document.querySelectorAll('.filter-row .chip').forEach(c => {
      c.classList.toggle('active', c === chip);
      c.setAttribute('aria-pressed', String(c === chip));
    });
    reviewFilter = chip.dataset.filter;
    closeOpenRecords();
    // The pages are slices of what the filter shows, so a new filter means new
    // pages -- and the first of them, not wherever the last filter had got to.
    reviewOffset = 0;
    recordIndex.clear();
    reloadReview().then(() =>
      announce(document.getElementById('review-count').textContent));
  }));
