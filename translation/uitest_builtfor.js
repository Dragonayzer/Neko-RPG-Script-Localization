// addBuiltForLabel(): the "built against" line under the bottom bar's version
// button.  Run against a BUILT script:  node uitest_builtfor.js ../Script.txt
//
// Two things here are easy to get wrong and invisible if you do:
//   - prepareGame() sets #changelog_button's innerHTML wholesale on body load,
//     which DESTROYS anything we put inside it. The pass has to survive that.
//   - the stylesheet is injected unconditionally, before the toggles are read,
//     so the re-boxing rule must be scoped to a class we only add when the
//     line is actually there. Otherwise the button is restyled for people who
//     have the label switched off.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8').split('\r\n').join('\n');

function slice(name) {
  const s = src.slice(src.indexOf('    function ' + name + '() {'));
  const end = s.indexOf('\n    }\n');
  if (end === -1) throw new Error('could not slice ' + name);
  return s.slice(0, end + 7);
}
// All four consts in the SAME eval as the function - a const does not leak.
const fnSrc = ['BUILT_CLASS', 'BUILT_FOR_GAME', 'TL_VERSION']
    .map((n) => src.match(new RegExp('const ' + n + " = '[^']*';"))[0]).join('\n') +
    '\n' + slice('addBuiltForLabel');

let bad = 0;
function expect(what, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) bad++;
  console.log('  ' + (ok ? 'ok  ' : 'FAIL') + ' ' + String(what).padEnd(42) +
              JSON.stringify(got) + (ok ? '' : '  want ' + JSON.stringify(want)));
}

// ---- the smallest DOM with the shape --------------------------------------
function makeLink() {
  return {
    children: [],
    classes: [],
    classList: { add: function (c) { if (this._o.classes.indexOf(c) === -1)
                                        this._o.classes.push(c); } },
    appendChild: function (c) { this.children.push(c); },
    querySelector: function (sel) {
      const want = sel.replace('.', '');
      return this.children.filter((c) => c.className === want)[0] || null;
    },
    // prepareGame() does `.innerHTML = "V3.47a"`, which drops every child.
    wipe: function () { this.children = []; this.classes = []; },
  };
}
function run(link, env) {
  env = env || { master: true, on: true };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const BUILT_FOR_LABEL = env.on;
  const document = {
    querySelector: () => link,
    createElement: () => ({ className: '', textContent: '' }),
  };
  eval(fnSrc);
  addBuiltForLabel();
  addBuiltForLabel();          // idempotency: must not stack up
  return link;
}

console.log('addBuiltForLabel');
let link = makeLink();
link.classList._o = link;
run(link);
expect('one line added, not two', link.children.length, 1);
expect('  reads TL<script> · <game>', link.children[0].textContent,
       'TL' + src.match(/const TL_VERSION = '([^']*)'/)[1] + ' · ' +
       src.match(/const BUILT_FOR_GAME = '([^']*)'/)[1]);
expect('  carries the styling class', link.children[0].className, 'tl_built');
expect('  link marked so the CSS applies', link.classes, ['tl_has_built']);

// prepareGame() wipes the button once on body load, and it can land AFTER our
// first pass. The next scan has to put the line back.
link.wipe();
expect('wiped by the game', link.children.length, 0);
run(link);
expect('  restored on the next scan', link.children.length, 1);

console.log('\ntoggles');
link = makeLink(); link.classList._o = link;
run(link, { master: true, on: false });
expect('toggle off: nothing added', link.children.length, 0);
expect('  and no class, so no restyle', link.classes, []);
link = makeLink(); link.classList._o = link;
run(link, { master: false, on: true });
expect('master off: nothing added', link.children.length, 0);

// ---- the CSS half ---------------------------------------------------------
// Sliced to styleOverrides: searching the whole file would match the changelog,
// where every rule this script adds is also described in prose.
console.log('\nstyleOverrides');
const CSS = (function () {
  const i = src.indexOf('styleOverrides.textContent = `');
  return src.slice(i, src.indexOf('`;', i));
})();
expect('re-box rule exists',
       /#changelog_button a\.tl_has_built\s*\{/.test(CSS), true);
expect('  scoped to .tl_has_built, not every version button',
       /#changelog_button a\s*\{/.test(CSS), false);
const rule = CSS.match(/#changelog_button a\.tl_has_built\s*\{([\s\S]*?)\}/)[1];
// 40px total, the same box the game gives it - so no sibling in the flex row
// moves. Anything taller overflows the bar, which is pinned to the viewport
// bottom, and the second line would render off-screen.
expect('  height still 40px', /height:\s*40px/.test(rule), true);
expect('  vertical padding removed', /padding:\s*0px 10px/.test(rule), true);
expect('  stacks as a column', /flex-direction:\s*column/.test(rule), true);
expect('sub-line rule exists', /#changelog_button \.tl_built\s*\{/.test(CSS), true);

console.log('\n' + (bad ? bad + ' FAILURES' : 'all correct'));
process.exit(bad ? 1 : 0);
