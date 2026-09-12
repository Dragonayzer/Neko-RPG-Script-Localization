// fixSpecColons(): the separator between a special attribute's name and its
// description.  Run against a BUILT script:  node uitest_speccolon.js ../Script.txt
//
// display.js writes each spec line as
//     `<br><b><font color=…>${name} </font></b> ：${description} `
// so the spacing that is right for a fullwidth Chinese colon leaves English
// reading "Spirit Flash  :A light-element insight." - colon bound to the
// sentence instead of the title.
//
// The two spaces sit in DIFFERENT text nodes, one inside the bold and one
// after it, which is the whole reason this is a DOM pass rather than a
// glossary entry. So the mock has to reproduce that structure, not just the
// string, or it tests nothing.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8').split('\r\n').join('\n');

function slice(name) {
  const s = src.slice(src.indexOf('    function ' + name + '() {'));
  const end = s.indexOf('\n    }\n');
  if (end === -1) throw new Error('could not slice ' + name);
  return s.slice(0, end + 7);
}
// Declared in the same eval as the function - a const does not leak out of one.
const fnSrc = src.match(/const SPEC_COLON_RE = [^\n]+/)[0] + '\n' +
              src.match(/const IDEO_RE = [^\n]+/)[0] + '\n' +
              slice('fixSpecColons');

let bad = 0;
function expect(what, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) bad++;
  console.log('  ' + (ok ? 'ok  ' : 'FAIL') + ' ' + String(what).padEnd(40) +
              JSON.stringify(got) + (ok ? '' : '  want ' + JSON.stringify(want)));
}

// ---- the smallest DOM that has the shape ----------------------------------
function text(t) {
  return { nodeType: 3, textContent: t, lastChild: null };
}
function el(tag, children) {
  const e = {
    nodeType: 1, tag: tag, children: children || [], dataset: {},
    get lastChild() { return this.children.length
        ? this.children[this.children.length - 1] : null; },
    get textContent() {
      return this.children.map((c) => c.textContent).join('');
    },
    querySelectorAll: function (sel) {
      const out = [];
      (function walk(n) {
        n.children.forEach((c) => {
          if (c.nodeType !== 1) return;
          if (c.tag === sel) out.push(c);
          walk(c);
        });
      })(this);
      return out;
    },
  };
  // nextSibling, wired by the parent
  e.children.forEach((c, i) => { c.nextSibling = e.children[i + 1] || null; });
  return e;
}

function tooltip(name, desc, opts) {
  opts = opts || {};
  const nameNode = text(name + (opts.noTrailingSpace ? '' : ' '));
  const font = el('font', [nameNode]);
  const b = el('b', [font]);
  const descNode = text((opts.sep === undefined ? ' ：' : opts.sep) + desc);
  const tip = el('div', [b, descNode]);
  tip.children.forEach((c, i) => { c.nextSibling = tip.children[i + 1] || null; });
  return tip;
}

function run(tips, env) {
  env = env || { master: true, on: true };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const SPEC_COLON_FIX = env.on;
  const document = {
    querySelectorAll: () => tips.filter((t) => t.dataset.tlColon === undefined),
  };
  eval(fnSrc);
  fixSpecColons();
  fixSpecColons();          // idempotency: the marker must hold
  return tips.map((t) => t.textContent);
}

console.log('fixSpecColons');
let t = tooltip('Spirit Flash', 'A light-element insight.');
expect('colon binds to the title', run([t])[0],
       'Spirit Flash: A light-element insight.');
expect('  tooltip marked done', t.dataset.tlColon, '1');

// The fullwidth colon may already have been converted to an ASCII one by the
// stranded-punctuation fragment before this pass runs, so BOTH must be handled.
t = tooltip('Greed ω', 'This enemy seems very sensitive to money.', { sep: ' :' });
expect('ASCII colon handled too', run([t])[0],
       'Greed ω: This enemy seems very sensitive to money.');

// Chinese still present = the prose pass has not been past. Deferring rather
// than marking done is what stops the tooltip being stranded half-translated.
t = tooltip('灵闪', '这个敌人...');
run([t]);
expect('untranslated tooltip deferred', t.dataset.tlColon, undefined);

// A bold that is NOT a spec name - the realm badge - is followed by a <br>
// ELEMENT, never a text node, so it must be left completely alone.
const badge = el('b', [text('Skyhigh-Tier Rank 4 +')]);
const br = el('br', []);
const tip2 = el('div', [badge, br, text('Some description with no colon.')]);
tip2.children.forEach((c, i) => { c.nextSibling = tip2.children[i + 1] || null; });
expect('realm badge untouched', run([tip2])[0],
       'Skyhigh-Tier Rank 4 +Some description with no colon.');

// A bold followed by text that does not start with a colon is not a spec line.
const other = el('b', [text('Stats:')]);
const tip3 = el('div', [other, text(' 8.19e13')]);
tip3.children.forEach((c, i) => { c.nextSibling = tip3.children[i + 1] || null; });
expect('non-separator text untouched', run([tip3])[0], 'Stats: 8.19e13');

console.log('\ntoggles');
t = tooltip('Spirit Flash', 'A light-element insight.');
expect('toggle off: untouched', run([t], { master: true, on: false })[0],
       'Spirit Flash  ：A light-element insight.');
t = tooltip('Spirit Flash', 'A light-element insight.');
expect('master off: untouched', run([t], { master: false, on: true })[0],
       'Spirit Flash  ：A light-element insight.');

console.log('\n' + (bad ? bad + ' FAILURES' : 'all correct'));
process.exit(bad ? 1 : 0);
