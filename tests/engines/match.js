// Reads {"regexes": [...], "statements": [...]} on stdin; writes, for each
// regex, a string of 1s and 0s: whether it matches each statement.
// Each regex is a literal such as /^v\.\d+$/i, as the workbench copies it.
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = input.regexes.map(text => {
  const m = /^\/([\s\S]*)\/([a-z]*)$/.exec(text);
  const rx = new RegExp(m[1], m[2]);
  return input.statements.map(s => (rx.test(s) ? '1' : '0')).join('');
});
process.stdout.write(JSON.stringify(out));
