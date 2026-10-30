/*
 * Inside a pattern card: the statements to look at, the table of what each
 * value means, and the preview of what it would write.
 *
 * Part of the page (templates/tool.html), which loads these files in order.
 */

function lookRows(group) {
  // With a file, a statement held or to check is put right on its record in
  // step 3, and the card says how many and takes you there (lookStep3Html).
  // What stays listed is what reading the pattern turns on: a statement the
  // standard parser cannot read at all, usually for a typo, which is also why
  // its card asks for an answer.
  const want = lookFilter !== 'all' ? [lookFilter]
    : sourceMode === 'paste' ? ['held', 'to_check', 'unread'] : ['unread'];
  return (group.to_look_at || []).map((r, i) => ({ r, i }))
    .filter(({ r }) => r.kinds.some(k => want.includes(k)));
}

/**
 * With a file: how many of a card's statements are held or to check, and a
 * way to them in step 3.
 *
 * Until 0.49.0 each was listed on the card with Edit and Split -- 28
 * statements across 17 cards on the real export, under "patterns with
 * statements to look at". Asked for by the cataloguer, who found it noise a
 * step early: 27 of the 28 were the same whatever was decided on the card
 * (13 changing between months and seasons, 8 with wording MARC has no code
 * for, 4 with a range inside one end, 2 issues across two years), and putting
 * one right means reading the rest of its record, which a card does not show.
 */
function lookStep3Html(group) {
  if (sourceMode === 'paste' || lookFilter !== 'all') return '';
  const held = group.held || 0;
  const check = group.to_check || 0;
  if (!held && !check) return '';
  const said = [held ? `${held} held` : '', check ? `${check} to check` : '']
    .filter(Boolean).join(' and ');
  return `<div class="pc-step3 small">
    <span><strong>${said}</strong>: put right on ${held + check !== 1 ? 'their records' : 'its record'}
      in step 3, with the rest of the record in view.</span>
    <button type="button" class="btn btn-secondary btn-sm pc-show-records"
            data-mode="look">Show ${held + check !== 1 ? 'them' : 'it'} in step 3</button>
  </div>`;
}

function lookAtHtml(group, idx) {
  const step3 = lookStep3Html(group);
  const rows = lookRows(group);
  if (!rows.length) return step3;
  const all = lookExpanded.has(patternIdFor(group));
  const shown = all ? rows : rows.slice(0, LOOK_SHOWN);
  // One explanation per reason, the statements it applies to under it.
  const byReason = new Map();
  shown.forEach(row => {
    const reason = lookReason(row.r);
    if (!byReason.has(reason.key)) byReason.set(reason.key, { reason, rows: [] });
    byReason.get(reason.key).rows.push(row);
  });
  return `${step3}<div class="pc-outcomes">
    <div class="small"><strong>Statements to look at</strong> (${rows.length}${
      (group.to_look_at || []).length >= 200 ? ' or more' : ''})</div>
    ${[...byReason.values()].map(({ reason, rows: these }) => `
      <div class="look-reason">
        ${reason.html}
        ${these.map(({ r, i }) => `
          <div class="pc-outcome" id="pcl-${idx}-${i}" data-idx="${idx}" data-i="${i}">
            ${lookRowHtml(r, reason)}
          </div>`).join('')}
      </div>`).join('')}
    ${rows.length > shown.length ? `<button type="button" class="btn btn-ghost btn-sm look-more"
       data-idx="${idx}">Show all ${rows.length}</button>` : ''}
  </div>`;
}

/**
 * The reason a statement in a card's list is there, said once for all the
 * statements that share it, with what is particular to each kept for its row.
 *
 * Six statements held for changing from months to seasons carried six orange
 * boxes saying the same thing but for two words -- the month and the season
 * -- and the list read six times longer than it was. The cataloguer asked for
 * the explanation once and the statements under it; the full message stays on
 * each statement in step 3, where one record is looked at on its own. What
 * differs between them is kept, short, on the row: the change ("February ->
 * Fall") is where to split, and where reading stopped points at the typo.
 * A message that is particular to its statement throughout ("'Buyers Guide'
 * is not something a month or season subfield can hold") groups only with
 * statements saying exactly the same.
 */
function lookReason(r) {
  if (lookFilter !== 'left_out' && r.kinds.includes('held')
      && r.chron_switch && r.chron_switch.where === 'within') {
    return { key: 'switch', hint: switchHint, html: `<div class="alert alert-attention small">
      <strong>Months and seasons in one statement.</strong> Each of these changes between months
      and seasons inside one 866. An 853 gives one or the other, so each needs two 853s and two
      863s, and only you can say which issue the change falls at. Split each at the change, or
      leave it as it is; nothing is written from it until then.</div>` };
  }
  if (lookFilter !== 'left_out' && r.kinds.includes('unread')) {
    return { key: 'unread', hint: stoppedHint, html: `<div class="alert alert-warn small">
      <strong>Not read by the standard parser.</strong> ${UNREAD_CAUSES}</div>` };
  }
  let html;
  let text;
  if (lookFilter !== 'left_out' && r.kinds.includes('held')) {
    text = (r.warnings || []).join('\n');
    html = `<div class="alert alert-attention small">${heldReasonHtml(r)}</div>`;
  } else {
    const ws = (r.warnings || []).filter(w =>
      lookFilter !== 'left_out' || (r.left_out || []).includes(w));
    text = ws.join('\n');
    html = ws.map(w => warningHtml(r, w)).join('');
  }
  return { key: `msg:${text}`, hint: () => '', html };
}

/** "February → Fall": the change, from the note that says where it is. */
function switchHint(r) {
  const m = ((r.chron_switch || {}).note || '').match(/\(([^()]*?) … ([^()]*?)\)/);
  return m ? `${escHtml(m[1])} → ${escHtml(m[2])}` : '';
}

/** Where reading stopped: the part of the statement nothing accounted for. */
function stoppedHint(r) {
  for (const w of r.warnings || []) {
    const m = w.match(/could not account for '(.*)'/);
    // Where it stopped is the start of what is quoted; the rest is the rest
    // of the statement, already on the row.
    if (m) return `stopped at <code>${escHtml(m[1].length > 40 ? m[1].slice(0, 40) + '…' : m[1])}</code>`;
  }
  const said = (r.warnings || []).find(w => !w.startsWith('No recognisable holdings ranges found'));
  return said ? escHtml(said) : '';
}

function lookRowHtml(r, reason) {
  const src = r.source;
  const rec = src && allRecords[src.record_index];
  const others = (r.records || []).length - 1;
  const where = src && sourceMode !== 'paste'
    ? `<span class="small dim">on ${recordName(src.record_index)}${
        others > 0 ? ` and ${others} other record${others !== 1 ? 's' : ''}` : ''}</span>` : '';
  const pills = r.kinds.map(k => {
    const [cls, label] = LOOK_PILLS[k];
    return `<span class="pill ${cls}">${label}</span>`;
  }).join('');
  const hint = reason.hint(r);
  const within = r.chron_switch && r.chron_switch.where === 'within';
  return `
    <div class="pc-outcome-head">
      <span class="role-sample">${escHtml(r.text)}</span>
      ${pills}
      ${hint ? `<span class="small look-hint">${hint}</span>` : ''}
      ${where}
      <button type="button" class="btn btn-secondary btn-sm" onclick="lookAction(this, 'edit')"
              aria-label="Edit ${escHtml(r.text)}">Edit</button>
      <button type="button" class="btn btn-${within ? 'secondary' : 'ghost'} btn-sm"
              aria-label="${within ? 'Split at the change' : 'Split'}: ${escHtml(r.text)}"
              title="Make this statement into two or more, to say where a change falls that it does not show, such as months to seasons"
              onclick="lookAction(this, 'split')">${within ? 'Split at the change' : 'Split'}</button>
    </div>
    <div class="look-slot"></div>`;
}

/** Edit or Split on a statement in a card's list, in place. */
function lookAction(button, kind) {
  const row = button.closest('.pc-outcome');
  const r = detected[Number(row.dataset.idx)].to_look_at[Number(row.dataset.i)];
  const slot = row.querySelector('.look-slot');
  if (sourceMode === 'paste') {
    if (kind === 'split') openInlineSplit(slot, { pasted: true }, r.text);
    else openInlineEdit(slot, { pasted: true }, r.text,
                        { where: 'Saving changes it in the pasted text.' });
    return;
  }
  // With a file, on its record in step 3: see editInStep3().
  const src = r.source;
  if (src) editInStep3(src.record_index, src.field_index, kind, row.closest('.pattern-card'));
}

document.addEventListener('click', e => {
  const more = e.target.closest('.look-more');
  if (!more) return;
  const group = detected[Number(more.dataset.idx)];
  lookExpanded.add(patternIdFor(group));
  redrawPatterns();
});

/**
 * What usually stops the standard parser, said once above the statements it
 * could not read. A statement the parser cannot read is often one with a
 * mistake in it, and as often one written as meant in a shape only a pattern
 * reads, so both are said.
 */
const UNREAD_CAUSES = 'If the statement has a mistake in it, such as a comma missing '
  + 'between runs, a hyphen after a run that is closed, or a stray character like //, '
  + 'Edit fixes it. If it is written as meant, what you say on this card is what converts it.';

function buildExamplesHtml(examples) {
  const shown = (examples || []).slice(0, 12);
  const more  = (examples || []).length - shown.length;
  return `
    <div class="mt-2">
      <div class="section-label">Example statements</div>
      ${shown.map(s => `<div class="role-sample">${escHtml(s)}</div>`).join('')}
      ${more > 0 ? `<div class="small dim mt-05">+ ${more} more</div>` : ''}
    </div>`;
}

/**
 * Draw one row per captured value, for the example currently on screen.
 *
 * The value column is what makes the screen worth having: seeing "1990" and
 * "1994" under two rows the tool both called an end year is how a cataloguer
 * notices that the first is really the start. It shows this statement's values
 * only — pooling them across examples produced a column that lined up against
 * nothing.
 */
/**
 * Whether a value's settings can change anything. The parser reads every
 * statement it can, and a confirmed pattern supplies only what it cannot: so
 * where the parser reads the group in full, nothing here changes the output,
 * and where it reads all but a caption, only the bare numbers -- the values
 * written with no caption, named "…_num" -- have anything to decide. Measured,
 * not assumed: on such a group, changing a captioned value's caption, meaning
 * or level, or a year's, leaves the 853 and 863 exactly as they were.
 */
function roleIsFixed(group, role) {
  if (!group) return false;
  if (group.decides === 'nothing') return true;
  if (group.decides === 'caption') return !BARE_NUMBER_RE.test(role.group);
  return false;
}
const BARE_NUMBER_RE = /(^|_)num(_\d+)?$/;
const FIXED_ROLE_TITLE = 'Read from the statement itself, so changing it here would change '
  + 'nothing. To correct it, edit the 866 on its record.';

function renderRoleRows(card, roles, values) {
  const body = card.querySelector('.role-rows');
  const group = card._group;
  body.innerHTML = roles.map(role => {
    const fixed = roleIsFixed(group, role);
    const off = fixed ? 'disabled' : '';
    // A suggested reading is shown chosen but still counts as undecided: the
    // cataloguer is being offered one, not told one. A fixed value has nothing
    // to decide.
    const undecided = !fixed && (role.kind === UNRESOLVED_KIND || role.suggested);
    const value = (values || {})[role.group] || '';
    const kindOptions = KIND_CHOICES.map(([kind, label]) =>
      `<option value="${kind}" ${role.kind === kind ? 'selected' : ''}>${escHtml(label)}</option>`
    ).join('');
    // Level is "by position" unless the cataloguer says otherwise. Position is
    // what MARC 21 means by $a-$f, so the order the values appear in is
    // normally the answer -- but a statement that states its levels out of
    // order needs to be able to say so.
    const levelOptions = Array.from({length: MAX_ENUM_LEVELS}, (_, i) =>
      `<option value="${i}" ${role.level === i ? 'selected' : ''}>${ordinal(i + 1)}</option>`
    ).join('');
    const enumOnly = role.kind === ENUM_KIND ? '' : 'hidden';
    return `
      <tr class="${undecided ? 'needs-decision' : ''}${fixed ? ' role-fixed' : ''}"
          data-group="${escHtml(role.group)}" ${fixed ? `title="${escHtml(FIXED_ROLE_TITLE)}"` : ''}>
        <td class="role-group">${escHtml(role.group)}</td>
        <td class="role-sample">${escHtml(value || '—')}${
          role.suggested && !fixed ? '<span class="role-guess">likely, please confirm</span>' : ''}${
          fixed ? '<span class="role-fixed-note">from the statement</span>' : ''}</td>
        <td>
          <select class="role-boundary" ${off} aria-label="Boundary for ${escHtml(role.group)}">
            <option value="start" ${role.boundary === 'start' ? 'selected' : ''}>Start</option>
            <option value="end"   ${role.boundary === 'end'   ? 'selected' : ''}>End</option>
          </select>
        </td>
        <td>
          <select class="role-kind" ${off} aria-label="Meaning of ${escHtml(role.group)}">
            <option value="" ${role.kind === UNRESOLVED_KIND ? 'selected' : ''} disabled>— choose —</option>
            ${kindOptions}
            <option value="${IGNORE_KIND}" ${role.kind === IGNORE_KIND ? 'selected' : ''}>
              ${escHtml(IGNORE_LABEL)}</option>
          </select>
        </td>
        <td class="enum-only" ${enumOnly}>
          <input type="text" class="role-caption" list="caption-words" ${off}
                 value="${escHtml(role.caption || '')}" placeholder="v."
                 aria-label="Caption for ${escHtml(role.group)}" />
        </td>
        <td class="enum-only" ${enumOnly}>
          <select class="role-enum-level" ${off} aria-label="Enumeration level of ${escHtml(role.group)}">
            <option value="">By position</option>
            ${levelOptions}
          </select>
        </td>
      </tr>`;
  }).join('');
}

function ordinal(n) {
  const suffix = (n % 100 >= 11 && n % 100 <= 13) ? 'th'
               : ['th', 'st', 'nd', 'rd'][n % 10] || 'th';
  return `${n}${suffix}`;
}

/**
 * Show or hide a row's caption and level boxes to match what it now means.
 *
 * Only enumeration has either: a year has no caption to choose and no level to
 * sit at, so leaving the boxes on screen would invite filling in something that
 * goes nowhere.
 */
function syncEnumCells(tr) {
  const isEnum = tr.querySelector('.role-kind').value === ENUM_KIND;
  tr.querySelectorAll('.enum-only').forEach(td => { td.hidden = !isEnum; });
}

/** Read the role table back out. */
function collectRoles(card) {
  return Array.from(card.querySelectorAll('.role-rows tr')).map(tr => {
    const kind    = tr.querySelector('.role-kind').value || UNRESOLVED_KIND;
    const caption = tr.querySelector('.role-caption').value.trim();
    const level   = tr.querySelector('.role-enum-level').value;
    return {
      group:    tr.dataset.group,
      boundary: tr.querySelector('.role-boundary').value,
      kind,
      // Caption and level belong to enumeration alone, and an empty level
      // means "wherever position puts it" -- the server numbers those.
      caption: kind === ENUM_KIND && caption ? caption : null,
      level:   kind === ENUM_KIND && level !== '' ? Number(level) : null,
      // Reading the table back is the cataloguer accepting what it shows, so a
      // suggestion stops being one the moment it is collected.
      suggested: false,
    };
  });
}

/**
 * Rows with no level chosen at all. A *suggested* level does not count: it is
 * already a usable answer, and pressing Confirm is how the cataloguer accepts
 * it. Suggestions keep a pattern out of auto-confirmation, which is what makes
 * them get looked at, but they must not block the button — re-picking the value
 * already selected fires no change event, so there would be no way to accept.
 */
function undecidedCount(card) {
  return collectRoles(card).filter(r => r.kind === UNRESOLVED_KIND).length;
}

function wireCard(card) {
  const body   = card.querySelector('.pc-body');
  const toggle = card.querySelector('.pc-toggle');

  toggle.addEventListener('click', () => {
    body.hidden = !body.hidden;
    toggle.textContent = body.hidden ? 'Review' : 'Hide';
    toggle.setAttribute('aria-expanded', String(!body.hidden));
    toggle.setAttribute('aria-label',
      `${body.hidden ? 'Review' : 'Hide'} pattern ${card._group.human_label}`);
    if (!body.hidden) refreshPreview(card);
  });

  // Re-preview whenever a role changes: the point of the screen is watching the
  // MARC output move when you correct something, not pressing a button to find
  // out afterwards.
  card.querySelector('.role-rows').addEventListener('change', e => {
    const tr = e.target.closest('tr');
    if (tr) {
      tr.classList.remove('needs-decision');
      if (e.target.classList.contains('role-kind')) syncEnumCells(tr);
    }
    card._roles = collectRoles(card);
    updateCardWarnings(card);
    refreshPreview(card);
  });

  card.querySelector('.pc-test').addEventListener('click', () => testPattern(card));
  card.querySelector('.pc-confirm').addEventListener('click', () => confirmPattern(card));
  card.querySelector('.pc-remove').addEventListener('click', () => removePattern(card));
  card.querySelector('.pc-skip').addEventListener('click', () => toggleSkip(card));
  card.querySelector('.pc-reset').addEventListener('click', () => {
    card._roles = card._group.suggested_roles;
    showExample(card);
  });

  card.querySelector('.ex-edit').addEventListener('click', () => openCardEdit(card));
  card.querySelector('.ex-split').addEventListener('click', () => openCardSplit(card));

  card.querySelector('.ex-prev').addEventListener('click', () => {
    const shown = card._group.examples_shown ?? (card._group.examples || []).length;
    // Wrap, so stepping back from the first lands on the last rather than
    // dead-ending on a disabled button.
    card._example = (card._example - 1 + shown) % shown;
    showExample(card);
  });
  card.querySelector('.ex-next').addEventListener('click', () => {
    const shown = card._group.examples_shown ?? (card._group.examples || []).length;
    card._example = (card._example + 1) % shown;
    showExample(card);
  });
}

/**
 * The pill and the Confirm button answer different questions.
 *
 * The pill asks "is this card waiting on a cataloguer?". It is whenever the
 * step counts it as wanting an answer -- not confirmed, and an answer would
 * change what is written -- and whenever a row is undecided or only suggested.
 * Until 0.46.1 only the rows lit it, so a card whose every value the detector
 * had given a meaning wanted an answer with nothing on it saying so: on the
 * real export the one such card said "not read" and no more, and 3 of the 10
 * on the first page from other libraries' catalogues were the same. Confirming
 * puts it out (confirmPattern redraws the table from the saved roles, which
 * carry no suggestions); removing the pattern from the library lights it again.
 * The button asks "is there an answer to act on?", which a suggestion already is.
 */
function updateCardWarnings(card) {
  const warn = card.querySelector('.role-warning');
  if (!warn) return;
  const stored = library.find(p => p.id === card._id);
  warn.hidden = !needsAnAnswer(card._group, stored)
    && card.querySelectorAll('.role-rows tr.needs-decision').length === 0;
}

let previewTimer = null;
function refreshPreview(card) {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => runPreview(card), 250);
}

async function runPreview(card) {
  // A skipped pattern produces nothing, and showing the fields it *would*
  // produce next to a note saying it will not would read as a promise.
  if (card.classList.contains('skipped')) return;

  const target = card.querySelector('.pattern-preview');
  const roles  = collectRoles(card);
  const undecided = roles.filter(r => r.kind === UNRESOLVED_KIND);

  if (undecided.length) {
    target.innerHTML = `<div class="alert alert-warn">
      Choose what ${undecided.map(r => `<code>${escHtml(r.group)}</code>`).join(', ')}
      ${undecided.length > 1 ? 'mean' : 'means'} before this pattern can be used.</div>`;
    return;
  }

  target.innerHTML = '<span class="spinner"></span> Working out the fields…';

  const source = exampleSource(card);
  try {
    const data = await postJson('api/pattern-preview', {
      regex: card.querySelector('.regex-box').value,
      roles,
      split: lastSplit,
      // With a record, the preview can show the linking numbers conversion
      // would really write; without one it can only show the statement alone.
      record_index: source ? source.record_index : null,
      field_index:  source ? source.field_index  : null,
      statements: [card._group.examples[card._example]],
      ...conventionPayload(),
    });
    target.innerHTML = data.scope === 'record'
      ? renderRecordPreview(data)
      : data.previews.map(renderPreviewPair).join('')
        || '<div class="alert alert-info">Nothing to preview.</div>';
  } catch (err) {
    showAlert(target, err.message, 'err');
  }
}

/**
 * The whole record the example sits in, so $8 can be read rather than trusted.
 *
 * Numbering is a record-level decision: statements sharing a publication
 * pattern share an 853 and run 1.1, 1.2, and a different pattern starts 2.1.
 * Showing the example alone always read "1.1" whatever it would really get.
 */
/**
 * One warning on a converted statement. A warning that is why the statement
 * is "to check" asks for a decision, and is orange and says so; any other is
 * said for the log, and stays yellow. One record can carry both, on different
 * statements, and in one colour they could not be told apart.
 */
/**
 * Why a statement was held: every reason, not the first. The first is often
 * the generic "No recognisable holdings ranges found", and the one after it
 * says where reading stopped -- "could not account for '// 1982//'" -- which
 * is what a cataloguer cleaning up the 866 needs to see.
 */
/**
 * Statements held because they belong in another field: a supplement (867)
 * or an index (868). Apart from the held statements, because what they want is
 * different -- not a pattern, but moving, which is the cataloguer's to do
 * until this tool converts 867 and 868.
 */
function elsewhereHtml(list) {
  if (!list.length) return '';
  return `
    <div class="pattern-group">
      <div class="pg-header">
        <div class="pg-header-meta">
          <span class="pg-title">Belongs in another field</span>
          <span class="pill">${list.length} statement${list.length !== 1 ? 's' : ''}</span>
        </div>
        <div class="dim small">Not converted. Supplements belong in 867 and indexes in
          868, which this tool does not convert yet. A pattern will not convert these.</div>
      </div>
      ${list.map(pv => `
        <div class="pair-row">
          <div>
            <div class="pair-col-label">866 — source</div>
            <div class="field-display f866">${escHtml(pv.source_866)}</div>
          </div>
          <div>
            <div class="pair-col-label">Belongs in ${escHtml(pv.belongs_in)}</div>
            <div class="alert alert-info">${heldReasonHtml(pv)}</div>
          </div>
        </div>`).join('')}
    </div>`;
}

function heldReasonHtml(pv) {
  const reasons = pv.warnings || [];
  if (!reasons.length) return 'Not converted.';
  return reasons.map(w => `<div>${escHtml(w)}</div>`).join('');
}

function warningHtml(pv, w, extra = 'small') {
  if ((pv.attention || []).includes(w)) {
    return `<div class="alert alert-attention ${extra}"><strong>To check:</strong> ${escHtml(w)}</div>`;
  }
  if ((pv.left_out || []).includes(w)) {
    return `<div class="alert alert-leftout ${extra}"><strong>Left out to fit MARC:</strong> ${escHtml(w)}</div>`;
  }
  return `<div class="alert alert-warn ${extra}">${escHtml(w)}</div>`;
}

function renderRecordPreview(data) {
  const idx = data.record.index;
  const elsewhere = data.previews.filter(pv => pv.belongs_in);
  const counts = linkCounts(data.previews);

  const row = pv => `
    <div class="pair-row ${pv.is_example ? 'is-example' : ''}">
      <div>
        <div class="pair-col-label">866${pv.is_example ? ' — the example above' : ''}</div>
        <div class="field-display f866">${escHtml(pv.source_866)}</div>
        <div class="small dim mt-1">read by
          <span class="pill ${pv.from_pattern ? 'from-pattern' : ''}">${escHtml(pv.source_label)}</span>
        </div>
      </div>
      <div>
        <div class="pair-col-label">863 — generated</div>
        ${pv.fields_863.map(f => fieldHtml(f, 'f863')).join('')}
      </div>
    </div>`;

  const blocks = inRecordOrder(data.previews).map(seg => seg.held
    ? heldRowsHtml(seg.rows, idx, pv => pv.is_example ? ' — the example above' : '')
    : `
    <div class="pattern-group">
      <div class="pg-header">
        <div class="pg-header-meta">
          <span class="pg-title">Pattern $8 ${escHtml(seg.link)}${seg.continued ? ', continued' : ''}</span>
          <span class="pill ${seg.existing ? '' : 'has-866'}">${
            seg.existing ? 'already on this record' : 'generated'}</span>
          <span class="dim small">${counts[seg.link]} statement${counts[seg.link] !== 1 ? 's' : ''}</span>
          ${seg.merged ? `<span class="pill decide"
             title="These statements record different amounts of detail. Tick &quot;Keep patterns separate&quot; on this record if they are not one publication.">merged</span>` : ''}
        </div>
        <div class="field-display f853">${highlightField(escHtml(seg.field_853 || ''))}</div>
      </div>
      ${seg.rows.map(row).join('')}
    </div>`).join('');

  return `
    <div class="small dim mb-1">In <strong>${escHtml(data.record.title)}</strong> —
      every holdings statement on the record, in its order, with the linking numbers it would
      receive.</div>
    ${blocks}${elsewhereHtml(elsewhere)}`;
}

/**
 * A record's statements in the order its 866s come, each under the 853 it
 * links to.
 *
 * Held statements were gathered into a "Held for review" block after
 * everything else, so the one statement asking for attention was the last
 * thing on the screen, and out of its place: a statement held between two
 * that convert is where the record changes, from months to seasons, say.
 * Each now sits where it comes, its reason in orange, with Edit and Split
 * beside it; once fixed it converts where it stands. Where the linking number
 * changes a new 853 heading starts, so a pattern the record comes back to is
 * headed again, "continued". Supplements and indexes keep their own block.
 */
function inRecordOrder(previews) {
  const segments = [];
  const seen = new Set();
  previews.forEach(pv => {
    if (pv.belongs_in) return;
    const last = segments[segments.length - 1];
    if (pv.needs_review || !pv.fields_863.length) {
      if (last && last.held) last.rows.push(pv);
      else segments.push({ held: true, rows: [pv] });
      return;
    }
    if (last && !last.held && last.link === pv.link) { last.rows.push(pv); return; }
    segments.push({ held: false, link: pv.link, field_853: pv.field_853,
                    existing: pv.existing, merged: pv.merged_run,
                    continued: seen.has(pv.link), rows: [pv] });
    seen.add(pv.link);
  });
  return segments;
}

/** How many statements link to each $8, wherever on the record they come. */
function linkCounts(previews) {
  const counts = {};
  previews.forEach(pv => {
    if (!pv.belongs_in && !pv.needs_review && pv.fields_863.length) {
      counts[pv.link] = (counts[pv.link] || 0) + 1;
    }
  });
  return counts;
}

/** Statements held where they come in the record: reason, Edit and Split. */
function heldRowsHtml(rows, idx, labelFor = () => '') {
  return `
    <div class="pattern-group held-group">
      ${rows.map(pv => `
        <div class="pair-row ${pv.is_example ? 'is-example' : ''}"
             data-record="${idx}" data-field="${pv.field_index ?? ''}">
          <div>
            <div class="pair-col-label">866${labelFor(pv)} — held, nothing written</div>
            <div class="field-display f866">${escHtml(pv.source_866)}</div>
            ${pv.field_index != null ? `<div class="btn-row mt-1">
              <button type="button" class="btn btn-secondary btn-sm"
                      aria-label="Edit 866 ${escHtml(pv.source_866)}"
                      onclick="heldAction(this, 'edit')">Edit</button>
              <button type="button" class="btn btn-${pv.chron_switch && pv.chron_switch.where === 'within'
                ? 'secondary' : 'ghost'} btn-sm"
                      aria-label="${pv.chron_switch && pv.chron_switch.where === 'within'
                        ? 'Split this 866 at the change' : 'Split 866'}: ${escHtml(pv.source_866)}"
                      title="Make this 866 into two or more statements, to say where a change falls that it does not show, such as months to seasons"
                      onclick="heldAction(this, 'split')">${pv.chron_switch && pv.chron_switch.where === 'within'
                        ? 'Split this 866 at the change' : 'Split'}</button>
            </div>` : ''}
            <div class="held-slot"></div>
          </div>
          <div>
            <div class="pair-col-label">Reason</div>
            <div class="alert alert-attention">${heldReasonHtml(pv)}</div>
          </div>
        </div>`).join('')}
    </div>`;
}

/** Edit or Split on a held statement, in place. */
function heldAction(button, kind) {
  const row = button.closest('.pair-row');
  const idx = Number(row.dataset.record);
  const fi = Number(row.dataset.field);
  const slot = row.querySelector('.held-slot');
  const f = ((allRecords[idx] || {}).fields_866 || [])[fi];
  if (!f) return;
  // In a card's preview, in step 2: on the record itself, in step 3. The same
  // preview inside step 3's record is edited where it stands.
  const card = button.closest('.pattern-card');
  if (card) { editInStep3(idx, fi, kind, card); return; }
  if (f.split_part != null) {
    slot.innerHTML = `<div class="alert alert-info small mt-1">This is a part of an 866 you
      split. Change it with Split in the record's list of 866s, in step 3.</div>`;
    return;
  }
  const target = { record_index: idx, field_index: fi };
  if (kind === 'split') openInlineSplit(slot, target, f.a || '');
  else openInlineEdit(slot, target, f.a || '');
}

/**
 * One statement, converted both ways.
 *
 * The statement-scope counterpart to renderRecordPreview. Statements pasted
 * rather than uploaded have no record to sit in, so the linking numbers cannot
 * be shown and the useful comparison is a different one: what this pattern
 * writes, beside what the standard parser writes today.
 *
 * It was deleted when record scope arrived and its caller was not, so every
 * pasted statement reached `data.previews.map(renderPreviewPair)` and threw
 * "renderPreviewPair is not defined" -- with the confirmation step showing an
 * error where the generated fields should be. The styles it uses were never
 * removed, which is the clearest sign the deletion was an accident.
 */
function renderPreviewPair(pv) {
  const side = (fields, label) => {
    if (!fields) {
      return `<div>
        <div class="pair-col-label">${label}</div>
        <div class="alert alert-warn">This pattern does not match the statement.</div>
      </div>`;
    }
    const lines = [
      fields.field_853 ? fieldHtml(fields.field_853, 'f853') : '',
      ...fields.fields_863.map(f => fieldHtml(f, 'f863')),
    ].filter(Boolean).join('');
    return `<div>
      <div class="pair-col-label">${label}</div>
      ${lines || '<div class="alert alert-warn">Nothing was converted from this statement.</div>'}
      ${(fields.warnings || []).map(
        w => warningHtml(fields, w, 'mt-1')).join('')}
    </div>`;
  };

  return `
    <div class="preview-pair">
      <div style="grid-column:1/-1;">
        <div class="preview-head">
          <span class="preview-stmt">${escHtml(pv.statement)}</span>
          ${pv.differs
            ? '<span class="pill decide">differs from the standard parser</span>'
            : '<span class="pill has-866">same as the standard parser</span>'}
        </div>
      </div>
      ${side(pv.pattern, 'With this pattern')}
      ${side(pv.parser, 'Standard parser (used today)')}
    </div>`;
}


async function testPattern(card) {
  const box = card.querySelector('.test-result');
  box.innerHTML = '<span class="spinner"></span> Testing…';
  try {
    const data = await postJson('api/test-regex', {
      regex: card.querySelector('.regex-box').value,
      statements: card._group.examples,
      roles: collectRoles(card),
    });
    const pct = Math.round(data.match_rate * 100);
    box.innerHTML = `<div class="alert alert-${pct === 100 ? 'ok' : 'warn'}">
      ${data.matched} of ${data.matched + data.failed} matched (${pct}%).</div>`;
    // The edit may have added or removed capture groups, so the table is
    // rebuilt from the roles the server worked out, keeping earlier decisions.
    card._roles = data.roles;
    card._group.example_values = data.example_values || [];
    showExample(card);
  } catch (err) {
    showAlert(box, err.message, 'err');
  }
}
