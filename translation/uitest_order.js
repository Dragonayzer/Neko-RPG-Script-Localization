// Pass ORDERING: the early exact pass vs the v4.0 `buttons` pairs.
// Run against a BUILT script:  node uitest_order.js ../Script.txt
//
// This exists because neither existing checker can see the bug it guards.
// verify_screenshot models applyProse ALONE, so it happily resolves a string
// that the buttons pass has already shredded in the real page - it would report
// green on exactly the failure a player sees. jscheck has the same blind spot.
// scan() order is: translateEarlyContainers() -> applySelector(buttons) ->
// applyProseToPanels(), and what matters is which of those touches a node first.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8').split('\r\n').join('\n');

function dict(name) {
  const i = src.indexOf('const ' + name + ' = Object.assign(Object.create(null), {');
  const j = src.indexOf('\n    });', i);
  const out = Object.create(null);
  const re = /^\s+'((?:[^'\\]|\\.)*)': '((?:[^'\\]|\\.)*)',$/gm;
  let m;
  const body = src.slice(i, j);
  while ((m = re.exec(body))) {
    out[m[1].replace(/\\'/g, "'")] = m[2].replace(/\\'/g, "'");
  }
  return out;
}
const proseExact = dict('proseExact');

// The pair list for one selector, in source order - order is the whole point.
function pairsFor(selector) {
  const key = "        '" + selector + "': [";
  const i = src.indexOf(key);
  if (i === -1) throw new Error('no pair list for ' + selector);
  const body = src.slice(i, src.indexOf('\n        ],', i));
  const out = [];
  const re = /\['((?:[^'\\]|\\.)*)',\s*'((?:[^'\\]|\\.)*)'\]/g;
  let m;
  while ((m = re.exec(body))) {
    out.push([m[1].replace(/\\'/g, "'"), m[2].replace(/\\'/g, "'")]);
  }
  return out;
}

// Which selectors the early exact pass covers, read from the built file.
const earlySel = eval(src.match(/const EARLY_PROSE_EXACT_SEL = ([^;]+)/)[1]);
const earlyClasses = earlySel.split(',').map((s) => s.trim());

// applySelector walks the list IN ORDER and applies EVERY match, so a short
// pair early in the list consumes text a longer one later would have matched.
function applyPairs(text, pairs) {
  for (const [zh, en] of pairs) {
    if (text.indexOf(zh) !== -1) text = text.split(zh).join(en);
  }
  return text;
}

const proseFrag = dict('proseFrag');
// Longest-first, as the built alternation is ordered.
const fragKeys = Object.keys(proseFrag).sort((a, b) => b.length - a.length);
function applyFrags(text) {
  for (const k of fragKeys) {
    if (text.indexOf(k) !== -1) text = text.split(k).join(proseFrag[k]);
  }
  return text;
}

const CJK = /[一-鿿]/;
let bad = 0;
// The full scan() order, all three stages. Modelling only the first two
// over-reports: a string the buttons pass leaves INTACT is still rescued by
// applyProseToPanels afterwards, and flagging those would be noise.
function check(what, selector, zh) {
  const covered = earlyClasses.indexOf(selector) !== -1;
  let text = zh;
  let via;
  if (covered && proseExact[text]) {
    text = proseExact[text];
    via = 'early exact';
  } else {
    text = applyPairs(text, pairsFor(selector));      // v4.0 buttons
    if (proseExact[text]) { text = proseExact[text]; via = 'prose exact'; }
    else { text = applyFrags(text); via = 'buttons+frag'; }
  }
  const ok = !CJK.test(text);
  if (!ok) bad++;
  console.log('  ' + (ok ? 'ok  ' : 'FAIL') + ' ' + what.padEnd(26) +
              ('[' + via + ']').padEnd(15) + text.slice(0, 58));
}

console.log('early exact pass covers: ' + earlySel + '\n');
console.log('.stat_tooltip');
// The reported case. Without .stat_tooltip in the early set this comes out as
// "Gems耐性，全称Gems软上限起始点倍率(…)" - the pair ['宝石','Gems'] sits at the
// END of that selector's list and eats the sentence.
check('SCGV description', '.stat_tooltip',
      '宝石耐性，全称宝石软上限起始点倍率(SoftCappedGemValue)');
check('Luck description', '.stat_tooltip', '幸运(影响材料掉率,杀怪经验)');
check('basic-attack mult', '.stat_tooltip', '普通攻击的伤害倍率');
check('defense description', '.stat_tooltip', '防御，用于抵消攻击伤害');

// ---- the hot list must not widen into #skill_list -------------------------
// translateHot runs FULL applyProse, regexes included. #skill_list must never
// be on it: the category headers would be half-translated by the
// `${category} 技能` template before the v4.0 pair could render them whole.
// That is the exact trap the narrow .skill_bar_name selector avoids, so assert
// the scope rather than trusting the comment.
console.log('\nhot-list scope');
const hotIds = src.slice(src.indexOf('const HOT_IDS = ['),
                         src.indexOf('];', src.indexOf('const HOT_IDS = [')));
// HOT_SEL is composed from HOT_TOOLTIP_SEL, so both have to be in scope.
const hotTipMatch = src.match(/const HOT_TOOLTIP_SEL = [^;]+;/);
const hotSel = eval((hotTipMatch ? hotTipMatch[0] + '\n' : '') +
                    src.match(/const HOT_SEL = [^;]+;/)[0] + '\nHOT_SEL');
function assert(what, cond, detail) {
  if (!cond) bad++;
  console.log('  ' + (cond ? 'ok  ' : 'FAIL') + ' ' + what.padEnd(41) + (detail || ''));
}
assert('#skill_list not in HOT_IDS', hotIds.indexOf("'skill_list'") === -1);
assert('HOT_SEL still covers bar names',
       hotSel.indexOf('.skill_bar_name') !== -1, hotSel);
// A :hover term MUST carry its parent class. ':hover .skill_tooltip' on its own
// matches every skill tooltip in the DOM - <body> is always in the hover chain
// and they all descend from it - which would turn a 0-1 element query into a
// ~111 element walk, the exact cost the hover scoping exists to avoid.
hotSel.split(',').forEach((term) => {
  const t = term.trim();
  if (t.indexOf(':hover') === -1) return;
  assert('  :hover term is parent-scoped: ' + t, /^[.#][\w-]+:hover\s+\S/.test(t), t);
});
// And the reason it must: this is what a full prose pass does to a header.
const catHeader = applyFrags(applyPairs('秘法 技能', pairsFor('#skill_list')));
assert('category header handled by v4.0', !CJK.test(catHeader), catHeader);

// The open tooltip's decoration has to be restored in the SAME batch as its
// translation. Restoring only the text leaves the "(x1.70e6)" suffix flickering
// on its own - the mistake v12.6 fixed for maxed bars, in a new place. Nothing
// that tests annotateXpGain in isolation can see this.
const hotFn = src.slice(src.indexOf('    function translateHot() {'));
const hotBody = hotFn.slice(0, hotFn.indexOf('\n    }\n'));
assert('translateHot re-annotates the open tooltip',
       /annotateXpGain\(\w+\)/.test(hotBody));
assert('  scoped to the tooltip, not document',
       hotBody.indexOf('annotateXpGain()') === -1);

// The family roster is translated off-throttle so its taller Chinese frame is
// never painted - but it is ~330 nodes, so it MUST stay behind the visibility
// test. Losing that gate would turn it into a per-batch walk of the whole
// table, which is exactly why HOT_IDS refused it in the first place.
assert('roster translated off-throttle',
       hotBody.indexOf('family_member_list') !== -1);
assert('  gated on the tab being visible',
       /family_div[\s\S]{0,120}style\.display !== 'none'/.test(hotBody));
// style.display, not getComputedStyle: showFamily() sets it inline, so the
// cheap read is correct AND avoids forcing a style flush every batch.
assert('  no getComputedStyle in the hot path',
       hotBody.indexOf('getComputedStyle') === -1);
// v15.1 adds a line to most roster rows. That has to happen in the SAME batch
// as the translation: one frame later it is a height change under the
// scrollbar, which is the fault v13.9 and v14.5 were both spent on. Asserting
// the call site, since nothing about breakRealmNames' own source says where it
// must run - uitest_visuals only checks what it does to the text.
assert('realm names broken in the same batch',
       /applyProse\(famList\);\s*\n\s*breakRealmNames\(\);/.test(hotBody));

// v15.2 stamps message timestamps off the observer's RECORDS. Two properties
// worth pinning, neither visible from the function's own source: it must be
// handed the records (a no-arg call would silently stamp nothing forever), and
// it must NOT be moved into the throttled scan, where the clock reading would
// be up to SCAN_MIN_MS late and could land in the wrong second.
const obs = src.slice(src.indexOf('    new MutationObserver((records) => {'));
const obsBody = obs.slice(0, obs.indexOf('    }).observe('));
assert('stampMessages runs off the observer',
       /stampMessages\(records\);/.test(obsBody));
const scanFn = src.slice(src.indexOf('    function scan() {'));
assert('  and not on the throttled scan',
       scanFn.slice(0, scanFn.indexOf('\n    }\n')).indexOf('stampMessages') === -1);

// ---- the daily rebuild's scroll restore ------------------------------------
// v14.5 puts the scroll offset back after the rebuild, which means the hot path
// now has a reason to touch scrollTop - and touching scrollTop forces a
// synchronous layout exactly like getComputedStyle would. The whole point of
// the design is that it happens ONCE PER GAME DAY rather than once per mutation
// batch, and nothing about the source makes that obvious to a reader, so it is
// asserted: translateHot itself stays free of layout-forcing reads, and every
// one of them lives behind the rebuild test.
const LAYOUT_READS = ['scrollTop', 'scrollHeight', 'getBoundingClientRect',
                      'offsetHeight', 'offsetWidth', 'clientHeight'];
LAYOUT_READS.forEach((prop) => {
  assert('  translateHot never touches ' + prop, hotBody.indexOf(prop) === -1);
});
// Rebuild detection must be node identity, not a measurement - comparing the
// header row we last translated against the one there now. Anything that
// measured the table to decide would reintroduce the per-batch layout flush
// through the back door.
assert('rebuild detected by node identity',
       /famHeadRow !== null && \w+ !== famHeadRow/.test(hotBody) &&
       hotBody.indexOf('firstElementChild') !== -1);
assert('  restore runs only on a rebuild',
       /if \(rebuilt\) restoreFamilyScroll\(/.test(hotBody));

const restoreFn = src.slice(src.indexOf('    function restoreFamilyScroll('));
const restoreBody = restoreFn.slice(0, restoreFn.indexOf('\n    }\n'));
assert('restore WRITES the offset', /famDiv\.scrollTop = famScrollTop;/.test(restoreBody));
// A read would return the value AFTER the browser's own adjustment for this
// frame - the number the fix exists to discard - so the only unguarded touch
// may be the assignment. The debug readout is allowed to read, because it is
// off by default and exists to tell the offset moving apart from the content
// moving; strip those blocks out before checking.
const restoreLive = restoreBody.replace(/if \(FAMILY_SCROLL_DEBUG\) \{[\s\S]*?\n        \}/g, '');
assert('  no unguarded reads outside the debug block',
       restoreLive.indexOf('scrollHeight') === -1 &&
       !/=\s*famDiv\.scrollTop/.test(restoreLive));
assert('  both toggles honoured',
       /FAMILY_SCROLL_RESTORE/.test(restoreBody) &&
       /FAMILY_SCROLL_DEBUG/.test(restoreBody));
// The listener is the only free read of scrollTop there is; if it stopped being
// bound, restore would have nothing to restore TO and would silently no-op.
const watchFn = src.slice(src.indexOf('    function watchFamilyScroll('));
const watchBody = watchFn.slice(0, watchFn.indexOf('\n    }\n'));
assert('scroll offset cached from the scroll event',
       /addEventListener\('scroll'/.test(watchBody) &&
       /famScrollTop = famDiv\.scrollTop/.test(watchBody));
assert('  bound once', /famScrollBound/.test(watchBody));

// ---- shadowed pairs: a long key an earlier short key destroys --------------
// applySelector applies EVERY pair in a list, IN ORDER. So if key A precedes
// key B and A is a substring of B, A fires first and B's translation is dead
// code. This has now shipped three times (SCGV in .stat_tooltip, and both
// stance descriptions in #stance_list_div), so it is enforced rather than
// commented: a shadowed pair is only ACCEPTABLE when one of the early passes
// resolves that text before the buttons loop ever sees it.
console.log('\nshadowed pairs (short key placed before a longer one)');

const bStart = src.indexOf('const buttons = {');
const bBlob = src.slice(bStart, src.indexOf('\n    };', bStart));
const selRe = /^        '([^']+)': \[/gm;
const pairRe = /\['((?:[^'\\]|\\.)*)',\s*'((?:[^'\\]|\\.)*)'\]/g;
const sels = [];
let sm;
while ((sm = selRe.exec(bBlob))) sels.push({ name: sm[1], at: sm.index, end: selRe.lastIndex });
// Sliced to the START OF THE NEXT selector: single-line lists do not end with
// '\n        ],', and slicing to that swallowed every following list.
sels.forEach((s, i) => {
  const body = bBlob.slice(s.end, i + 1 < sels.length ? sels[i + 1].at : bBlob.length);
  s.keys = [];
  pairRe.lastIndex = 0;
  let pm;
  while ((pm = pairRe.exec(body))) s.keys.push(pm[1].replace(/\\'/g, "'"));
});

const earlyFull = eval(src.match(/const EARLY_PROSE_FULL = (\[[^\]]*\])/)[1]);
const earlyExact = eval(src.match(/const EARLY_PROSE_EXACT = (\[[^\]]*\])/)[1]);
const earlySelList = eval(src.match(/const EARLY_PROSE_EXACT_SEL = ([^;]+)/)[1])
    .split(',').map((x) => x.trim());
const covered = (sel) =>
    earlySelList.indexOf(sel) !== -1 ||
    (sel.charAt(0) === '#' && (earlyFull.indexOf(sel.slice(1)) !== -1 ||
                               earlyExact.indexOf(sel.slice(1)) !== -1));

let shadowed = 0;
sels.forEach((s) => {
  s.keys.forEach((later, j) => {
    for (const earlier of s.keys.slice(0, j)) {
      if (!earlier || earlier === later || later.indexOf(earlier) === -1) continue;
      shadowed++;
      const ok = covered(s.name);
      if (!ok) bad++;
      console.log('  ' + (ok ? 'ok  ' : 'FAIL') + ' ' + s.name.padEnd(22) +
                  JSON.stringify(earlier).slice(0, 16).padEnd(18) + 'eats ' +
                  JSON.stringify(later).slice(0, 34) +
                  (ok ? '   (early pass resolves it first)'
                      : '   NOT covered by any early pass'));
      return;
    }
  });
});
console.log('  ' + shadowed + ' shadowed pair(s) across ' + sels.length + ' selectors');

console.log('\n' + (bad ? bad + ' FAILURES' : 'all correct'));
process.exit(bad ? 1 : 0);
