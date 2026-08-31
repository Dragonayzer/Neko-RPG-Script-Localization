// mirrorReturnIcons(): travel-option icons - glyph swap + mirrored Return arrow.
// Cosmetic behaviour lives in JS and the Python suite cannot reach it.
// Run against a BUILT script:  node uitest_icons.js ../Script.txt
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8').split('\r\n').join('\n');

const reSrc = src.match(/const RETURN_LABEL_RE = [^\n]+/)[0] + '\n' +
              src.match(/const JUMP_LABEL_RE = [^\n]+/)[0] + '\n' +
              src.slice(src.indexOf('    const BACKWARD_LABELS = new Set(['),
                        src.indexOf(']);', src.indexOf('const BACKWARD_LABELS')) + 3);
const fnSrc = src.slice(src.indexOf('    function mirrorReturnIcons() {'));
const end = fnSrc.indexOf('\n    }\n');
if (end === -1) throw new Error('could not slice function body');
const fnBody = fnSrc.slice(0, end + 7);

// read the shipped glyph, so this cannot pass on a stale value
const SHIPPED_ICON = eval(src.match(/const TRAVEL_ICON = [^;]+/)[0].split('=')[1]);

function mkOpt(label, glyph) {
  const icon = { textContent: glyph || 'directions', style: {},
                 nextSibling: { textContent: ' ' + label } };
  return { querySelector: (s) => (s === '.material-icons' ? icon : null),
           _icon: icon, _label: label, _orig: glyph || 'directions' };
}

// Every label here is a REAL one, taken from locations.js via the built dicts.
// The pairs that matter are the near-misses: "Leave the village" goes FORWARD
// (Village -> Forest road) while "Leave the Crypt" goes back, and "Climb out"
// / "Give up" are backward without looking remotely like "Return".
function mkOpts() {
  return [
    mkOpt('Return to the Na Family Treasury'),          // back  (regex)
    mkOpt('Return to the Camp'),                        // back  (regex)
    mkOpt('Quick Return [Wildbeast Forest]', 'warning_amber'),   // jump
    mkOpt("Quick Return [Neko's Room]"),                // jump, glyph=directions
    mkOpt('Climb out'),                                 // back  (set)
    mkOpt('Give up'),                                   // back  (set)
    mkOpt('Leave the Crypt'),                           // back  (set)
    mkOpt('Take the side path, return to the Camp'),    // back  (set)
    mkOpt('Go to [Qingye Riverbank]'),                  // forward
    mkOpt('Enter [Wildbeast Forest - 1]', 'warning_amber'),
    mkOpt('Leave the village'),                         // FORWARD, not the set
    mkOpt('Leave the safe path'),                       // FORWARD, not the set
    mkOpt('Fast Travel - Act 1'),                       // neither: keep signpost
  ];
}

// Runs the shipped function twice (idempotency) under `env`.
function run(env) {
  const opts = mkOpts();
  const document = { querySelectorAll: () => opts };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const MIRROR_RETURN_ICONS = env.mirror;
  const REPLACE_TRAVEL_ICON = env.replace;
  const TRAVEL_ICON = SHIPPED_ICON;
  eval(reSrc + '\n' + fnBody);
  mirrorReturnIcons();
  mirrorReturnIcons();
  return opts;
}

const pad = (v, n) => String(v).padEnd(n);

// ---- everything on: the shipped configuration -----------------------------
const opts = run({ master: true, mirror: true, replace: true });
console.log(pad('ARROW', 10) + pad('glyph was', 15) + pad('glyph now', 15) + 'label');
for (const o of opts) {
  console.log(pad(o._icon.style.transform === 'scaleX(-1)' ? 'MIRRORED' : 'as-is', 10) +
              pad(o._orig, 15) + pad(o._icon.textContent, 15) + o._label);
}

// warning_amber must never be swapped - it is a hazard marker, not a direction
const kept = opts.filter((o) => o._orig === 'warning_amber')
                 .every((o) => o._icon.textContent === 'warning_amber');
console.log('\nwarning_amber preserved : ' + (kept ? 'YES' : 'NO'));

// ---- direction, against the real label set --------------------------------
let bad = 0;
function expect(what, got, want) {
  const ok = got === want;
  if (!ok) bad++;
  console.log('   ' + (ok ? 'ok  ' : 'FAIL') + ' ' + pad(what, 34) +
              JSON.stringify(got) + (ok ? '' : '   want ' + JSON.stringify(want)));
}
const by = (label) => opts.find((o) => o._label === label);
const mirrored = (label) => by(label)._icon.style.transform === 'scaleX(-1)';

console.log('\ndirection');
for (const l of ['Climb out', 'Give up', 'Leave the Crypt',
                 'Take the side path, return to the Camp']) {
  expect('backward: ' + l, mirrored(l), true);
}
// The whole reason the set is enumerated rather than a ^Leave prefix.
expect('FORWARD: Leave the village', mirrored('Leave the village'), false);
expect('FORWARD: Leave the safe path', mirrored('Leave the safe path'), false);
expect('FORWARD: Go to […]', mirrored('Go to [Qingye Riverbank]'), false);

// Jumps teleport you to a remembered place: neither forward nor back, so they
// keep the game's signpost AND stay unmirrored. Quick Return is the one that
// has to be checked explicitly - its label starts with a word the backward
// rule used to claim.
console.log('\njumps keep the signpost, unmirrored');
for (const l of ['Fast Travel - Act 1', "Quick Return [Neko's Room]"]) {
  expect('glyph not swapped: ' + l, by(l)._icon.textContent, 'directions');
  expect('not mirrored: ' + l, mirrored(l), false);
}
expect('combat Quick Return not mirrored',
       mirrored('Quick Return [Wildbeast Forest]'), false);

// ---- the toggle matrix ----------------------------------------------------
// The two behaviours share one function, so each has to be shown INDEPENDENT
// of the other: mirroring off must not disable the glyph swap, and vice versa.
// A `return` in the wrong place would still pass the all-on case above.
//
// Looked up BY LABEL, never by index: adding a row to the fixture used to shift
// every positional assertion under it and fail something unrelated.
const RETURN = 'Return to the Camp';
const FORWARD = 'Go to [Qingye Riverbank]';
const pick = (o, label) => o.find((x) => x._label === label)._icon;

console.log('\nmirror=on  replace=off');
let o = run({ master: true, mirror: true, replace: false });
expect('Return glyph (game\'s own kept)', pick(o, RETURN).textContent, 'directions');
expect('Return arrow still mirrored', pick(o, RETURN).style.transform, 'scaleX(-1)');

console.log('\nmirror=off replace=on');
o = run({ master: true, mirror: false, replace: true });
expect('Return glyph swapped', pick(o, RETURN).textContent, SHIPPED_ICON);
expect('Return arrow NOT mirrored', pick(o, RETURN).style.transform, undefined);
expect('forward option swapped too', pick(o, FORWARD).textContent, SHIPPED_ICON);

console.log('\nmirror=off replace=off');
o = run({ master: true, mirror: false, replace: false });
expect('glyph untouched', pick(o, RETURN).textContent, 'directions');
expect('transform untouched', pick(o, RETURN).style.transform, undefined);

console.log('\nENABLE_VISUAL_OVERRIDES=false, both sub-toggles on');
o = run({ master: false, mirror: true, replace: true });
expect('glyph untouched', pick(o, RETURN).textContent, 'directions');
expect('transform untouched', pick(o, RETURN).style.transform, undefined);

// ---- colorRestTravel ------------------------------------------------------
// Same travel options, but keyed off data-travel rather than the label - so
// unlike mirrorReturnIcons this is unaffected by ENABLE_PROSE.
const restSrc =
    src.slice(src.indexOf('    const REST_LOCATIONS = new Set(['),
              src.indexOf(']);', src.indexOf('const REST_LOCATIONS')) + 3) + '\n' +
    src.slice(src.indexOf('    function colorRestTravel() {'),
              src.indexOf('\n    }\n',
                          src.indexOf('    function colorRestTravel() {')) + 7);
const SHIPPED_REST_COLOR =
    eval(src.match(/const REST_TRAVEL_COLOR = [^;]+/)[0].split('=')[1]);

function mkLink(travel, cls) {
  return { _cls: cls || 'travel_normal', style: {},
           getAttribute: (a) => (a === 'data-travel' ? travel : null) };
}
function runRest(links, env) {
  env = env || { master: true, on: true };
  const document = {
    // Model the selector: .travel_normal only, so a combat link is never seen.
    querySelectorAll: () => links.filter((l) => l._cls === 'travel_normal'),
  };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const HIGHLIGHT_REST_TRAVEL = env.on;
  const REST_TRAVEL_COLOR = SHIPPED_REST_COLOR;
  eval(restSrc);
  colorRestTravel();
  colorRestTravel();             // idempotency: same value, no drift
  return links;
}

console.log('\ncolorRestTravel');
// 狩猎大赛·补给点 is the reported case; 纳家大厅 is the hall next door, no bed.
let L = [mkLink('狩猎大赛·补给点'), mkLink('纳家大厅'),
         mkLink('纳可的房间'), mkLink('燕岗矿井', 'travel_combat')];
runRest(L);
expect('rest destination coloured', L[0].style.color, SHIPPED_REST_COLOR);
expect('non-rest destination untouched', L[1].style.color, undefined);
expect('second rest destination coloured', L[2].style.color, SHIPPED_REST_COLOR);
expect('combat link never visited', L[3].style.color, undefined);
L = runRest([mkLink('狩猎大赛·补给点')], { master: true, on: false });
expect('toggle off: untouched', L[0].style.color, undefined);
L = runRest([mkLink('狩猎大赛·补给点')], { master: false, on: true });
expect('master off: untouched', L[0].style.color, undefined);

// The colour must MATCH the game's own quick-return-to-bed link, which
// display.js hard-codes inline. Read from the game source, so this fails if
// the game ever recolours it and ours silently stops matching.
const disp = fs.readFileSync('../NekoRPG/src/display.js', 'utf8');
const bedColor = (disp.match(/快速返回 \[\$\{last_bed/) &&
                  disp.match(/color:(#[0-9a-fA-F]{6})"><i class="material-icons">directions<\/i> 快速返回 \[\$\{last_bed/));
expect('matches the game\'s bed-link colour',
       bedColor && bedColor[1].toLowerCase(), SHIPPED_REST_COLOR.toLowerCase());

// The set is generated by slicing locations.js, and the failure mode is
// UNDER-matching: a definition that stops fitting the slice just drops out and
// its link quietly loses the colour. Cross-check the count against the raw
// number of sleeping blocks, independently of the build's own check.
const locjs = fs.readFileSync('../NekoRPG/src/locations.js', 'utf8');
const sleepBlocks = (locjs.match(/\bsleeping:\s*\{/g) || []).length;
const shippedSet = eval(
    src.slice(src.indexOf('    const REST_LOCATIONS = new Set(['),
              src.indexOf(']);', src.indexOf('const REST_LOCATIONS')) + 3)
       .replace('const REST_LOCATIONS =', ''));
expect('every sleeping block is in the set', shippedSet.size, sleepBlocks);
expect('  including the reported one',
       shippedSet.has('狩猎大赛·补给点'), true);

if (!kept) bad++;
console.log('\n' + (bad ? bad + ' FAILURES' : 'all toggle combinations correct'));
process.exit(bad ? 1 : 0);
