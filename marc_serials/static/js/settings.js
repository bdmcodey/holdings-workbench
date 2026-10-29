/*
 * Conversion settings: the caption convention, the 853 indicators and
 * subfields, frequency and issues per volume, strict and the left-out choice.
 *
 * Part of the page (templates/tool.html), which loads these files in order.
 */

// ─────────────────────────────────────────────────────────────────────────
// Caption convention (ported from the converter, one editor rather than two)
// ─────────────────────────────────────────────────────────────────────────

function applyPreset(name) {
  const preset = CONVENTION_PRESETS[name] || CONVENTION_PRESETS.standard;
  ENUM_LEVELS.forEach((lvl, i) => {
    const sf  = document.getElementById(`bsf-${lvl.key}`);
    const cap = document.getElementById(`bcap-${lvl.key}`);
    if (sf) sf.value = (preset.subfields.enum || [])[i] || '';
    // Left empty on purpose: an enumeration caption is the word the statement
    // itself used, and filling these in would overwrite "no. 26" with "v. 26".
    // The placeholder shows what a statement that names no caption gets.
    if (cap) cap.value = '';
  });
  CONVENTION_LEVELS.forEach(level => {
    const sf  = document.getElementById(`bsf-${level}`);
    const cap = document.getElementById(`bcap-${level}`);
    if (sf)  sf.value  = preset.subfields[level] || '';
    if (cap) cap.value = DEFAULT_CAPTIONS[level] || '';
  });
  document.getElementById('batch-ind1').value = preset.indicators[0];
  document.getElementById('batch-ind2').value = preset.indicators[1];
  document.getElementById('batch-chronology').value =
    preset.chron_as_text ? 'text' : 'code';
  markInvalidSubfields();
  markInvalidIndicators();
}


/**
 * Say beside the boxes when an 853 indicator is one the standard does not
 * define. The server keeps the preset's value instead, and says so in the run
 * summary, but that is after the fact; this is while the value is being typed.
 */
function markInvalidIndicators() {
  const err = document.getElementById('batch-ind-error');
  const bad = [];
  [['batch-ind1', 'first'], ['batch-ind2', 'second']].forEach(([id, label]) => {
    const el = document.getElementById(id);
    const v = (el.value || '').trim();
    const ok = v.length === 1 && INDICATOR_VALUES.includes(v);
    el.classList.toggle('invalid', !ok);
    if (!ok) bad.push(label);
  });
  if (!bad.length) { err.hidden = true; return; }
  err.innerHTML = `<div class="alert alert-warn">The 853 ${bad.join(' and ')}
    indicator${bad.length > 1 ? 's take' : ' takes'} 0, 1, 2 or 3. Until
    ${bad.length > 1 ? "they do, the preset's values are" : "it does, the preset's value is"}
    written instead.</div>`;
  err.hidden = false;
}
['batch-ind1', 'batch-ind2'].forEach(id =>
  document.getElementById(id).addEventListener('input', markInvalidIndicators));

/** Flag subfields MARC will not accept, or that two levels are fighting over. */
function markInvalidSubfields() {
  const seen = {};
  ENUM_LEVELS.map(l => l.key).concat(CONVENTION_LEVELS).forEach(level => {
    const el = document.getElementById(`bsf-${level}`);
    if (!el) return;
    const v = (el.value || '').trim().toLowerCase();
    const bad = v && (v.length !== 1 || !ALLOWED_SUBFIELDS.includes(v) || seen[v]);
    el.classList.toggle('invalid', !!bad);
    if (v) seen[v] = true;
  });
}

/** Collect the editor into the shape every conversion endpoint expects. */
function conventionPayload() {
  const subfields = {}, captions = {};
  const enumSubfields = {};
  ENUM_LEVELS.forEach(lvl => {
    const sf  = document.getElementById(`bsf-${lvl.key}`);
    const cap = document.getElementById(`bcap-${lvl.key}`);
    if (sf && sf.value.trim())   enumSubfields[lvl.key] = sf.value.trim().toLowerCase();
    if (cap && cap.value.trim()) captions[lvl.key]      = cap.value.trim();
  });
  if (Object.keys(enumSubfields).length) subfields.enum = enumSubfields;
  CONVENTION_LEVELS.forEach(level => {
    const sf  = document.getElementById(`bsf-${level}`);
    const cap = document.getElementById(`bcap-${level}`);
    if (sf && sf.value.trim())   subfields[level] = sf.value.trim().toLowerCase();
    if (cap && cap.value.trim()) captions[level]  = cap.value.trim();
  });
  return {
    convention: document.getElementById('batch-convention').value,
    subfields,
    captions,
    indicators: [document.getElementById('batch-ind1').value,
                 document.getElementById('batch-ind2').value],
    chronology: document.getElementById('batch-chronology').value,
    parser_fallback: document.getElementById('opt-parser-fallback').checked,
    parser_strict: document.getElementById('opt-parser-strict').checked,
    left_out_policy: document.getElementById('opt-left-out').value,
    keep_separate: [...keepSeparate],
    skip_records: [...skipRecords],
    frequency: document.getElementById('batch-freq').value,
    numbering_continuity: document.getElementById('batch-continuity').value,
    holdings_level: document.getElementById('batch-holdings-level').value,
    units_per_higher: unitsPerHigher(),
    // Carried with every preview, not only with the conversions: whether a
    // record that already has 863s is kept or regenerated changes what its
    // preview should show.
    clear_existing_853_863: document.getElementById('batch-clear853863').checked,
  };
}

/**
 * The declared $u, or "" when the box holds nothing usable.
 *
 * Validated here rather than only on the server, because the server's fallback
 * is silence: an unusable value writes no $u, and a cataloguer who typed "1 a
 * year" would see nothing appear and have nothing to read about why. The
 * message belongs beside the box they typed in.
 */
function unitsPerHigher() {
  const box = document.getElementById('batch-units');
  const err = document.getElementById('batch-units-error');
  const raw = (box.value || '').trim().toLowerCase();

  if (!raw) { err.hidden = true; return ''; }
  const ok = raw === 'var' || raw === 'und'
          || (/^[1-9][0-9]{0,2}$/.test(raw));
  if (!ok) {
    err.innerHTML = `<div class="alert alert-warn">A count of parts, or
      <code>var</code> or <code>und</code>. Nothing is written to $u until this
      reads as one of those.</div>`;
    err.hidden = false;
    return '';
  }
  err.hidden = true;
  return raw;
}

document.getElementById('batch-units').addEventListener('change', () => {
  // The same reasoning as the holdings level below: $u goes into every 853, so
  // every preview on screen was built under the old value.
  unitsPerHigher();
  document.querySelectorAll('.pattern-card').forEach(card => {
    if (!card.querySelector('.pc-body')?.hidden) refreshPreview(card);
  });
  if (allRecords.length) refreshReview();
});

document.getElementById('batch-clear853863').addEventListener('change', () => {
  // Ticking it turns every record kept for its own 863s into one that will be
  // regenerated, so the list and any open preview are out of date.
  if (allRecords.length) refreshReview();
});

document.getElementById('batch-holdings-level').addEventListener('change', () => {
  // The level goes into every 863 and decides which records are reported as
  // disagreeing with their own Leader/17, so both have to be recomputed --
  // otherwise choosing a level appears to do nothing until something else
  // happens to reload.
  //
  // Worth knowing: the other controls in this panel do not do this. Frequency
  // and numbering continuity change the 853 a preview shows and take effect on
  // the next reload rather than at once. Left alone here rather than changed
  // quietly -- it is the same gap, and fixing it for everything is a decision
  // about how often the screen should talk to the server.
  document.querySelectorAll('.pattern-card').forEach(card => {
    if (!card.querySelector('.pc-body')?.hidden) refreshPreview(card);
  });
  if (allRecords.length) refreshReview();
});

function syncStrict() {
  // Strict qualifies the parser; with the parser off there is nothing for it
  // to qualify.
  const strict = document.getElementById('opt-parser-strict');
  strict.disabled = !document.getElementById('opt-parser-fallback').checked;
}

['opt-parser-fallback', 'opt-parser-strict', 'opt-left-out'].forEach(id =>
  document.getElementById(id).addEventListener('change', () => {
    syncStrict();
    // Every preview on screen was computed under the old setting.
    document.querySelectorAll('.pattern-card').forEach(card => {
      if (!card.querySelector('.pc-body')?.hidden) refreshPreview(card);
    });
    if (allRecords.length) refreshReview();
    revealSteps();
  }));
syncStrict();

(function () {
  const sel = document.getElementById('batch-convention');
  sel.addEventListener('change', () => applyPreset(sel.value));
  document.getElementById('conv-grid-batch')
          .addEventListener('input', markInvalidSubfields);
  applyPreset(sel.value);
})();
