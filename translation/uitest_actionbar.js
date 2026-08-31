// addActionBar(): the icon shortcut row at the top of the location actions.
// Run against a BUILT script:  node uitest_actionbar.js ../Script.txt
//
// The interesting behaviour is all in the SELECTION, and none of it is visible
// from a screenshot: which rows become icons, which category wins when a
// location has six of one kind, and which rows are deliberately excluded.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8').split('\r\n').join('\n');

function slice(name) {
  const s = src.slice(src.indexOf('    function ' + name + '('));
  const end = s.indexOf('\n    }\n');
  if (end === -1) throw new Error('could not slice ' + name);
  return s.slice(0, end + 7);
}
// The safe-zone slot is keyed on REST_LOCATIONS, generated from locations.js
// and holding the CHINESE names that data-travel carries.
const REST_SRC = src.slice(src.indexOf('    const REST_LOCATIONS = new Set(['),
                           src.indexOf(']);', src.indexOf('const REST_LOCATIONS')) + 3);
const barSrc = [
  src.match(/const ACTION_BAR_ID = [^\n]+/)[0],
  REST_SRC,
  slice('isSafeZoneRow'),
  src.slice(src.indexOf('    const ACTION_BAR_SLOTS = ['),
            src.indexOf('    ];', src.indexOf('const ACTION_BAR_SLOTS')) + 6),
  slice('barIconFor'),
  slice('addActionBar'),
].join('\n');
const REST_SET = eval(REST_SRC.replace('const REST_LOCATIONS =', ''));
// A real one, so this cannot pass on a name the game no longer uses.
const A_BED = Array.from(REST_SET).filter((n) => /[一-鿿]/.test(n))[0];

let bad = 0;
function expect(what, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) bad++;
  console.log('  ' + (ok ? 'ok  ' : 'FAIL') + ' ' + String(what).padEnd(44) +
              JSON.stringify(got) + (ok ? '' : '  want ' + JSON.stringify(want)));
}

// --- mock rows --------------------------------------------------------------
function mkRow(spec) {
  const set = new Set(spec.cls || []);
  const attrs = spec.attrs || {};
  const icon = spec.icon === null ? null : {
    _glyph: spec.icon || 'work_outline',
    style: {},
    parentNode: null,
    cloneNode() { return { _glyph: this._glyph, style: {} }; },
  };
  const row = {
    id: spec.id || '',
    style: spec.color ? { color: spec.color } : {},
    classList: { contains: (c) => set.has(c) },
    hasAttribute: (a) => a in attrs,
    getAttribute: (a) => (a in attrs ? attrs[a] : null),
    querySelector: (s) => (s === '.material-icons' ? icon : null),
    click: () => clicks.push(spec.name),
    _name: spec.name,
  };
  if (icon) icon.parentNode = row;
  return row;
}
let clicks = [];

function run(rowSpecs, env) {
  env = env || { master: true, on: true };
  clicks = [];
  const rows = rowSpecs.map(mkRow);
  const made = [];
  const host = {
    children: rows,
    insertBefore: (node) => { host._bar = node; },
    _bar: null,
  };
  const document = {
    getElementById: (i) => (i === 'location_actions_div' ? host
                          : (host._bar && i === 'tl_action_bar' ? host._bar : null)),
    createElement: () => {
      const e = { id: '', className: '', innerHTML: '', style: {}, children: [],
                  _kids: [],
                  appendChild(c) { this._kids.push(c); return c; },
                  addEventListener(t, fn) { this._click = fn; } };
      made.push(e);
      return e;
    },
  };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const LOCATION_ACTION_BAR = env.on;
  eval(barSrc);
  addActionBar();
  addActionBar();               // idempotency: must not build twice
  return { bar: host._bar, host: host };
}

// Read a built bar back as [leftGlyphs, rightGlyphs]. An inactive slot reads
// as "(glyph)" - it still renders its own icon, just dimmed and dead.
function readBar(bar) {
  if (!bar) return null;
  const grp = (g) => g._kids.map((cell) => {
    if (cell.className.indexOf('tl_bar_empty') !== -1) {
      return '(' + /material-icons">([^<]+)</.exec(cell.innerHTML)[1] + ')';
    }
    return cell._kids[0] ? cell._kids[0]._glyph : '?';
  });
  return [grp(bar._kids[0]), grp(bar._kids[1])];
}

// Village: the worst case. 6 jobs, 3 dialogues, a trader, a crafting station.
const VILLAGE = [
  { name: 'job1', cls: ['start_activity'], icon: 'work_outline' },
  { name: 'job2', cls: ['start_activity'], icon: 'work_outline' },
  { name: 'dlg1', cls: ['start_dialogue'], icon: 'question_answer' },
  { name: 'dlg2', cls: ['start_dialogue'], icon: 'question_answer' },
  { name: 'trader', cls: ['start_trade'], icon: 'work_outline' },
  { name: 'craft', cls: ['location_choices'], icon: 'construction' },
  { name: 'exit1', cls: ['travel_normal', 'action_travel'], icon: 'forward' },
  { name: 'exit2', cls: ['travel_normal', 'action_travel'], icon: 'forward' },
  { name: 'combat', cls: ['travel_combat', 'action_travel'], icon: 'warning_amber' },
];

console.log('addActionBar');
let r = run(VILLAGE);
expect('two nav arrows left, combat excluded', readBar(r.bar)[0],
       ['forward', 'forward']);
// One icon per CATEGORY: six jobs and three dialogues collapse to one each,
// which is what makes the slots fixed. Order is the shipped slot order, and
// absent slots still render their own glyph, dimmed.
expect('one icon per category, fixed order', readBar(r.bar)[1],
       ['question_answer', 'work_outline', 'work_outline', '(bed)',
        'construction', '(directions)']);
// Clicking runs the game's own onclick on the FIRST row of that category.
r.bar._kids[1]._kids[2]._click();
expect('activity slot starts the first job', clicks, ['job1']);
r.bar._kids[1]._kids[0]._click();
expect('dialogue slot starts the first dialogue', clicks, ['job1', 'dlg1']);
r.bar._kids[0]._kids[1]._click();
expect('nav arrows keep their own rows', clicks, ['job1', 'dlg1', 'exit2']);

// Absent categories hold their slot open, or the present ones would slide from
// location to location - the whole point of anchoring them right.
console.log('\nfixed slots');
r = run([{ name: 'bed', id: 'start_sleeping_div', icon: 'bed' }]);
expect('sleep alone keeps its position', readBar(r.bar)[1],
       ['(question_answer)', '(work_outline)', '(work_outline)', 'bed',
        '(construction)', '(directions)']);
expect('  and no nav group', readBar(r.bar)[0], []);
// Inactive slots must be dead, not merely faint - a live-looking icon that
// does nothing is worse than an obviously absent one.
expect('  inactive slots have no click handler',
       r.bar._kids[1]._kids.map((c) => typeof c._click).join(','),
       'undefined,undefined,undefined,function,undefined,undefined');
// The expander is deliberately NOT a slot: it only appears where a location
// has more than three exits, so its slot would sit dead nearly everywhere.
r = run([
  { name: 'craft', cls: ['location_choices'], icon: 'construction' },
  { name: 'expand', cls: ['location_choices'], attrs: { 'data-location': 'x' },
    icon: 'format_list_bulleted' },
]);
expect('crafting fills its slot', readBar(r.bar)[1][4], 'construction');
expect('  and the expander gets no slot at all',
       readBar(r.bar)[1].indexOf('format_list_bulleted'), -1);

console.log('\nsafe zone');
// A travel row whose destination is a rest location: the game's own
// quick-return-to-bed, or an ordinary exit that happens to lead to one.
r = run([
  { name: 'exit', cls: ['travel_normal', 'action_travel'],
    attrs: { 'data-travel': '不存在的地方' }, icon: 'forward' },
  { name: 'home', cls: ['travel_normal', 'action_travel'],
    attrs: { 'data-travel': A_BED }, icon: 'directions', color: '#c0c0ff' },
]);
expect('safe zone fills the last slot', readBar(r.bar)[1][5], 'directions');
// Lifted OUT of the navigation group, or it would be offered twice - and its
// whole reason for having a slot is to stop being the nth arrow.
expect('  and is not also a nav arrow', readBar(r.bar)[0], ['forward']);
r.bar._kids[1]._kids[5]._click();
expect('  clicking travels there', clicks, ['home']);
expect('  keeps its rest tint',
       r.bar._kids[1]._kids[5]._kids[0].style.color, '#c0c0ff');
// A combat quick-return is an encounter even if it points at a rest location.
r = run([{ name: 'danger', cls: ['travel_combat', 'action_travel'],
           attrs: { 'data-travel': A_BED }, icon: 'warning_amber' }]);
expect('combat row never counts as safe zone', r.bar, null);

console.log('\nexclusions');
// An unavailable job never gets .start_activity, so it is excluded by
// construction rather than by a test that could be forgotten.
r = run([{ name: 'closed', cls: ['activity_unavailable'], icon: 'work_outline' }]);
expect('unavailable activity is not offered', r.bar, null);
// Encounters are one click from a fight; an icon-only control must not offer
// them. Combat-only location => nothing to show at all.
r = run([{ name: 'zone', cls: ['travel_combat', 'action_travel'], icon: 'warning_amber' }]);
expect('combat-only location shows no bar', r.bar, null);
// During gathering the container holds #action_status_div and friends, which
// are innerText with no glyph. Decided by CONTENT, so it holds for any mode.
r = run([{ name: 'status', id: 'action_status_div', icon: null },
         { name: 'xp', id: 'action_xp_div', icon: null }]);
expect('no icons anywhere => no bar', r.bar, null);

console.log('\ncolour and toggles');
// The tint lives on a wrapper span in most rows; the clone has to pick it up
// or a rest destination's #c0c0ff arrow would come out plain white.
r = run([{ name: 'rest', cls: ['travel_normal', 'action_travel'], icon: 'forward',
           color: '#c0c0ff' }]);
expect('row colour copied onto the icon',
       r.bar._kids[0]._kids[0]._kids[0].style.color, '#c0c0ff');
r = run(VILLAGE, { master: true, on: false });
expect('toggle off: no bar', r.bar, null);
r = run(VILLAGE, { master: false, on: true });
expect('master off: no bar', r.bar, null);

console.log('\n' + (bad ? bad + ' FAILURES' : 'all correct'));
process.exit(bad ? 1 : 0);
