// nbspLocationNames() and highlightBestiaryLinks(), against mock elements.
// Cosmetic behaviour lives in JS and the Python suite cannot reach it.
// Run against a BUILT script:  node uitest_visuals.js ../Script.txt
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8').split('\r\n').join('\n');

// Anchors on the '(' rather than '() {' so functions that take parameters
// (bestiaryActColor(row)) can be sliced too.
function slice(name) {
  const s = src.slice(src.indexOf('    function ' + name + '('));
  const end = s.indexOf('\n    }\n');
  if (end === -1) throw new Error('could not slice ' + name);
  return s.slice(0, end + 7);
}
// read the shipped colour, so this cannot pass on a stale value
const SHIPPED_COLOR =
    eval(src.match(/const BESTIARY_LINK_COLOR = [^;]+/)[0].split('=')[1]);
// The act palette, read from the built file so these cannot pass on stale hexes.
const ACT_COLORS = eval(
    src.slice(src.indexOf('const BESTIARY_ACT_COLORS = ['),
              src.indexOf('];', src.indexOf('const BESTIARY_ACT_COLORS')) + 2)
       .replace('const BESTIARY_ACT_COLORS =', '').replace(/;$/, ''));

const nbspSrc = slice('nbspLocationNames');
const bestSrc = src.match(/const ZONE_ROW_CLASS = [^\n]+/)[0] + '\n' +
                slice('highlightBestiaryLinks') + '\n' +
                slice('bestiaryActColor');
const NB = ' ';
// JSON.stringify emits the NBSP as itself (indistinguishable from a space on
// screen) and returns undefined - not a string - for undefined. Handle both.
const show = (s) => String(JSON.stringify(s)).split(' ').join('~');

let bad = 0;
function expect(what, got, want) {
  const ok = got === want;
  if (!ok) bad++;
  console.log('  ' + (ok ? 'ok  ' : 'FAIL') + ' ' + String(what).padEnd(38) +
              show(got) + (ok ? '' : '   want ' + show(want)));
}

// ---- nbspLocationNames ----------------------------------------------------
// Every space becomes NBSP, separators included: the name must never wrap.
// Text is all this touches - no sizing, no clipping - so the mock is just a
// textContent holder, and a style write would show up as an unexpected key.
function runNbsp(text, env) {
  env = env || { master: true, nbsp: true };
  const el = { textContent: text, style: {} };
  const document = { getElementById: (id) => (id === 'location_name_span' ? el : null) };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const NBSP_LOCATION_NAMES = env.nbsp;
  eval(nbspSrc);
  nbspLocationNames();
  nbspLocationNames();          // idempotency
  return el;
}

console.log('nbspLocationNames  (~ = NBSP; no plain space may survive)');
expect('· joined too',
       runNbsp('Illusory Realm Core · Barrier Lake').textContent,
       'Illusory' + NB + 'Realm' + NB + 'Core' + NB + '·' + NB + 'Barrier' + NB + 'Lake');
expect('- joined too',
       runNbsp('Wildbeast Forest - 1').textContent,
       'Wildbeast' + NB + 'Forest' + NB + '-' + NB + '1');
expect('longest name in the game',
       runNbsp('Hunting Tournament · Ancient Tomb Battle').textContent.indexOf(' '),
       -1);
expect('single word untouched', runNbsp('Village').textContent, 'Village');
expect('no-space name untouched', runNbsp('燕岗城').textContent, '燕岗城');
expect('toggle off',
       runNbsp('Barrier Lake', { master: true, nbsp: false }).textContent,
       'Barrier Lake');
expect('master off',
       runNbsp('Barrier Lake', { master: false, nbsp: true }).textContent,
       'Barrier Lake');
// The pass must not touch presentation at all - it joins text and stops.
expect('no style written',
       Object.keys(runNbsp('Hunting Tournament · Ancient Tomb Battle').style).length,
       0);

// ---- highlightBestiaryLinks ----------------------------------------------
// Only ZONE rows are links. display.js gives them a <div onclick> inside
// .bestiary_entry_name; enemy rows have no such div and must stay untouched.
function mkRow(hasLink, bestiaryAttr) {
  const link = hasLink ? { style: {} } : null;
  const name = { querySelector: (s) => (s === 'div[onclick]' ? link : null) };
  const count = { style: {} };
  const set = new Set();
  return {
    querySelector: (s) => (s === '.bestiary_entry_name' ? name :
                           s === '.bestiary_entry_kill_count' ? count : null),
    getAttribute: (a) => (a === 'data-bestiary' ? bestiaryAttr : null),
    classList: { add: (c) => set.add(c), contains: (c) => set.has(c) },
    _link: link, _count: count, _classes: set,
  };
}

function runBest(env, zoneAttr) {
  // -4200 is zone 41 -> Act 4, the row from the reported DOM.
  const rows = [mkRow(true, zoneAttr === undefined ? '-4200' : zoneAttr),
                mkRow(false, '-47')];            // one zone row, one enemy row
  const document = { querySelectorAll: () => rows };
  const ENABLE_VISUAL_OVERRIDES = env === undefined ? true : env.master;
  const HIGHLIGHT_BESTIARY_LINKS = env === undefined ? true : env.on;
  // The Zones tab filters on the same marker this pass sets, so the two are
  // coupled: default it off, and test the on-case explicitly below.
  const ZONES_TAB = env === undefined ? false : !!env.zones;
  const BESTIARY_LINK_COLOR = SHIPPED_COLOR;
  const BESTIARY_ACT_COLORS = ACT_COLORS;
  eval(bestSrc);
  highlightBestiaryLinks();
  highlightBestiaryLinks();     // idempotency
  return { zone: rows[0], enemy: rows[1] };
}

console.log('\nhighlightBestiaryLinks  (act palette ' + ACT_COLORS.join(' ') + ')');
let r = runBest();
expect('zone link takes its ACT colour', r.zone._link.style.color, ACT_COLORS[3]);
expect('act number matches the name', r.zone._count.style.color, ACT_COLORS[3]);

// The act arithmetic, against real data-bestiary values: -100*(zone+1).
// One row per act, including both ends of each act's zone range.
console.log('  act derivation from data-bestiary');
[['-1200', 11, 1], ['-1600', 15, 1], ['-2200', 21, 2], ['-2900', 28, 2],
 ['-3200', 31, 3], ['-4200', 41, 4], ['-4900', 48, 4], ['-5200', 51, 5],
 ['-6200', 61, 6], ['-6900', 68, 6]].forEach(function (t) {
  const got = runBest(undefined, t[0]).zone._link.style.color;
  expect('  ' + t[0] + ' -> zone ' + t[1] + ', act ' + t[2], got, ACT_COLORS[t[2] - 1]);
});
// Act 1 must NOT be white - that is what every enemy row already is.
expect('  act 1 is not white', ACT_COLORS[0].toLowerCase() === '#ffffff', false);
// Unreadable attribute falls back rather than throwing or painting undefined.
expect('  missing attr -> fallback', runBest(undefined, null).zone._link.style.color,
       SHIPPED_COLOR);
expect('  junk attr -> fallback', runBest(undefined, 'x').zone._link.style.color,
       SHIPPED_COLOR);
expect('zone link is a pointer', r.zone._link.style.cursor, 'pointer');
// The one that matters: an enemy row shares the class and must not be painted.
expect('ENEMY row untouched', r.enemy._count.style.color, undefined);

expect('zone row marked for the tab', r.zone._classes.has('tl_zone_row'), true);
expect('ENEMY row not marked', r.enemy._classes.has('tl_zone_row'), false);

r = runBest({ master: true, on: false });
expect('toggle off', r.zone._link.style.color, undefined);
// The coupling introduced with the Zones tab: turning the COLOUR off must not
// stop the marking, or the tab would filter down to an empty list.
r = runBest({ master: true, on: false, zones: true });
expect('colour off + tab on -> still marked',
       r.zone._classes.has('tl_zone_row'), true);
expect('colour off + tab on -> not coloured', r.zone._link.style.color, undefined);
r = runBest({ master: false, on: true });
expect('master off', r.zone._link.style.color, undefined);

// ---- annotateXpGain -------------------------------------------------------
// Appends a scientific form to the tooltip's XP multiplier. Read the threshold
// from the built file so this cannot pass on a stale value.
// Both annotators share sciShort(), so it has to come along in the slice.
const xpSrc = src.match(/const XP_GAIN_VALUE_RE = [^\n]+/)[0] + '\n' +
              slice('sciShort') + '\n' + slice('annotateXpGain');
const SCI_MIN = eval(src.match(/const XP_GAIN_SCI_MIN = ([^;]+)/)[1]);

function runXp(text, env) {
  env = env || { master: true, on: true };
  const node = { nodeType: 3, textContent: text };
  const el = { firstChild: node };
  const document = { querySelectorAll: () => [el] };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const XP_GAIN_SCIENTIFIC = env.on;
  const XP_GAIN_SCI_MIN = SCI_MIN;
  eval(xpSrc);
  annotateXpGain();
  annotateXpGain();            // idempotency: must not append twice
  return node.textContent;
}

console.log('\nannotateXpGain  (threshold ' + SCI_MIN + ')');
expect('the reported case', runXp('XP Gain: x1704855.1'),
       'XP Gain: x1704855.1 (x1.7e6)');
expect('large integer', runXp('XP Gain: x250000'),
       'XP Gain: x250000 (x2.5e5)');
expect('huge value', runXp('XP Gain: x9876543210.5'),
       'XP Gain: x9876543210.5 (x9.88e9)');
// Below the threshold the annotation would be longer than the number.
expect('small value untouched', runXp('XP Gain: x1.6'), 'XP Gain: x1.6');
expect('at threshold', runXp('XP Gain: x100000'), 'XP Gain: x100000 (x1e5)');
expect('just under threshold', runXp('XP Gain: x99999.9'), 'XP Gain: x99999.9');
// Matched on the number, not the label, so it survives ENABLE_PROSE=false.
expect('untranslated label still works', runXp('经验获取: x1704855.1'),
       '经验获取: x1704855.1 (x1.7e6)');
expect('toggle off', runXp('XP Gain: x1704855.1', { master: true, on: false }),
       'XP Gain: x1704855.1');
expect('master off', runXp('XP Gain: x1704855.1', { master: false, on: true }),
       'XP Gain: x1704855.1');

// translateHot passes the ONE open tooltip as a root, so the annotation is
// restored in the same batch that rewrote the line. Prove the root is actually
// used for the query rather than ignored in favour of document.
(function () {
  const node = { nodeType: 3, textContent: 'XP Gain: x1704855.1' };
  let askedDocument = false;
  const root = { querySelectorAll: () => [{ firstChild: node }] };
  const document = { querySelectorAll: () => { askedDocument = true; return []; } };
  const ENABLE_VISUAL_OVERRIDES = true, XP_GAIN_SCIENTIFIC = true;
  const XP_GAIN_SCI_MIN = SCI_MIN;
  eval(xpSrc);
  annotateXpGain(root);
  expect('root scopes the query', node.textContent,
         'XP Gain: x1704855.1 (x1.7e6)');
  expect('  and document is not swept', askedDocument, false);
}());

// ---- prefixCraftingTiers --------------------------------------------------
// Runs against the REAL generated partTiers table, so these assertions are on
// the tiers actually shipped, not on a fixture that could drift from items.js.
const tierDictSrc = src.slice(
    src.indexOf('    const partTiers = Object.assign(Object.create(null), {'),
    src.indexOf('\n    });', src.indexOf('const partTiers')) + 8);
const tierSrc = src.match(/const PART_TIER_DONE_RE = [^\n]+/)[0] + '\n' +
                tierDictSrc + '\n' + slice('prefixCraftingTiers');

// sel picks which list the mock row belongs to: '.selectable_material' (parts,
// tier from the generated table) or '.selectable_component' (gear, tier from
// the element's own data-component_tier).
function runTier(name, env, sel, tierAttr) {
  env = env || { master: true, on: true };
  sel = sel || '.selectable_material';
  const node = { nodeType: 3, textContent: name };
  const row = {
    querySelector: (s) => (s === '.material-icons' ? { nextSibling: node } : null),
    getAttribute: (a) => (a === 'data-component_tier' ? tierAttr : null),
  };
  const document = { querySelectorAll: (s) => (s === sel ? [row] : []) };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const CRAFTING_TIER_PREFIX = env.on;
  eval(tierSrc);
  prefixCraftingTiers();
  prefixCraftingTiers();       // idempotency: must not stack "T16 · T16 · "
  return node.textContent;
}
const runGear = (name, tierAttr, env) =>
  runTier(name, env, '.selectable_component', tierAttr);

console.log('\nprefixCraftingTiers  (against the shipped partTiers table)');
expect('weapon part', runTier('Skybreaker Wheel Hub'), 'T16 · Skybreaker Wheel Hub');
// The reported bug: an ARMOR part. Its tooltip takes the equippable branch and
// never prints a tier, so the old tooltip-reading version called this T0.
expect('armor part is NOT T0', runTier('Phantom Rune Vest'), 'T16 · Phantom Rune Vest');
expect('armor part (hat)', runTier('Phantom Rune Hat'), 'T16 · Phantom Rune Hat');
// ...and a genuine tier 0 still reads 0, which a falsy check would drop.
expect('real tier 0', runTier('Iron Sword Blade'), 'T0 · Iron Sword Blade');
// Base-game items are already English; their name is its own display key.
expect('english-named part', runTier('Iron hammer head'), 'T2 · Iron hammer head');
// Not a part at all - a raw material has no component_tier.
expect('plain material untouched', runTier('Skybreaker Violet Fern'),
       'Skybreaker Violet Fern');
// Chinese keys are kept too, so this works with ENABLE_PROSE off.
expect('untranslated name', runTier('幻符背心'), 'T16 · 幻符背心');
// The game rebuilds this list constantly, so re-prefixing must be a no-op -
// including for T0, whose prefix has to survive the same guard.
expect('already prefixed', runTier('T16 · Skybreaker Wheel Hub'),
       'T16 · Skybreaker Wheel Hub');
expect('already prefixed T0', runTier('T0 · Iron Sword Blade'),
       'T0 · Iron Sword Blade');
expect('toggle off', runTier('Skybreaker Wheel Hub', { master: true, on: false }),
       'Skybreaker Wheel Hub');
expect('master off', runTier('Skybreaker Wheel Hub', { master: false, on: true }),
       'Skybreaker Wheel Hub');

console.log('\n  gear list (tier from data-component_tier)');
const GEAR = 'Woven Reed Socks, 400%, x42834';
expect('the reported row', runGear(GEAR, '6'), 'T6 · ' + GEAR);
expect('tier 0 is a real tier', runGear(GEAR, '0'), 'T0 · ' + GEAR);
// display.js assigns item.component_tier unconditionally, so an item without
// one stringifies to "undefined" - it must not render as "Tundefined · ".
expect('missing tier -> untouched', runGear(GEAR, 'undefined'), GEAR);
expect('empty tier -> untouched', runGear(GEAR, ''), GEAR);
expect('null attr -> untouched', runGear(GEAR, null), GEAR);
expect('already prefixed', runGear('T6 · ' + GEAR, '6'), 'T6 · ' + GEAR);
expect('gear toggle off', runGear(GEAR, '6', { master: true, on: false }), GEAR);
expect('gear master off', runGear(GEAR, '6', { master: false, on: true }), GEAR);

// ---- fitLootNames ---------------------------------------------------------
// Only names long enough to WRAP may get the tighter line-height; applying it
// to a one-liner shifts it off the baseline that .loot_slot_div's 20px row and
// .loot_name's -4px margin were tuned for. That is the v11.9 regression.
const lootSrc = [
  src.match(/const LOOT_NAME_W = [^\n]+/)[0],
  src.match(/const LOOT_NAME_WRAP_LEN = [^\n]+/)[0],
  src.match(/let lootCtx;[^\n]*/)[0],
  src.match(/let lootFont = [^\n]+/)[0],
  slice('lootWraps'),
  slice('fitLootNames'),
].join('\n');
const WRAP_LEN = parseInt(src.match(/const LOOT_NAME_WRAP_LEN = (\d+)/)[1], 10);
const LOOT_W = parseInt(src.match(/const LOOT_NAME_W = (\d+)/)[1], 10);
const CJK_SRC = src.match(/const CJK_RE = [^\n]+/)[0];

// Arial advance widths, units per 1000 em - the real metrics, so measureText
// here answers what the browser would. Only the glyphs the fixtures use.
const ARIAL = { ' ': 278, '·': 350,
  A: 667, B: 667, C: 722, D: 722, E: 667, F: 611, G: 778, I: 278, M: 833,
  P: 667, S: 667, W: 944, Y: 667,
  a: 556, b: 556, c: 500, d: 556, e: 556, f: 278, g: 556, h: 556, i: 222,
  k: 500, l: 222, m: 833, n: 556, o: 556, p: 556, r: 333, s: 500, t: 278,
  u: 556, v: 500, w: 722, y: 500 };
function arialWidth(text, px) {
  let u = 0;
  for (const ch of text) {
    if (!(ch in ARIAL)) throw new Error('no Arial metric for ' + JSON.stringify(ch));
    u += ARIAL[ch];
  }
  return u * px / 1000;
}

function runLoot(texts, env) {
  env = env || {};
  const els = texts.map((t) => ({ textContent: t, style: {}, dataset: {} }));
  const document = {
    querySelectorAll: () => els.filter((e) => e.dataset.tlFit === undefined),
    // env.noCanvas models a browser without 2d canvas, which must fall back to
    // the old character count rather than deciding nothing.
    createElement: () => ({
      getContext: () => (env.noCanvas ? null : {
        font: '',
        measureText(t) {
          // The font string the code built has to be usable, or the real
          // canvas would silently keep its 10px sans-serif default and every
          // name would measure short - the same bug in a new place.
          const m = /(\d+)px/.exec(this.font);
          if (!m) throw new Error('unusable font string: ' + this.font);
          return { width: arialWidth(t, Number(m[1])) };
        },
      }),
    }),
  };
  const window = {
    getComputedStyle: () => ({ fontStyle: 'normal', fontWeight: '400',
                               fontSize: '16px', fontFamily: 'Arial' }),
  };
  eval(CJK_SRC + '\n' + lootSrc);
  fitLootNames();
  fitLootNames();              // idempotency
  return els;
}

console.log('\nfitLootNames  (wraps past ' + LOOT_W + 'px)');
const LONG = 'Intermediate Evolution Crystal Fragment';
// THE regression case, v14.9. Both of these are exactly 27 characters, so no
// character count can separate them - and they must be separated: the first
// renders ~203px and wraps, the second ~196px and does not.
const WIDE = 'Dust · Ferocious Beast Meat';
const EDGE = 'Intermediate Evolution Crys';
expect('the two 27-char names are the same length',
       WIDE.length === EDGE.length && WIDE.length === WRAP_LEN, true);
expect('  but not the same width', arialWidth(WIDE, 16) > LOOT_W &&
       arialWidth(EDGE, 16) <= LOOT_W, true);
let els = runLoot([LONG, EDGE, 'Iron Ingot', 'Wolf Pelt', '中等进化结晶碎片', WIDE]);
expect('long name gets 12px', els[0].style.lineHeight, '12px');
// Wide-but-short: the case the character count got wrong.
expect('wide 27-char name gets 12px', els[5].style.lineHeight, '12px');
// Narrow-and-short: applying it here is the v11.9 regression.
expect('narrow 27-char name untouched', els[1].style.lineHeight, undefined);
expect('short name untouched', els[2].style.lineHeight, undefined);
expect('short name untouched (2)', els[3].style.lineHeight, undefined);
// An untranslated name must NOT be decided yet - the Chinese is short and
// would lock in "fits" forever.
expect('untranslated left undecided', els[4].dataset.tlFit, undefined);
expect('untranslated not styled', els[4].style.lineHeight, undefined);
// Decided rows are marked, so the selector skips them on later scans.
// Joined, not as arrays: expect() compares with ===, which is reference
// equality for arrays and would fail on two identical-looking lists.
expect('decided rows marked',
       [els[0].dataset.tlFit, els[2].dataset.tlFit].join(','), '1,1');
// Once translated on a later scan, it is decided normally.
els[4].textContent = LONG;
const doc2 = els.filter((e) => e.dataset.tlFit === undefined);
expect('undecided row picked up later', doc2.length, 1);
runLoot([LONG]);   // sanity: same input, same answer
expect('width is the shipped value', LOOT_W, 200);

// No canvas: fall back to the character count rather than deciding nothing.
// Wrong for WIDE, which is the bug being fixed - but a browser this old is
// hypothetical, and a wrong answer beats every long name overflowing.
const fb = runLoot([LONG, EDGE, WIDE], { noCanvas: true });
expect('no canvas: long name still handled', fb[0].style.lineHeight, '12px');
expect('no canvas: falls back to the count', fb[2].style.lineHeight, undefined);


// ---- digging panel: the conversion button fits on one line -----------------
// #location_related_div is 400px and this <b> is the widest thing in it. At
// Arial BOLD 16px "[Convert Heart of the Illusory Realm to material version]"
// measured 425px, so it wrapped - and the second line pushed [Leave] below the
// panel, out of the game window entirely.
//
// Measured, not counted. The character count cannot decide this: the same 48
// characters run 60px apart depending on how many m/w/capitals they hold,
// which is the whole reason fitLootNames measures rather than counts.
const ARIAL_BOLD = { ' ': 278, '[': 333, ']': 333, '\u00b7': 350,
  C: 722, H: 722, I: 278, L: 611, M: 833, R: 722, S: 722, T: 611, V: 667,
  a: 556, b: 611, c: 556, d: 611, e: 556, f: 333, g: 611, h: 611, i: 278,
  l: 278, m: 889, n: 611, o: 611, p: 611, r: 389, s: 556, t: 333, u: 611,
  v: 556, y: 556 };
function boldWidth(text, px) {
  let u = 0;
  for (const ch of text) {
    if (!(ch in ARIAL_BOLD)) throw new Error('no Arial Bold metric for ' +
                                             JSON.stringify(ch));
    u += ARIAL_BOLD[ch];
  }
  return u * px / 1000;
}
console.log('\ndigging panel conversion button');
{
  // 400px panel, less the padding the game puts around the span.
  const PANEL = 390;
  const i = src.indexOf('const proseFrag = Object.assign');
  const body = src.slice(i, src.indexOf('\n    });', i));
  const row = /^        '((?:[^'\\]|\\.)*)': '((?:[^'\\]|\\.)*)',$/gm;
  const found = [];
  let m;
  while ((m = row.exec(body))) {
    if (/^\[Convert Heart of the /.test(m[2])) found.push(m[2]);
  }
  expect('both conversion buttons present', found.length, 2);
  found.forEach((label) => {
    const w = boldWidth(label, 16);
    expect('  fits 390px: ' + label.slice(9, 34), w <= PANEL, true);
    console.log('       (' + w.toFixed(0) + 'px) ' + label);
  });
  // The exact string that broke it, pinned as a negative: if anyone restores
  // "version" this fails with the real number rather than a vague warning.
  expect('  the old wording would NOT have fit',
         boldWidth('[Convert Heart of the Illusory Realm to material version]', 16)
             > PANEL, true);
}

// ---- family panel: soft-cap lines fit on one line -------------------------
// #skills_and_stances_div is 400px wide and #family_div has a permanent
// scrollbar, so these spans get roughly 383px. At the panel's font that is
// about 53 characters, which is where the original wording broke - it put
// "cap (^1.5)" on a second line, doubling the height of all three.
//
// A budget rather than an exact string: the wording is editorial and may well
// change again, but it must not grow back past the width. 50 leaves a little
// room for the threshold token, which is the part that varies (10,000 is the
// longest of the three).
const SOFTCAP_MAX = 50;
const softCapLines = [];
{
  const i = src.indexOf("const proseExact = Object.assign");
  const body = src.slice(i, src.indexOf('\n    });', i));
  const row = /^        '((?:[^'\\]|\\.)*)': '((?:[^'\\]|\\.)*)',$/gm;
  let m;
  while ((m = row.exec(body))) {
    // Anchored: 'soft cap' alone also matches a gem-ingot description and
    // a fragment of the altar readout, neither of which lives in this panel.
    if (/^Newborns over .*soft cap/.test(m[2])) softCapLines.push(m[2]);
  }
}
console.log('\nfamily soft-cap lines');
expect('all three present', softCapLines.length, 3);
softCapLines.forEach((line) => {
  const plain = line.replace(/<[^>]*>/g, '');
  expect('  fits: ' + plain.slice(0, 26), plain.length <= SOFTCAP_MAX, true);
  console.log('       (' + plain.length + ' chars) ' + plain);
});

// ---- breakRealmNames ------------------------------------------------------
// "Sky-Tier Rank 1" -> two lines. The tier list is generated from main.js
// realm_rate; the SKIP list is an editorial choice living in the toggles.
// NB_SPACE/NB_HYPHEN must be eval'd in the SAME string as the function: a
// const does not leak out of an eval, so declaring them separately would
// leave breakRealmNames throwing ReferenceError the moment it reached a
// skipped tier - which is exactly what it did the first time.
const realmSrc =
    src.slice(src.indexOf('    const REALM_TIERS = new Set(['),
              src.indexOf(']);', src.indexOf('const REALM_TIERS')) + 3) + '\n' +
    src.match(/const NB_SPACE = '[^']+';/)[0] + '\n' +
    src.match(/const NB_HYPHEN = '[^']+';/)[0] + '\n' +
    slice('breakRealmNames');
const SKIP = eval(src.match(/const FAMILY_REALM_BREAK_SKIP = (\[[^\]]*\])/)[1]);
const TIERS = eval(
    src.slice(src.indexOf('    const REALM_TIERS = new Set(['),
              src.indexOf(']);', src.indexOf('const REALM_TIERS')) + 3)
       .replace('const REALM_TIERS =', ''));

function runRealm(texts, env) {
  env = env || { master: true, on: true };
  const cells = texts.map((t) => ({ textContent: t }));
  const document = { querySelectorAll: () => cells };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const FAMILY_REALM_BREAK = env.on;
  const FAMILY_REALM_BREAK_SKIP = SKIP;
  eval(realmSrc);
  breakRealmNames();
  breakRealmNames();           // idempotency: must not break twice
  return cells.map((c) => c.textContent);
}

const NBSP = String.fromCharCode(0xa0);
const NBHY = String.fromCharCode(0x2011);
console.log('\nbreakRealmNames');
let rn = runRealm(['Sky-Tier Rank 1', 'All-Things-Tier Basic', 'Realm',
                   '天空级一阶', 'Dust-Tier Intermediate', 'Skyhigh-Tier Rank 8',
                   'All-Things-Tier High-Tier']);
expect('tier broken onto its own line', rn[0], 'Sky-Tier\nRank 1');
// v18.1: a skipped tier is NOT left alone - it is GLUED, so the wrap lands
// on the tier name's own hyphen instead of inside the rank.
expect('skipped tier glued, not broken', rn[1], 'All-Things-Tier' + NBSP + 'Basic');
expect('header has no space, untouched', rn[2], 'Realm');
// Untranslated: the cell still says 天空级一阶, which has no space at all - but
// even if it had, the tier would not be in the set. A later batch gets it once
// the prose pass has been past.
expect('untranslated left for later', rn[3], '天空级一阶');
expect('second tier broken', rn[4], 'Dust-Tier\nIntermediate');
expect('two-digit rank broken', rn[5], 'Skyhigh-Tier\nRank 8');
// The case that prompted this: left alone, the browser wrapped at the hyphen
// INSIDE the rank and orphaned "Tier" on line two.
expect('  hyphenated rank glued whole', rn[6],
       'All-Things-Tier' + NBSP + 'High' + NBHY + 'Tier');
expect('  no breakable space survives', rn[6].indexOf(' '), -1);
// The TIER's own hyphens stay ordinary - they are the break we want left.
expect('  tier hyphens still breakable', rn[6].split('-').length, 3);
rn = runRealm(['Sky-Tier Rank 1'], { master: true, on: false });
expect('toggle off: untouched', rn[0], 'Sky-Tier Rank 1');
rn = runRealm(['Sky-Tier Rank 1'], { master: false, on: true });
expect('master off: untouched', rn[0], 'Sky-Tier Rank 1');

// A skip entry that is not a real tier would be a silent no-op - the row would
// just break anyway, and nothing would say why.
expect('every skipped tier is a real tier',
       SKIP.every((t) => TIERS.has(t)), true);
expect('  and the skip is the requested one', SKIP.join(','), 'All-Things-Tier');
// All seven tiers from realm_rate, so a newly added one cannot be missed.
expect('tier set is complete', TIERS.size, 7);

// The newline only renders as a break because of this rule. Without it the
// cell shows "Sky-Tier Rank 1" on one line and the whole pass is invisible.
// Sliced to styleOverrides: searching the whole file matches the changelog.
const CSS = (function () {
  const i = src.indexOf('styleOverrides.textContent = `');
  return src.slice(i, src.indexOf('`;', i));
})();
const realmRule = CSS.match(
    /#family_member_list \.member_list_realm\s*\{([\s\S]*?)\}/);
expect('realm cell rule exists', Boolean(realmRule), true);
expect('  carries white-space: pre-line',
       Boolean(realmRule && /white-space:\s*pre-line/.test(realmRule[1])), true);

// ---- stampMessages --------------------------------------------------------
// Driven off the observer's records, so the fixture is a record list, not a
// DOM query. The skip list is the editorial half and lives in the toggles.
const stampSrc = [
  src.match(/const MSG_LOG_ID = [^\n]+/)[0],
  src.match(/const MSG_STACKED_CLASS = [^\n]+/)[0],
  src.match(/let msgLog = [^\n]+/)[0],
  slice('pad2'),
  slice('stampNow'),
  slice('stampMessages'),
].join('\n');
const SKIP_GROUPS = eval(src.match(/const MESSAGE_TIMESTAMP_SKIP = (\[[^\]]*\])/)[1]);

function mkMsg(groups) {
  const set = new Set(['message_common'].concat(groups || []));
  const attrs = {};
  return { nodeType: 1,
           classList: { contains: (c) => set.has(c), add: (c) => set.add(c) },
           hasAttribute: (a) => a in attrs,
           setAttribute: (a, v) => { attrs[a] = v; },
           _ts: () => attrs['data-tl-ts'],
           _has: (c) => set.has(c) };
}
function runStamp(nodes, env) {
  env = env || { master: true, on: true };
  const log = { _isLog: true };
  const document = { getElementById: (i) => (i === 'message_box_div' ? log : null) };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const MESSAGE_TIMESTAMPS = env.on;
  const MESSAGE_TIMESTAMP_DATE = Boolean(env.date);
  const MESSAGE_TIMESTAMP_SKIP = SKIP_GROUPS;
  eval(stampSrc);
  const records = [{ target: env.foreign ? {} : log, addedNodes: nodes }];
  stampMessages(records);
  stampMessages(records);      // idempotency: hasAttribute must hold it off
  return nodes.map((n) => n._ts && n._ts());
}

console.log('\nstampMessages');
const TS_RE = /^\d{2}:\d{2}:\d{2}$/;                 // time only, the default
const msgs = [mkMsg(['message_events']), mkMsg(['message_combat']),
              mkMsg(['message_loot']), mkMsg(['message_unlocks']),
              mkMsg(['message_crafting']), mkMsg(['message_background'])];
let ts = runStamp(msgs);
expect('events stamped', TS_RE.test(ts[0]), true);
expect('combat NOT stamped', ts[1], undefined);
expect('loot NOT stamped', ts[2], undefined);
expect('unlocks stamped', TS_RE.test(ts[3]), true);
expect('crafting stamped', TS_RE.test(ts[4]), true);
expect('background stamped', TS_RE.test(ts[5]), true);
// One reading per batch: messages added in the same task were logged in the
// same task, and giving them different seconds would be a lie about ordering.
expect('one reading shared across the batch', ts[0] === ts[3], true);
// Anything that is not a message element must be ignored - the observer sees
// every childList mutation in the document, not just this log's.
const junk = [{ nodeType: 3 }, mkMsg([]) ];
junk[1].classList = { contains: () => false };      // not .message_common
expect('non-elements and non-messages ignored',
       runStamp(junk).join(','), ',');
// Records whose target is some OTHER container must not be stamped, or every
// div added anywhere in the game would get a timestamp.
expect('records from elsewhere ignored',
       runStamp([mkMsg(['message_events'])], { master: true, on: true, foreign: true })[0],
       undefined);
expect('toggle off: unstamped',
       runStamp([mkMsg(['message_events'])], { master: true, on: false })[0], undefined);
expect('master off: unstamped',
       runStamp([mkMsg(['message_events'])], { master: false, on: true })[0], undefined);

// Zero-padded throughout, checked against a FIXED date rather than "now", so a
// single-digit day, month or hour cannot pass by accident on a two-digit one.
const RealDate = Date;
global.Date = function () { return new RealDate(2026, 7, 3, 9, 7, 2); };
expect('default format is HH:MM:SS',
       runStamp([mkMsg(['message_events'])])[0], '09:07:02');
// Date on: two lines, a real newline, date above time. The ::before renders it
// with white-space:pre, so the newline is the line break.
const dated = runStamp([mkMsg(['message_events'])], { master: true, on: true, date: true });
expect('date on: DD.MM.YYYY over HH:MM:SS', dated[0], '03.08.2026\n09:07:02');
global.Date = RealDate;
// The two lines are INTENTIONALLY unequal: the full 4-digit year makes the date
// line wider than the time line, and that ragged edge is the wanted look. An
// earlier draft used a 2-digit year to make them match, so this is asserted to
// stop it being "tidied" back.
expect('  date line deliberately longer than the time line',
       dated[0].split('\n')[0].length > dated[0].split('\n')[1].length, true);
// The class is what lets CSS tell the two layouts apart: it cannot ask whether
// an attribute value contains a newline.
const stackedMsg = mkMsg(['message_events']);
runStamp([stackedMsg], { master: true, on: true, date: true });
expect('date on: stacked class set', stackedMsg._has('tl_ts_stacked'), true);
const flatMsg = mkMsg(['message_events']);
runStamp([flatMsg]);
expect('date off: NOT stacked', flatMsg._has('tl_ts_stacked'), false);

expect('skip list is combat + loot', SKIP_GROUPS.join(','),
       'message_combat,message_loot');
// Without the ::before there is no visible timestamp at all - the attribute
// alone renders nothing.
const tsRule = CSS.match(/\.message_common\[data-tl-ts\]::before\s*\{([\s\S]*?)\}/);
expect('::before rule exists', Boolean(tsRule), true);
expect('  renders the attribute',
       Boolean(tsRule && /content:\s*attr\(data-tl-ts\)/.test(tsRule[1])), true);
expect('  at 10px', Boolean(tsRule && /font-size:\s*10px/.test(tsRule[1])), true);
// Without white-space:pre the newline collapses to a space and the stacked
// form silently renders on one line - the feature would look unimplemented.
expect('  white-space: pre for the stacked break',
       Boolean(tsRule && /white-space:\s*pre/.test(tsRule[1])), true);
expect('  base rule does not float',
       Boolean(tsRule && !/float/.test(tsRule[1])), true);
const stackRule = CSS.match(/\.message_common\.tl_ts_stacked::before\s*\{([\s\S]*?)\}/);
expect('stacked rule floats',
       Boolean(stackRule && /float:\s*left/.test(stackRule[1])), true);
// Lifts the stamp level with the message text; without it the block rides low
// against .message_common's 2px padding.
expect('  pulled up 4px',
       Boolean(stackRule && /margin-top:\s*-4px/.test(stackRule[1])), true);
// The float is a LOOK decision, not a layout accident: v15.6 made this an
// inline-block (cheaper - it costs only the first line box) and it was
// reverted in v15.7. .message_common is text-align:center, so a float is
// pinned to the panel's left edge and the stamps form a stable column, while
// an inline-block is centred with the first line of text and slides about with
// message length. Asserted so the cheaper version is not reintroduced as an
// optimisation.
expect('  not an inline-block (v15.6, reverted)',
       Boolean(stackRule && !/display:\s*inline-block/.test(stackRule[1])), true);

// ---- sciBigNumbers --------------------------------------------------------
// The rule is "lossless AND shorter", which is what makes it safe without a
// list of exceptions: a number carrying real precision is LONGER in scientific
// form and so declines itself.
const sciSrc = [
  src.match(/const SCI_MIN_DIGITS = [^\n]+/)[0],
  src.match(/const BIG_INT_RE = [^\n]+/)[0],
  slice('sciIfShorter'),
].join('\n');
eval(sciSrc);

console.log('\nsciIfShorter');
// Round numbers: every digit is recoverable from the exponent.
expect('9e11 from 12 digits', sciIfShorter('900000000000'), '9e11');
expect('1e12 from 13 digits', sciIfShorter('1000000000000'), '1e12');
expect('keeps a real mantissa', sciIfShorter('1500000'), '1.5e6');
expect('  and its digits', sciIfShorter('63000000'), '6.3e7');
// THE case this rule exists for. A kill count is all significant digits, so
// its scientific form is longer and it survives untouched.
expect('exact count left alone', sciIfShorter('63247689'), '63247689');
expect('  and another', sciIfShorter('123456789012'), '123456789012');
// Below 1e6 nothing is worth converting - "1e5" saves two characters and reads
// worse than 100000 at that size.
expect('under the floor untouched', sciIfShorter('100000'), '100000');
expect('at the floor converted', sciIfShorter('1000000'), '1e6');
// Lossless is the property that matters most: round-tripping must be exact.
let lossless = true;
['900000000000', '1000000000000', '1500000', '63000000', '1000000'].forEach((d) => {
  const out = sciIfShorter(d);
  if (out !== d && Number(out) !== Number(d)) lossless = false;
});
expect('every rewrite round-trips exactly', lossless, true);

// Scope. The kill counter is a bare Math.round() in .data_entry_value that the
// game deliberately leaves unformatted; this pass must be unable to see it.
const sciFn = src.slice(src.indexOf('    function sciBigNumbers() {'));
const sciBody = sciFn.slice(0, sciFn.indexOf('\n    }\n'));
expect('scoped to bestiary tooltips',
       /querySelectorAll\(\s*\n?\s*'\.bestiary_entry_tooltip/.test(sciBody), true);
expect('  cannot reach the Data tab counters',
       sciBody.indexOf('data_entry') === -1, true);
// Marking a tooltip that still holds Chinese would freeze it undecided: the
// rewritten digits would no longer match the proseExact key they belong to.
expect('  defers a tooltip still holding Chinese',
       /CJK_RE\.test\(tip\.textContent\)\)\s*continue/.test(sciBody), true);
expect('  decided once per tooltip',
       sciBody.indexOf('data-tl-sci') !== -1 &&
       sciBody.indexOf('dataset.tlSci') !== -1, true);
// Order is load-bearing, not incidental - see the guard above.
const scanBody = (function () {
  const f = src.slice(src.indexOf('    function scan() {'));
  return f.slice(0, f.indexOf('\n    }\n'));
})();
expect('runs after the prose pass',
       scanBody.indexOf('applyProseToPanels()') < scanBody.indexOf('sciBigNumbers()'), true);

console.log('\n' + (bad ? bad + ' FAILURES' : 'all correct'));
process.exit(bad ? 1 : 0);
