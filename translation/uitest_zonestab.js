// addZonesTab(): the 5th journal tab, and the bestiary filter it drives.
// Run against a BUILT script:  node uitest_zonestab.js ../Script.txt
//
// This is the first thing in the script that ADDS UI rather than restyling it,
// so the assertions are mostly about fitting into machinery we do not own:
// set_active_button's no-child-elements rule, and the 400px tab row.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8').split('\r\n').join('\n');

function slice(name) {
  const s = src.slice(src.indexOf('    function ' + name + '() {'));
  const end = s.indexOf('\n    }\n');
  if (end === -1) throw new Error('could not slice ' + name);
  return s.slice(0, end + 7);
}
const consts = ['ZONES_TAB_ID', 'ZONES_ONLY_CLASS'].map(
    (n) => src.match(new RegExp('const ' + n + ' = [^\n]+'))[0]).join('\n');
const widths = src.slice(src.indexOf('    const JOURNAL_TAB_W = ['),
                         src.indexOf('];', src.indexOf('const JOURNAL_TAB_W')) + 2);
const tabSrc = consts + '\n' + widths + '\n' + slice('addZonesTab');

let bad = 0;
function expect(what, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) bad++;
  console.log('  ' + (ok ? 'ok  ' : 'FAIL') + ' ' + String(what).padEnd(40) +
              JSON.stringify(got) + (ok ? '' : '  want ' + JSON.stringify(want)));
}

// --- a mock journal bar -----------------------------------------------------
function mkEl(id) {
  return { id: id, style: {}, className: '', children: [], childNodes: [],
           classList: { _s: new Set(), add(c) { this._s.add(c); },
                        remove(c) { this._s.delete(c); },
                        contains(c) { return this._s.has(c); } } };
}
function harness(env) {
  env = env || { master: true, on: true };
  const ids = ['journal_show_quests', 'journal_show_bestiary',
               'journal_show_levelary', 'journal_show_data'];
  const els = {};
  ids.forEach((i) => { els[i] = mkEl(i); });
  const bar = mkEl('journal_control_div');
  bar.children = ids.map((i) => els[i]);
  bar._listeners = [];
  bar.addEventListener = (t, fn) => bar._listeners.push(fn);
  bar.insertBefore = (node, ref) => {
    bar.children.splice(bar.children.indexOf(ref), 0, node);
    node.parentNode = bar;
    els[node.id] = node;
  };
  ids.forEach((i) => { els[i].parentNode = bar; });
  const list = mkEl('bestiary_list');
  let shown = 0;
  const document = {
    getElementById: (i) => (i === 'journal_control_div' ? bar
                          : i === 'bestiary_list' ? list : (els[i] || null)),
    createElement: () => mkEl(''),
  };
  const window = { showBestiary: () => { shown++; } };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const ZONES_TAB = env.on;
  eval(tabSrc);
  addZonesTab();
  addZonesTab();                 // idempotency: must not insert twice
  return { bar: bar, els: els, list: list, shown: () => shown };
}

console.log('addZonesTab');
let h = harness();
const order = h.bar.children.map((c) => c.id);
expect('inserted once, in the right slot', order,
       ['journal_show_quests', 'tl_journal_show_zones', 'journal_show_bestiary',
        'journal_show_levelary', 'journal_show_data']);
// set_active_button requires `clicked_element.children.length == 0` - an
// element child here would silently cost the tab its active highlighting.
const btn = h.els['tl_journal_show_zones'];
expect('no element children (set_active_button)', btn.children.length, 0);
expect('carries the game button class', btn.className, 'journal_control_button');

// The tab row is exactly 400px: 5 widths + 1px margin either side of each.
const w = h.bar.children.map((c) => parseInt(c.style.width, 10));
expect('widths applied', w, [103, 58, 73, 73, 83]);
expect('widths + margins == 400px panel',
       w.reduce((a, b) => a + b, 0) + 2 * w.length, 400);

// --- the filter, driven through the delegated listener ----------------------
const fire = (target) => h.bar._listeners.forEach((fn) => fn({ target: target }));
fire(btn);
expect('Zones click filters the list', h.list.classList.contains('tl_zones_only'), true);
expect('Zones click shows the bestiary panel', h.shown(), 1);
fire(h.els['journal_show_bestiary']);
expect('Bestiary click clears the filter',
       h.list.classList.contains('tl_zones_only'), false);
fire(btn);
fire(h.els['journal_show_data']);
expect('any other tab clears it too',
       h.list.classList.contains('tl_zones_only'), false);
// A click on something that is not a direct child must be ignored.
fire(mkEl('unrelated'));
expect('stray click ignored', h.list.classList.contains('tl_zones_only'), false);

console.log('\ntoggles');
h = harness({ master: true, on: false });
expect('toggle off: no tab', h.bar.children.length, 4);
expect('toggle off: widths untouched',
       h.bar.children.map((c) => c.style.width), [undefined, undefined, undefined, undefined]);
h = harness({ master: false, on: true });
expect('master off: no tab', h.bar.children.length, 4);

console.log('\n' + (bad ? bad + ' FAILURES' : 'all correct'));
process.exit(bad ? 1 : 0);
