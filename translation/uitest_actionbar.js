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
  src.match(/const BAR_TARGET_CLASS = [^\n]+/)[0],
  REST_SRC,
  slice('isSafeZoneRow'),
  slice('isGameQuickReturn'),
  src.slice(src.indexOf('    const ACTION_BAR_SLOTS = ['),
            src.indexOf('    ];', src.indexOf('const ACTION_BAR_SLOTS')) + 6),
  slice('barIconFor'),
  slice('addActionBar'),
].join('\n');
// Slot positions and basic glyphs come from the shipped table itself - see
// SLOTS below, which is derived by EVALUATING it inside run(). Reordering the
// bar or renaming a glyph therefore moves these tests with it, instead of
// leaving them checking the wrong slot against a string the assertion chose.
//
// Read rather than text-matched: a predicate can hold string literals of its
// own (r.id === 'start_sleeping_div'), which makes a 3-element slot textually
// indistinguishable from a 4-element one. Two different regexes got that
// wrong before this was given up as a parsing problem.

const REST_SET = eval(REST_SRC.replace('const REST_LOCATIONS =', ''));
// A real one, so this cannot pass on a name the game no longer uses.
const BEDS = Array.from(REST_SET).filter((n) => /[一-鿿]/.test(n));
const A_BED = BEDS[0];
const B_BED = BEDS[1];

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
    // barGlyph reads textContent, the same property mirrorReturnIcons writes
    // when it swaps a signpost for an arrow.
    textContent: spec.icon || 'work_outline',
    style: {},
    parentNode: null,
    cloneNode() { return { _glyph: this._glyph, style: {} }; },
  };
  const marks = new Set();
  const row = {
    id: spec.id || '',
    style: spec.color ? { color: spec.color } : {},
    classList: { contains: (c) => set.has(c),
                 add: (c) => marks.add(c), remove: (c) => marks.delete(c) },
    _marks: marks,
    hasAttribute: (a) => a in attrs,
    getAttribute: (a) => (a in attrs ? attrs[a] : null),
    // The game wraps ONLY its quick-return-to-bed link in an inner
    // <span style="color:#c0c0ff">; our own rest tint goes on the row.
    querySelector: (sel) => {
      if (sel === '.material-icons') return icon;
      if (sel.indexOf('c0c0ff') !== -1) return spec.gameQuickReturn ? {} : null;
      return null;
    },
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
                  _kids: [], _on: {},
                  appendChild(c) { this._kids.push(c); return c; },
                  addEventListener(t, fn) {
                    this._on[t] = fn;
                    if (t === 'click') this._click = fn;
                  } };
      made.push(e);
      return e;
    },
  };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const LOCATION_ACTION_BAR = env.on;
  const ACTION_BAR_HOVER_HINT = env.hover !== false;
  // A const declared inside eval does NOT leak to the enclosing scope, so the
  // table has to be handed out by ASSIGNMENT to a variable that already exists
  // here. (Only function declarations leak; this bit me on ADD_ALL_BTN_ID too.)
  let captured = null;
  eval(barSrc + '\ncaptured = ACTION_BAR_SLOTS;');
  addActionBar();
  addActionBar();               // idempotency: must not build twice
  return { bar: host._bar, host: host, rows: rows, slots: captured };
}

// The shipped slot table, evaluated rather than parsed. run([]) builds no bar
// - there are no rows - but it does expose the table.
const SLOTS = run([]).slots;
const SLOT = {};
SLOTS.forEach((s, i) => { SLOT[s[0]] = i; });
// An inactive slot renders its basic glyph, dimmed.
const dim = (name) => '(' + SLOTS[SLOT[name]][2] + ')';

// Read a built bar back as [leftGlyphs, rightGlyphs]. An inactive slot reads
// as "(glyph)" - it still renders its own icon, just dimmed and dead.
function readBar(bar) {
  if (!bar) return null;
  const grp = (g) => g._kids.map((cell) => {
    if (cell.className.indexOf('tl_bar_empty') !== -1) {
      return '(' + /material-icons">([^<]+)</.exec(cell.innerHTML)[1] + ')';
    }
    // A cloned nav icon carries _glyph; a fixed slot's is BUILT, so it has
    // textContent instead. Both are read, so a slot silently falling back to
    // cloning would show up here as the row's glyph rather than the slot's.
    const k = cell._kids[0];
    if (!k) return '?';
    return k._glyph !== undefined ? k._glyph : k.textContent;
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
       ['question_answer', 'work_outline', 'work_outline', dim('sleep'),
        'construction', dim('safezone')]);
// Clicking runs the game's own onclick on the FIRST row of that category.
r.bar._kids[1]._kids[SLOT.activity]._click();
expect('activity slot starts the first job', clicks, ['job1']);
r.bar._kids[1]._kids[SLOT.dialogue]._click();
expect('dialogue slot starts the first dialogue', clicks, ['job1', 'dlg1']);
r.bar._kids[0]._kids[1]._click();
expect('nav arrows keep their own rows', clicks, ['job1', 'dlg1', 'exit2']);

// Absent categories hold their slot open, or the present ones would slide from
// location to location - the whole point of anchoring them right.
console.log('\nfixed slots');
r = run([{ name: 'bed', id: 'start_sleeping_div', icon: 'bed' }]);
expect('sleep alone keeps its position', readBar(r.bar)[1],
       [dim('dialogue'), dim('activity'), dim('trade'), 'bed',
        dim('craft'), dim('safezone')]);
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
expect('crafting fills its slot', readBar(r.bar)[1][SLOT.craft], 'construction');
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
expect('safe zone fills the last slot', readBar(r.bar)[1][SLOT.safezone], 'directions');
// The claimed row is lifted OUT of the navigation group - it has a fixed home
// on the right, and offering it twice would defeat the point of giving it one.
// The unrelated exit is untouched.
expect('  and is not also a nav arrow', readBar(r.bar)[0], ['forward']);
r.bar._kids[1]._kids[SLOT.safezone]._click();
expect('  clicking travels there', clicks, ['home']);
expect('  keeps its rest tint',
       r.bar._kids[1]._kids[SLOT.safezone]._kids[0].style.color, '#c0c0ff');
// A combat quick-return is an encounter even if it points at a rest location.
r = run([{ name: 'danger', cls: ['travel_combat', 'action_travel'],
           attrs: { 'data-travel': A_BED }, icon: 'warning_amber' }]);
expect('combat row never counts as safe zone', r.bar, null);

// THE reported case, v16.4. At the Act 2 camp both a Fast Travel and the real
// Quick Return lead somewhere restful, and mirrorReturnIcons leaves the
// 'directions' signpost on BOTH jump kinds - so matching the glyph picked the
// Fast Travel, which comes first. Only the game's own link carries an inner
// c0c0ff span, and that is what decides it now.
r = run([
  { name: 'ft_act1', cls: ['travel_normal', 'action_travel'],
    attrs: { 'data-travel': A_BED }, icon: 'directions' },
  { name: 'quickreturn', cls: ['travel_normal', 'action_travel'],
    attrs: { 'data-travel': B_BED }, icon: 'directions', gameQuickReturn: true },
]);
r.bar._kids[1]._kids[SLOT.safezone]._click();
expect('Quick Return beats a Fast Travel to a bed', clicks, ['quickreturn']);
expect('  the Fast Travel stays a nav arrow', readBar(r.bar)[0], ['directions']);

// Same, with the loser an ordinary walkable exit rather than a Fast Travel.
r = run([
  { name: 'walk', cls: ['travel_normal', 'action_travel'],
    attrs: { 'data-travel': A_BED }, icon: 'forward' },
  { name: 'quickreturn', cls: ['travel_normal', 'action_travel'],
    attrs: { 'data-travel': A_BED }, icon: 'directions', gameQuickReturn: true },
]);
r.bar._kids[1]._kids[SLOT.safezone]._click();
expect('Quick Return beats an earlier walkable exit', clicks, ['quickreturn']);
// Only the row the slot actually TOOK leaves the nav group. The other exit is
// an ordinary walking route that happens to end somewhere restful, so it stays
// with the other ways out - excluding it would lose a real destination.
expect('  the losing rest exit stays a nav arrow', readBar(r.bar)[0], ['forward']);
r.bar._kids[0]._kids[0]._click();
expect('  and still walks there', clicks, ['quickreturn', 'walk']);
// Without a preferred glyph present, first occurrence still wins.
r = run([
  { name: 'walkA', cls: ['travel_normal', 'action_travel'],
    attrs: { 'data-travel': A_BED }, icon: 'forward' },
  { name: 'walkB', cls: ['travel_normal', 'action_travel'],
    attrs: { 'data-travel': A_BED }, icon: 'forward' },
]);
r.bar._kids[1]._kids[SLOT.safezone]._click();
expect('no Quick Return: first occurrence wins', clicks, ['walkA']);

console.log('\nhover hint');
r = run(VILLAGE);
const activityCell = r.bar._kids[1]._kids[SLOT.activity];
activityCell._on.mouseenter();
expect('hovering lights the row it will act on',
       r.rows[0]._marks.has('tl_bar_target'), true);
expect('  and only that row',
       r.rows.filter((x) => x._marks.has('tl_bar_target')).length, 1);
activityCell._on.mouseleave();
expect('  cleared on leave', r.rows[0]._marks.has('tl_bar_target'), false);
r = run(VILLAGE, { master: true, on: true, hover: false });
expect('hover toggle off: no listeners',
       typeof r.bar._kids[1]._kids[SLOT.activity]._on.mouseenter, 'undefined');

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
