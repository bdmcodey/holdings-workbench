/*
 * Text size, the dark theme and the About box; and the library is loaded.
 *
 * Part of the page (templates/tool.html), which loads these files in order.
 */

// ── Accessibility controls: text size and theme ───────────────────────────
(function () {
  const root = document.documentElement;

  const sizeBtns = Array.from(document.querySelectorAll('.ui-size-btn'));
  function applyScale(v) {
    root.style.setProperty('--ui-scale', v);
    try { localStorage.setItem('mst-scale', v); } catch (e) {}
    sizeBtns.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.scale === String(v))));
  }
  sizeBtns.forEach(b => b.addEventListener('click', () => applyScale(b.dataset.scale)));
  let savedScale = null;
  try { savedScale = localStorage.getItem('mst-scale'); } catch (e) {}
  applyScale(savedScale || '1');

  const themeBtn = document.getElementById('theme-toggle');
  function applyTheme(t) {
    root.setAttribute('data-theme', t);
    try { localStorage.setItem('mst-theme', t); } catch (e) {}
    themeBtn.querySelector('.theme-label').textContent = t === 'dark' ? 'Light' : 'Dark';
    themeBtn.setAttribute('aria-pressed', String(t === 'dark'));
  }
  let savedTheme = null;
  try { savedTheme = localStorage.getItem('mst-theme'); } catch (e) {}
  applyTheme(savedTheme ||
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
  themeBtn.addEventListener('click', () =>
    applyTheme(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'));
})();

// ── About / changelog dialog ──────────────────────────────────────────────
(function () {
  const dlg  = document.getElementById('about-dialog');
  const open = document.getElementById('btn-about');
  const done = document.getElementById('btn-about-done');
  if (!dlg || !open) return;
  open.addEventListener('click', () => dlg.showModal());
  done && done.addEventListener('click', () => dlg.close());
  dlg.addEventListener('close', () => open.focus());
  dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
})();

loadLibrary();
