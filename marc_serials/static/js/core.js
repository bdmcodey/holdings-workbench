/*
 * State the whole page shares, and the small helpers every part uses:
 * escaping text, showing an alert, posting a request to the server.
 *
 * Part of the page (templates/tool.html), which loads these files in order.
 */

const ENUM_KIND          = 'enum';
// 853 carries enumeration captions in $a-$f, so six levels is the deepest a
// record can state. Anything past that has nowhere to go.
const MAX_ENUM_LEVELS    = 6;
const DEFAULT_CAPTIONS   = { year: '(year)', month: '(month)', day: '(day)' };
const ALLOWED_SUBFIELDS = 'abcdefghijklm';

// ── State ────────────────────────────────────────────────────────────────
let allRecords  = [];    // record summaries from the uploaded file
let allStatements = [];  // every 866 $a in that file, in order
let detected    = [];    // the last detection run's groups
// Where the statements come from: an uploaded file, or the text box. One or
// the other, never both -- patterns found from pasted text while Convert
// worked on a file were two sources on one screen, and nothing said which
// was which. The last one chosen wins.
let sourceMode  = null;  // "file" or "paste"
// The loaded file, kept while pasted statements are in use, so switching back
// is one click rather than a second upload: its name, its line in step 1, and
// the patterns last found from it.
let fileName    = '';
let fileSummary = '';
let fileDetect  = null;
let library     = [];    // confirmed patterns, mirroring the server's copy
let lastSplit   = true;  // how the last detection ran; patterns inherit it
// Patterns the cataloguer has taken out of the library one at a time.
// Auto-confirmation must not put them back on the next detection run --
// removing one is a decision. Clear forgets them all: see its handler.
let dismissed   = new Set();
// How many patterns the last detection run left out for that reason, to say so.
let removedHeldBack = 0;
// Review state, for this visit only: which records have been previewed, which
// the cataloguer has ticked off, and where in the file they are.
let recordPreviews = new Map();   // record index -> the page entry for it
let reviewed       = new Set();
// Records where the cataloguer has said two statements recording different
// amounts of detail are NOT one publication. A judgement about the serial, so
// it is theirs, and it is per record.
let keepSeparate   = new Set();
let skipRecords    = new Set();   // records to leave exactly as they are
// Records that have been converted, so the file on the server has them
// converted and each can be downloaded on its own. The server rebuilds that
// file from every decision made on it, so a record stays converted here until
// a new file is uploaded.
let convertedRecords = new Set();
// What every record in the file would produce, in counts rather than fields.
// The filters and the row status run on this, so they answer for the whole
// file rather than for whichever page happens to be loaded.
let recordIndex    = new Map();
let reviewFilter   = 'all';
// Set by a pattern card: {id, mode: 'converted' | 'shape', indexes}.
let patternFilter  = null;
let reviewOffset   = 0;
let reviewSearch   = '';    // what the Find box is narrowing the list to

// Ten a page, in both steps, unless the cataloguer chooses otherwise in Convert.
//
// It was 50 in Convert, and 50 rows is about eight screens of scrolling before
// the Convert and Download buttons below the list come into reach -- on a
// 320-record file the accordion measured 34,800px. Ten is enough to see the
// shape of a page and short enough that the controls stay in view.
//
// Nothing here fetches less than it did: previews were already requested a
// page at a time, so a smaller page means more requests, each smaller.
//
// The review list's size is now the cataloguer's to choose -- 5, 10, 25 or 50
// -- and ten stays the default for the reason above. The choice is kept in this
// browser, like the theme and text size, so it survives a reload and a new
// upload.
//
// "All records" was offered from 0.19.0 and withdrawn in 0.24.1: on a
// 372-record file, opening and closing a record lagged noticeably in the
// cataloguer's browser with every row on screen. Measured headless it did not
// (about 0.1s at every size, the page holding the same 8,275 elements), so the
// cost is in drawing 372 rows, which a headless test does not do. Fifty is the
// cataloguer's cap. A saved "all" from before becomes 50, the nearest size
// still offered, rather than falling back to ten.
const REVIEW_PAGE_SIZES = ['5', '10', '25', '50'];
let reviewPageSize = '10';
const PATTERN_PAGE = 10;


/** Records per page in the review list, as a number the paging can add up. */
function reviewPageLimit() {
  return Number(reviewPageSize);
}

// Which page of the patterns still wanting a decision is on screen. The
// confirmed, parser-read, skipped and too-complex groups are folded away
// already and are not paged -- folding a fold would help nobody.
let patternOffset  = 0;

// ─────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function highlightField(raw) {
  // Colour-code MARC display strings like "853 ## $8 1 $a v."
  return raw
    .replace(/^(\d{3})/,         '<span class="sf-tag">$1</span>')
    .replace(/\s(##|\d[\d#])/,   ' <span class="sf-ind">$1</span>')
    .replace(/\$([a-z0-9])/g,    '<span class="sf-code">$$$1</span>')
    .replace(/<\/span>([^<$]+)/g, '</span><span class="sf-value">$1</span>');
}

function showAlert(container, msg, type='warn') {
  if (!container) return;
  container.innerHTML = `<div class="alert alert-${type}">${escHtml(msg)}</div>`;
}

function fieldHtml(display, cls) {
  return `<div class="field-display ${cls}">${highlightField(escHtml(display))}</div>`;
}

/** POST JSON and return the parsed body, or throw with the server's message. */
async function postJson(url, payload) {
  const res  = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data;
}
