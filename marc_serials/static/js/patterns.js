/*
 * Step 2, Patterns: pasted statements, Find patterns, confirming what can be
 * read on its own, the folds and counts, and building each card.
 *
 * Part of the page (templates/tool.html), which loads these files in order.
 */

// ─────────────────────────────────────────────────────────────────────────
// 2 · Patterns
// ─────────────────────────────────────────────────────────────────────────

document.getElementById('btn-use-text').addEventListener('click', () => {
  if (!pastedStatements().length) {
    showAlert(document.getElementById('detect-error'),
      'Type or paste some holdings statements first.', 'warn');
    return;
  }
  if (sourceMode === 'file') setFileAside();
  sourceMode = 'paste';
  showPasteHint();
  showPastedSummary();
  revealSteps();
  document.getElementById('step-patterns').scrollIntoView({ behavior: 'smooth', block: 'start' });
});

function showPastedSummary() {
  const n = pastedStatements().length;
  showSourceSummary(`${n} pasted statement${n !== 1 ? 's' : ''}`,
    allRecords.length ? fileAsideHtml() : '');
}

/**
 * Switch from a file to pasted statements. The file stays loaded -- its
 * records, what has been decided on them, the patterns found from it -- but out
 * of play: Convert is hidden and its patterns come off the page. "Back to" the
 * file puts all of it back; uploading replaces it.
 */
function setFileAside() {
  clearPatternFilter(false);
  detected = [];
  document.getElementById('patterns-area').innerHTML = '';
}

/** Switch back from pasted statements to the file set aside. */
function useFileAgain() {
  sourceMode = 'file';
  if (fileDetect) {
    detected = fileDetect.groups;
    patternOffset = 0;
    renderPatterns(fileDetect);
    setPatternsCollapsed(!partitionGroups(fileDetect.groups).open.length);
  } else {
    detected = [];
    document.getElementById('patterns-area').innerHTML = '';
  }
  showPasteHint();
  showSourceSummary(fileSummary);
  revealSteps();
}

/** The file set aside, named, with the way back to it. */
function fileAsideHtml() {
  return ` · <span class="dim">${escHtml(fileName)} set aside</span>
    <button type="button" class="btn btn-ghost btn-sm"
            onclick="useFileAgain()">Back to ${escHtml(fileName)}</button>`;
}

/**
 * What the text box can do about the file. Typing while the file is in use
 * changes nothing until the switch is asked for, so say how to ask; while
 * pasted statements are in use, offer the file back.
 */
function showPasteHint() {
  const hint = document.getElementById('paste-hint');
  const back = document.getElementById('btn-use-file');
  const typed = !!document.getElementById('stmt-input').value.trim();
  const inUse = sourceMode === 'file' && allRecords.length > 0;
  hint.hidden = !(inUse && typed);
  if (!hint.hidden) {
    hint.innerHTML = `<strong>${escHtml(fileName)}</strong> is loaded, so these
      statements are not being used. <strong>Use these statements</strong>
      switches to them and sets the file aside, to come back to with one click.`;
  }
  back.hidden = !(sourceMode === 'paste' && allRecords.length > 0);
  back.textContent = `Back to ${fileName}`;
}

document.getElementById('stmt-input').addEventListener('input', showPasteHint);
document.getElementById('btn-use-file').addEventListener('click', useFileAgain);

document.getElementById('btn-detect').addEventListener('click', runDetect);

async function runDetect({ keepFold = false } = {}) {
  const statements = statementsForDetection();
  const errBox = document.getElementById('detect-error');
  errBox.innerHTML = '';

  if (!statements.length) {
    showAlert(errBox, 'Upload a MARC file or paste some statements first.', 'warn');
    return;
  }

  const label = document.getElementById('detect-label');
  label.innerHTML = '<span class="spinner"></span> Finding patterns…';
  lastSplit = document.getElementById('opt-split').checked;

  try {
    const data = await postJson('api/detect', {
      statements,
      split_multi_range: lastSplit,
      // Pasted statements belong to no record, even one in the loaded file
      // that happens to read the same.
      pasted: sourceMode === 'paste',
    });
    detected = data.groups;
    if (sourceMode === 'file') fileDetect = data;
    // A new run is a new set of cards, so start at the first page of them
    // rather than wherever the last run had got to.
    patternOffset = 0;
    await autoConfirm(data.groups);
    // Pasted statements have no Convert step: the patterns are all there is
    // to see, and someone trying out a statement wants its pattern and its
    // expression. So a run from the text box shows them open, folds and all.
    const fromPaste = sourceMode === 'paste';
    if (fromPaste) {
      patternFolds.confirmed = patternFolds.readable = patternFolds.complex = true;
    }
    renderPatterns(data);
    // From a file: nothing here asks anything, so fold it and put Convert in
    // view. If something does need deciding, that is the work -- stay open.
    // After an edit or a split the cataloguer is still at work where they
    // were, so the step is left as it is: folding it because the last card
    // that asked something was just fixed took the screen away mid-task.
    if (!keepFold) {
      setPatternsCollapsed(!fromPaste && !partitionGroups(data.groups).open.length);
      const open = partitionGroups(data.groups).open.length;
      const n = data.groups.length;
      announce(`Found ${n} pattern${n !== 1 ? 's' : ''}`
        + (open ? `; ${open} need${open === 1 ? 's' : ''} a decision.` : '; none needs a decision.'));
    }
  } catch (err) {
    showAlert(errBox, err.message, 'err');
  } finally {
    label.textContent = '⟳ Find patterns';
  }
}

/**
 * Confirm every pattern that needs no decision.
 *
 * Match rate is not the filter it looks like: the detector tests each
 * expression against its own cluster, so every group scores 100%. What actually
 * separates a pattern that is ready from one that is not is whether every
 * captured value got a meaning — an unresolved one cannot be stored at all.
 *
 * A pattern that decides the *reading* is never confirmed unasked, however
 * confident its roles look. The standard parser writes nothing for those
 * statements, and it refuses them on purpose: it read part of the wording and
 * could not account for the rest. Confirming such a pattern overrides that
 * refusal and writes holdings on the strength of an inference nobody checked.
 * "v. 19 no. 2 Suppl. (1998)" is the shape that showed this up — the pattern
 * reads it confidently as volume 19, issue 2, and the supplement, which is what
 * the library actually holds, disappears into an ordinary 863.
 *
 * Patterns the cataloguer has removed one at a time are not re-added; taking
 * one out is a decision, and a detection run should not undo it. How many were
 * left out is said on the step, so the library being smaller than expected has
 * a reason on screen.
 */
async function autoConfirm(groups) {
  const readable = groups.filter(g =>
    !g.too_complex &&
    g.regex &&
    g.decides !== 'reading' &&
    // Held whatever is confirmed, so confirming one says nothing true.
    g.decides !== 'elsewhere' &&
    !(g.suggested_roles || []).some(r => r.kind === UNRESOLVED_KIND || r.suggested) &&
    !library.some(p => p.id === patternIdFor(g))
  );
  const ready = readable.filter(g => !dismissed.has(patternIdFor(g)));
  removedHeldBack = readable.length - ready.length;
  if (!ready.length) return;

  const additions = ready.map(g => ({
    id: patternIdFor(g),
    label: g.human_label,
    regex: g.regex,
    roles: g.suggested_roles,
    split: lastSplit,
    priority: g.count,
    notes: (g.examples || [])[0] || '',
  }));

  const data = await saveLibrary(library.concat(additions));
  if (data.rejected && data.rejected.length) {
    showAlert(document.getElementById('library-status'),
      'Some patterns could not be confirmed automatically: ' + data.rejected.join(' '),
      'warn');
  }
}

/**
 * Sort the detected groups by what they still want from the cataloguer.
 *
 * `open` is the work: patterns that ask what a value means, and patterns taken
 * out of the library that could go back in. `confirmed` and `complex` are
 * finished business -- reachable, but not worth the vertical space, which on a
 * large file is measured in thousands of pixels.
 *
 * The index is carried along because a card is built against its position in
 * the detection run, not its position on screen.
 */
function partitionGroups(groups) {
  const parts = { open: [], attention: [], readable: [], elsewhere: [], confirmed: [],
                  skipped: [], complex: [] };
  groups.forEach((group, idx) => {
    const entry = { group, idx };
    const stored = library.find(p => p.id === patternIdFor(group));
    if (stored && stored.skip) parts.skipped.push(entry);
    // Nothing to decide is not nothing to see. A statement that is held, or
    // converts with something to check, was folded away with the patterns
    // that read cleanly -- and pasted statements have no Convert step where it
    // would have turned up. Supplements and indexes keep their own fold.
    // A pattern that still wants an answer is open already, and says so.
    else if (needsALook(group) && !needsAnAnswer(group, stored)) parts.attention.push(entry);
    else if (group.too_complex) parts.complex.push(entry);
    else if (stored) parts.confirmed.push(entry);
    // Asking about a pattern whose answer would change nothing is asking a
    // question with no consequence. The parser reads these statements in full,
    // captions and all, so they are finished business rather than work.
    else if (group.decides === 'nothing') parts.readable.push(entry);
    // Supplements and indexes are held whatever is answered, so there is no
    // question here either -- but they are not "read", so they are not filed
    // with the patterns that are.
    else if (group.decides === 'elsewhere') parts.elsewhere.push(entry);
    else parts.open.push(entry);
  });
  return parts;
}

/**
 * A pattern with a statement to look at here, in step 2.
 *
 * Pasted: one held or to check, on its own reading -- there is no step 3, so
 * this is the only place they show. With a file, those are put right on their
 * records in step 3 (since 0.49.0), and what keeps a card open here is a
 * statement not read at all: the typo that also makes its pattern ask.
 */
function needsALook(group) {
  return group.decides !== 'elsewhere' && (sourceMode === 'paste'
    ? ((group.held || 0) + (group.to_check || 0)) > 0
    : (group.unread || 0) > 0);
}

/** Whether partitionGroups() would file this pattern with the decisions. */
function needsAnAnswer(group, stored) {
  return !stored && !group.too_complex
    && group.decides !== 'nothing' && group.decides !== 'elsewhere';
}

// Which kind of statement the Patterns step is narrowed to: "all", or "held",
// "to_check", "unread" or "left_out". Kept outside the render, like the folds.
let lookFilter = 'all';

// Which folds the cataloguer has opened. Kept outside the render so opening one
// to look at a pattern, then removing another, does not fold it back up.
const patternFolds = {};

/**
 * How many statements, across these patterns, are held, to check, or lose a
 * value, as the standard parser reads each on its own. Skipped patterns are
 * left as they are, so nothing about converting them is true.
 */
function outcomeTotals(entries) {
  const t = { held: 0, to_check: 0, left_out: 0 };
  entries.forEach(({ group }) => {
    t.held += group.held || 0;
    t.to_check += group.to_check || 0;
    t.left_out += group.left_out || 0;
  });
  return t;
}

/**
 * Statements to look at, by kind, with counts, as buttons that narrow the
 * step to the patterns with that kind.
 *
 * Until 0.43.0 this was a sentence under the pattern count and a line on the
 * group of cards, both long and both giving the same totals in prose; a
 * cataloguer found it hard to read and had no way to go straight to, say,
 * the held ones. Skipped patterns are left as they are, so they are not
 * counted.
 */
const LOOK_CHIPS = [
  ['held', 'Held'], ['to_check', 'To check'], ['unread', 'Not read'], ['left_out', 'Left out'],
];

function lookChipsHtml(groups) {
  const counted = groups.filter(g => {
    const stored = library.find(p => p.id === patternIdFor(g));
    return !(stored && stored.skip);
  });
  const chips = LOOK_CHIPS.map(([kind, label]) => {
    const statements = counted.reduce((n, g) => n + (g[kind] || 0), 0);
    const patterns = counted.filter(g => g[kind]).length;
    if (!statements && lookFilter !== kind) return '';
    return `<button type="button" class="chip${lookFilter === kind ? ' active' : ''}"
      data-look="${kind}" aria-pressed="${lookFilter === kind}">${label} — ${statements}
      statement${statements !== 1 ? 's' : ''} in ${patterns} pattern${patterns !== 1 ? 's' : ''}</button>`;
  }).join('');
  if (!chips) return '';
  return `
    <div class="look-row mt-1">
      <span class="small">Statements to look at:</span>
      ${chips}
      ${lookFilter !== 'all' ? `<button type="button" class="chip" data-look="all">Show all patterns</button>` : ''}
    </div>
    <p class="small dim mt-05">Counted by reading each statement on its own. Step 3 reads
      whole records, and can find a little more, such as months changing to seasons
      between two 866s.</p>`;
}

/**
 * With a file: what there is to look at, and that it is looked at in step 3.
 *
 * The chips above stay for pasted statements, which have nowhere else to show
 * them. With a file they narrowed step 2 to cards listing statements to put
 * right, and those are put right on their records now: see lookStep3Html().
 */
function step3LookHtml(groups) {
  const counted = groups.filter(g => {
    const stored = library.find(p => p.id === patternIdFor(g));
    return !(stored && stored.skip);
  });
  const sum = kind => counted.reduce((n, g) => n + (g[kind] || 0), 0);
  const held = sum('held'), check = sum('to_check'), unread = sum('unread'), left = sum('left_out');
  const s = n => n !== 1 ? 's' : '';
  const bits = [];
  if (held || check) {
    bits.push(`<span><strong>${[held ? `${held} held` : '', check ? `${check} to check` : '']
      .filter(Boolean).join(' and ')}</strong>: put right on their records, in step 3.</span>
      <button type="button" class="btn btn-secondary btn-sm"
              onclick="showInStep3('held')">Show Needs attention</button>`);
  }
  if (unread) {
    bits.push(`<span><strong>${unread} not read</strong> by the standard parser: listed on
      ${unread !== 1 ? 'their cards' : 'its card'} below, with Edit.</span>`);
  }
  if (left) {
    bits.push(`<span><strong>${left} statement${s(left)}</strong> with something left out to
      fit MARC.</span>
      <button type="button" class="btn btn-ghost btn-sm"
              onclick="showInStep3('leftout')">Show Something left out</button>`);
  }
  if (!bits.length) return '';
  return `
    <div class="look-step3 mt-1">${bits.map(b => `<div class="look-step3-line">${b}</div>`).join('')}</div>
    <p class="small dim mt-05">Counted by reading each statement on its own. Step 3 reads
      whole records, and can find a little more, such as months changing to seasons
      between two 866s.</p>`;
}

document.addEventListener('click', e => {
  const chip = e.target.closest('[data-look]');
  if (!chip) return;
  lookFilter = chip.dataset.look;
  patternOffset = 0;
  redrawPatterns();
});

/** The pills a card wears for what its statements do on their own. */
function outcomePills(group) {
  const bits = [];
  if (group.unread) bits.push(`<span class="pill decide"
    title="Statements the standard parser can't read at all; the note under the expression says where it stopped">${group.unread} not read</span>`);
  if (group.held) bits.push(`<span class="pill attention"
    title="Statements read and deliberately not converted: nothing is written from them and the 866 stays as it is">${group.held} held</span>`);
  if (group.to_check) bits.push(`<span class="pill attention"
    title="Statements that convert with something to look at before loading">${group.to_check} to check</span>`);
  if (group.left_out) bits.push(`<span class="pill leftout"
    title="Statements that convert with a value read and left out because MARC has no place for it; the preview below says which">${group.left_out} left out</span>`);
  return bits.join('');
}

function buildPatternFold(key, label, entries) {
  const details = document.createElement('details');
  details.className = 'pattern-group';
  details.open = patternFolds[key] ?? key === 'attention';
  details.addEventListener('toggle', () => { patternFolds[key] = details.open; });

  const summary = document.createElement('summary');
  summary.className = 'small';
  // A fold of patterns with nothing to decide can still lose a value; say so
  // on the line that is all a folded group shows. Held and to-check
  // statements are not folded at all, but are said here too should one be.
  // The group of patterns to look at is counted by the buttons at the top.
  const t = key === 'skipped' || key === 'attention' ? {} : outcomeTotals(entries);
  const bits = [];
  if (t.held) bits.push(`${t.held} held`);
  if (t.to_check) bits.push(`${t.to_check} to check`);
  if (t.left_out) {
    bits.push(`${t.left_out} statement${t.left_out !== 1 ? 's' : ''} with something left out to fit MARC`);
  }
  summary.textContent = [label, ...bits].join(' · ');
  details.appendChild(summary);

  const body = document.createElement('div');
  body.className = 'pattern-group-body';
  entries.forEach(({ group, idx }) => body.appendChild(buildPatternCard(group, idx)));
  details.appendChild(body);
  return details;
}

function renderPatterns(data) {
  const area = document.getElementById('patterns-area');
  area.innerHTML = '';
  // The kind chips are for pasted statements; a file has no way to set one.
  if (sourceMode !== 'paste') lookFilter = 'all';

  const parts = partitionGroups(data.groups);
  const undecided = parts.open.length;

  const summary = document.createElement('div');
  summary.className = 'card';
  summary.innerHTML = `
    <div class="card-title">${data.total_patterns} pattern${data.total_patterns !== 1 ? 's' : ''}
      <span class="tag">${data.total_statements} statements</span>
      <button type="button" class="btn btn-ghost btn-sm" id="btn-copy-all-regex"
              title="Copy every expression, one per line: heading, statements, expression"
              >Copy all expressions</button>
      <span class="small dim" id="copy-all-status" role="status"></span></div>
    <p class="small dim">${
      undecided
        ? `Patterns that could be read on their own are already confirmed${
            parts.readable.length
              ? `, and ${parts.readable.length} more ${parts.readable.length === 1
                  ? 'is read' : 'are read'} in full by the standard parser`
              : ''}.
           <strong>${undecided}</strong> still ${undecided === 1 ? 'wants' : 'want'}
           an answer — ${openBreakdown(parts.open)}.`
        : `Nothing is waiting on you${
            parts.readable.length
              ? ': the confirmed patterns and the standard parser between them read every statement'
              : ' — all patterns are confirmed and will be used when you convert'}.`
    }</p>
    ${removedHeldBack ? `<p class="small dim">${removedHeldBack} pattern${
      removedHeldBack !== 1 ? 's' : ''} you removed from the library ${
      removedHeldBack !== 1 ? 'were' : 'was'} not confirmed again. Confirm on a card brings
      one back; Clear, in the library, starts over.</p>` : ''}
    ${sourceMode === 'paste' ? lookChipsHtml(data.groups) : step3LookHtml(data.groups)}
    ${flavourChooserHtml()}`;
  area.appendChild(summary);
  paintFlavourAlert();

  // Narrowed to one kind: every pattern with a statement of it, unfolded,
  // each listing only those statements.
  if (lookFilter !== 'all') {
    const matching = data.groups.map((group, idx) => ({ group, idx }))
      .filter(({ group }) => {
        const stored = library.find(p => p.id === patternIdFor(group));
        return !(stored && stored.skip) && group[lookFilter];
      });
    const label = Object.fromEntries(LOOK_CHIPS)[lookFilter].toLowerCase();
    const note = document.createElement('p');
    note.className = 'small dim mt-2';
    note.textContent = matching.length
      ? `${matching.length} pattern${matching.length !== 1 ? 's have' : ' has'} statements ${
          lookFilter === 'unread' ? 'not read' : label}. "Show all patterns" goes back to all of them.`
      : `No statements ${lookFilter === 'unread' ? 'not read' : label} now.`;
    area.appendChild(note);
    matching.forEach(({ group, idx }) => area.appendChild(buildPatternCard(group, idx)));
    renderPatternPager(0);
    document.getElementById('btn-toggle-patterns').hidden = false;
    refreshPatternsSummary();
    return;
  }

  // A page of the cards still wanting a decision.
  //
  // Only these are paged. The four folds below hold the patterns with nothing
  // to decide and are collapsed already, so paging them would hide what is
  // hidden. On the test collection this changes nothing -- nine open cards fit
  // in one page and the pager stays hidden -- but a file with more variety than
  // the corpus can put dozens of decisions on one screen.
  if (patternOffset >= parts.open.length) patternOffset = 0;
  const openPage = parts.open.slice(patternOffset, patternOffset + PATTERN_PAGE);
  openPage.forEach(({ group, idx }) => area.appendChild(buildPatternCard(group, idx)));
  renderPatternPager(parts.open.length);

  // What folding used to hide, so open until the cataloguer folds it: one
  // file measured 19 of these against 5 cards asking for a decision, which is
  // too many to lay out loose, and too many to tuck away.
  if (parts.attention.length) {
    const n = parts.attention.length;
    area.appendChild(buildPatternFold('attention',
      `${n} pattern${n !== 1 ? 's' : ''} with statements to look at`,
      parts.attention));
  }

  if (parts.confirmed.length) {
    const n = parts.confirmed.length;
    area.appendChild(buildPatternFold('confirmed',
      `${n} confirmed pattern${n !== 1 ? 's' : ''} — nothing to decide`,
      parts.confirmed));
  }
  if (parts.readable.length) {
    const n = parts.readable.length;
    area.appendChild(buildPatternFold('readable',
      `${n} pattern${n !== 1 ? 's' : ''} the standard parser reads on ${
        n !== 1 ? 'their' : 'its'} own — nothing to decide`,
      parts.readable));
  }
  if (parts.elsewhere.length) {
    const n = parts.elsewhere.length;
    area.appendChild(buildPatternFold('elsewhere',
      `${n} pattern${n !== 1 ? 's' : ''} for supplements or indexes — held, not converted:
       they belong in 867 or 868`,
      parts.elsewhere));
  }
  if (parts.skipped.length) {
    const n = parts.skipped.length;
    area.appendChild(buildPatternFold('skipped',
      `${n} skipped — recognised, and left exactly as ${n !== 1 ? 'they are' : 'it is'}`,
      parts.skipped));
  }
  if (parts.complex.length) {
    const n = parts.complex.length;
    area.appendChild(buildPatternFold('complex',
      `${n} too idiosyncratic to express as a pattern — the standard parser reads ${n !== 1 ? 'them' : 'it'}`,
      parts.complex));
  }

  document.getElementById('btn-toggle-patterns').hidden = false;
  refreshPatternsSummary();
}

/**
 * What the folded step 2 says about itself.
 *
 * Folding must not hide work still to do, so patterns still asking something
 * are named on the one line that remains, in the colour that means "look".
 */
function patternsSummaryLine() {
  if (!detected.length) return '<span class="icon">✓</span> No patterns found yet';

  const parts = partitionGroups(detected);
  const bits = [`${detected.length} pattern${detected.length !== 1 ? 's' : ''}`];
  if (parts.confirmed.length) bits.push(`${parts.confirmed.length} confirmed`);
  if (parts.readable.length) bits.push(`${parts.readable.length} read by the parser`);
  if (parts.skipped.length) bits.push(`${parts.skipped.length} skipped`);
  if (parts.complex.length) bits.push(`${parts.complex.length} too complex`);
  if (parts.attention.length) {
    bits.push(`<span class="count-warn">${parts.attention.length} with statements ${
      sourceMode === 'paste' ? 'held or to check' : 'not read'}</span>`);
  }
  if (parts.open.length) {
    bits.push(`<span class="count-warn">${parts.open.length} need${
      parts.open.length === 1 ? 's' : ''} a decision</span>`);
  }
  const done = !parts.open.length;
  return `<span class="icon${done ? '' : ' pending'}">${done ? '✓' : '●'}</span> `
       + bits.join(' · ');
}

/** Fold step 2 to a line, the way step 1 folds once it has a file. */
function setPatternsCollapsed(collapsed) {
  const body    = document.getElementById('patterns-body');
  const summary = document.getElementById('patterns-summary');
  const toggle  = document.getElementById('btn-toggle-patterns');
  body.hidden = collapsed;
  summary.hidden = !collapsed;
  toggle.textContent = collapsed ? 'Show patterns' : 'Hide patterns';
  toggle.setAttribute('aria-expanded', String(!collapsed));
  if (collapsed) summary.innerHTML = patternsSummaryLine();
}

/** Keep the folded line honest as patterns are confirmed or removed. */
function refreshPatternsSummary() {
  const summary = document.getElementById('patterns-summary');
  if (summary && !summary.hidden) summary.innerHTML = patternsSummaryLine();
}

document.getElementById('btn-toggle-patterns').addEventListener('click', () => {
  setPatternsCollapsed(!document.getElementById('patterns-body').hidden);
});

/** The id a confirmed pattern gets: stable for a group across re-detections. */
function patternIdFor(group) {
  return 'p' + Math.abs(hashString(group.signature || group.human_label)).toString(36);
}

function hashString(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) | 0; }
  return h;
}

/**
 * What answering this card would actually change.
 *
 * The parser reads every statement it can, and a confirmed pattern supplies
 * only what it cannot. So the same screen can be doing one of three quite
 * different jobs, and a cataloguer deciding how much care to spend deserves to
 * know which. Before 0.10.0 they were all the same job and the screen was right
 * not to distinguish them.
 */
/**
 * What the outstanding patterns are outstanding *for*.
 *
 * "Say what a value means" described every card until 0.10.0, when most of them
 * stopped deciding a reading and started supplying only a caption. Two quite
 * different amounts of care, so the count says which is which.
 */
function openBreakdown(open) {
  const reading = open.filter(e => e.group.decides === 'reading').length;
  const caption = open.length - reading;
  const bits = [];
  if (reading) {
    bits.push(`<strong>${reading}</strong> ${reading === 1 ? 'decides' : 'decide'}
               how a statement is read`);
  }
  if (caption) {
    bits.push(`<strong>${caption}</strong> ${caption === 1 ? 'supplies' : 'supply'}
               a caption`);
  }
  return bits.join(', ');
}


function decidesNote(group, skipped) {
  if (skipped || group.too_complex) return '';
  const note = {
    reading: ['alert-warn',
      `The standard parser writes nothing for ${group.count !== 1 ? 'some of these statements' : 'this statement'}
       — nothing in the wording says what the values are. What you say here is what converts
       ${group.count !== 1 ? 'them' : 'it'}.`],
    caption: ['alert-info',
      `The standard parser reads ${group.count !== 1 ? 'these statements' : 'this statement'} already.
       What you add here is the caption: the word the 853 declares for a level written as a bare
       number, where the parser can only write &ldquo;(*)&rdquo;. Only those values can be set;
       the others are read from the statement itself and are greyed out. To correct one of
       those, edit the 866 on its record.`],
    elsewhere: ['alert-info',
      `${group.count !== 1 ? 'These statements read' : 'This statement reads'} as
       ${group.belongs_in === '868' ? 'an index' : 'a supplement'}, which MARC 21 records in
       ${escHtml(group.belongs_in || '867')}, not in 866/863. This tool does not convert
       ${escHtml(group.belongs_in || '867')} yet, so ${group.count !== 1 ? 'they are' : 'it is'}
       held whatever you confirm here. If ${group.count !== 1 ? 'one is' : 'it is'} really part
       of the main run, edit ${group.count !== 1 ? 'its' : 'the'} 866 to take the word out.`],
    nothing: ['alert-info',
      `The standard parser reads ${group.count !== 1 ? 'these statements' : 'this statement'} in full,
       captions and all. Confirming this pattern is optional — it will not change what is written.
       The values below are read from the statement itself, so they are greyed out; to correct
       one, edit the 866 on its record.`],
  }[group.decides];
  if (!note) return '';
  const [cls, text] = note;
  return `<div class="alert ${cls} decides-note">${text}</div>`;
}


function buildPatternCard(group, idx) {
  const card = document.createElement('div');
  card.className = 'pattern-card';
  card.dataset.idx = idx;

  const id = patternIdFor(group);
  const confirmed = library.find(p => p.id === id);
  const skipped = !!(confirmed && confirmed.skip);
  if (confirmed && !skipped) card.classList.add('confirmed');
  if (skipped) card.classList.add('skipped');

  const rate = Math.round((group.match_rate || 0) * 100);

  if (group.too_complex) {
    card.classList.add('too-complex');
    card.innerHTML = `
      <div class="pc-head">
        <span class="pc-label">${escHtml(group.human_label)}</span>
        <span class="pill">${group.count} statement${group.count !== 1 ? 's' : ''}</span>
        <span class="pill decide">too idiosyncratic to express as a pattern</span>
        ${outcomePills(group)}
      </div>
      <div class="pc-body">
        <p class="small dim">${escHtml(group.decline_reason
          || `These statements are ${group.token_count} parts long, which is past the point where a single expression can describe them usefully.`)}
          They will be converted by the standard parser.</p>
        ${buildExamplesHtml(group.examples)}
      </div>
      <div class="pc-records small"></div>
      ${lookAtHtml(group, idx)}`;
    card._group = group;
    card._id = id;
    paintPatternRecords(card);
    return card;
  }

  // Roles already confirmed win over the freshly inferred ones: a cataloguer's
  // decision must survive re-running detection.
  const roles = confirmed ? confirmed.roles : group.suggested_roles;

  card.innerHTML = `
    <div class="pc-head">
      <span class="pc-label">${escHtml(group.human_label)}</span>
      <span class="pill">${group.count} statement${group.count !== 1 ? 's' : ''}</span>
      <span class="pill ${rate === 100 ? 'has-866' : 'decide'}">${rate}% matched</span>
      ${outcomePills(group)}
      <span class="pill confirmed-pill" ${confirmed && !skipped ? '' : 'hidden'}>Confirmed</span>
      <span class="pill skipped-pill" ${skipped ? '' : 'hidden'}>Skipped</span>
      <span class="pill decide role-warning" ${
        !skipped && (needsAnAnswer(group, confirmed)
          || roles.some(r => r.kind === UNRESOLVED_KIND || r.suggested)) ? '' : 'hidden'}>
        needs a decision</span>
      <button type="button" class="btn btn-secondary btn-sm pc-toggle" aria-expanded="false"
              aria-label="Review pattern ${escHtml(group.human_label)}">Review</button>
    </div>
    <div class="pc-expr-row">
      <code class="pc-expr" role="button" tabindex="0" aria-expanded="false"
            title="Click to show the whole expression">${escHtml(group.regex)}</code>
      <button type="button" class="btn btn-ghost btn-sm pc-copy"
              aria-label="Copy expression for ${escHtml(group.human_label)}"
              title="Copy this expression, including any edits made below">Copy</button>
    </div>
    <div class="pc-records small"></div>
    ${lookAtHtml(group, idx)}
    <div class="pc-body" hidden>
      ${decidesNote(group, skipped)}
      <div class="example-bar">
        <button type="button" class="btn btn-ghost btn-sm ex-prev"
                aria-label="Previous example">‹</button>
        <div class="example-text" id="ex-text-${idx}"></div>
        <button type="button" class="btn btn-ghost btn-sm ex-next"
                aria-label="Next example">›</button>
        <span class="example-count small dim"></span>
        <button type="button" class="btn btn-secondary btn-sm ex-edit" aria-describedby="ex-text-${idx}"
                title="Correct this statement here: the 866 on its record, or the line you pasted">Edit</button>
        <button type="button" class="btn btn-ghost btn-sm ex-split" aria-describedby="ex-text-${idx}"
                title="Make this statement into two or more, to say where a change falls that it does not show, such as months to seasons">Split</button>
      </div>
      <div class="ex-edit-slot"></div>

      <div class="role-scroll">
        <table class="role-table">
          <thead>
            <tr><th>Captured</th><th>Value</th><th>Boundary</th><th>Means</th>
                <th>Caption</th><th>Level</th></tr>
          </thead>
          <tbody class="role-rows"></tbody>
        </table>
      </div>

      <div class="skip-note" ${skipped ? '' : 'hidden'}>
        <div class="alert alert-info">
          These statements are recognised and left exactly as they are — no 853,
          no 863, and the 866 stays on the record. Nothing else will pick them
          up, including the standard parser.
        </div>
      </div>

      <div class="preview-block" ${skipped ? 'hidden' : ''}>
        <div class="section-label">What it would produce</div>
        <div class="pattern-preview"><span class="dim small">Checking…</span></div>
      </div>

      <details>
        <summary class="small">Expression and example statements</summary>
        <div class="mt-2">
          <label for="rx-${idx}" class="small">Expression (editable), as the workbench runs it</label>
          <textarea class="regex-box" id="rx-${idx}">${escHtml(group.regex)}</textarea>
          <div class="btn-row">
            <button type="button" class="btn btn-secondary btn-sm pc-test">Test expression</button>
          </div>
          <div class="test-result mt-1"></div>
          ${buildExamplesHtml(group.examples)}
        </div>
      </details>

      <div class="btn-row">
        <button type="button" class="btn btn-primary pc-confirm" ${skipped ? 'hidden' : ''}>
          ${confirmed ? 'Update confirmation' : 'Confirm pattern'}</button>
        <button type="button" class="btn btn-danger btn-sm pc-remove" ${confirmed && !skipped ? '' : 'hidden'}>
          Remove from library</button>
        <button type="button" class="btn btn-secondary btn-sm pc-skip"
                title="Recognise these statements and convert none of them, leaving every 866 as it is">
          ${skipped ? 'Convert these after all' : 'Skip these'}</button>
        <button type="button" class="btn btn-ghost btn-sm pc-reset" ${skipped ? 'hidden' : ''}>
          Reset to suggested</button>
      </div>
      <div class="pc-status"></div>
    </div>`;

  card._group = group;
  card._id = id;
  card._example = 0;            // which example drives the table and preview
  card._roles = roles;
  showExample(card);
  wireCard(card);
  paintPatternRecords(card);
  scheduleFlavoured(card);
  return card;
}

/**
 * Put one example on screen: the statement, its captured values, its preview.
 *
 * Everything the cataloguer reads top to bottom describes the same 866 — the
 * statement, then what was caught from it, then what that becomes in MARC.
 */
function showExample(card) {
  const group = card._group;
  const examples = group.examples || [];
  const shown = group.examples_shown ?? examples.length;
  const i = Math.min(card._example, Math.max(shown - 1, 0));
  card._example = i;

  card.querySelector('.example-text').textContent = examples[i] || '';
  const total = examples.length;
  card.querySelector('.example-count').textContent =
    shown < total ? `${i + 1} of ${shown} shown (${total} in group)`
                  : `${i + 1} of ${total}`;
  card.querySelector('.ex-prev').disabled = shown <= 1;
  card.querySelector('.ex-next').disabled = shown <= 1;
  // Edit is for the statement on screen: one from a file can be edited where
  // the file says it came from; one pasted, in the pasted text.
  card.querySelector('.ex-edit').hidden = card.querySelector('.ex-split').hidden =
    !(sourceMode === 'paste' || exampleSource(card));
  card.querySelector('.ex-edit-slot').innerHTML = '';

  renderRoleRows(card, card._roles, (group.example_values || [])[i] || {});
  updateCardWarnings(card);
  refreshPreview(card);
}

/**
 * Edit or Split one statement in place, wherever it is shown.
 *
 * The Patterns step is where a mistake in a statement is seen -- a comma
 * missing between runs, a stray hyphen, months turning into seasons -- and
 * until 0.41.0 correcting it meant finding the record again in step 3. These
 * make the same edit and split step 3 makes, stored the same way: listed on
 * the record, logged as "Edited by you", put back from there. `target` is
 * {record_index, field_index} for a file, or {pasted: true} for the pasted
 * text. Opened from a card's example, a held statement in a record's
 * preview, or a pasted statement's outcome.
 */
